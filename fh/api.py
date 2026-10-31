"""FastAPI service: scoring API, SSE live stream, policy lab, model card, analyst feedback."""
import os
import json
import time
import hmac
import pickle
import hashlib
import asyncio
import random
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ingest, train, policy, whatif, feat, drift, backtest, audit, persist, sample, redteam
from .engine import Engine
from .geo import CITY
from .gen import T0, DAY, TYPS, CATS, PERS_CATS
from .geo import NIN
from .model import GAM
from .sim import Sim

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
S = {}  # app state


def load():
    f = lambda n: os.path.join(train.ART, n)
    if not os.path.exists(f("model.json")) or not os.path.exists(f("world.pkl")):
        print("no artifacts found, training (about 30s) ...")
        train.main()
    g = GAM.load(json.load(open(f("model.json"))))
    w, st = pickle.load(open(f("world.pkl"), "rb"))
    rep = json.load(open(f("report.json")))
    h = dict(np.load(f("holdout.npz"), allow_pickle=True))
    eng = Engine(g, st, policy.Cfg())
    return g, w, rep, h, eng


def model_version():
    return hashlib.sha1(open(os.path.join(train.ART, "model.json"), "rb").read()).hexdigest()[:8]


STATE = os.path.join(train.ART, "state.pkl")


def guard(req: Request):
    """If FH_API_KEY is set, integration endpoints need a matching X-API-Key header."""
    k = os.environ.get("FH_API_KEY")
    if k and not hmac.compare_digest(req.headers.get("x-api-key", ""), k):
        raise HTTPException(401, "missing or wrong X-API-Key header")


@asynccontextmanager
async def life(app):
    g, w, rep, h, eng = load()
    if os.environ.get("FH_STATE", "1") != "0":     # resume from the last snapshot of what the engine had learned
        old = persist.load(STATE, os.path.getmtime(os.path.join(train.ART, "world.pkl")))
        if old is not None:
            eng.st = old
            print("restored feature store from", STATE)
    S.update(g=g, w=w, rep=rep, h=h, eng=eng, sim=Sim(eng, w, T0 + train.DAYS * DAY), subs=set(), fb=dict(fraud=0, legit=0, blocks=0),
             ver=model_version(), aud=audit.Audit(os.environ.get("FH_AUDIT_DB", os.path.join(train.ART, "audit.db"))), reviewed=set(), bt={})
    task = asyncio.create_task(pump())
    yield
    task.cancel()
    if os.environ.get("FH_STATE", "1") != "0":
        persist.save(eng.st, STATE)


app = FastAPI(title="Fraud Hunter India", version="1.1", lifespan=life)
# A static frontend hosted elsewhere (Netlify, Vercel, GitHub Pages) can call this API. Restrict in production:
#   FH_ORIGINS="https://my-frontend.netlify.app,https://example.com"
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get("FH_ORIGINS", "*").split(",") if o.strip()],
                   allow_methods=["GET", "POST"], allow_headers=["content-type", "x-api-key"])


async def pump():
    sim, last, lsnap, lsave = S["sim"], time.time(), 0.0, time.time()
    while True:
        await asyncio.sleep(0.1)
        now = time.time()
        msgs = sim.tick(now - last)
        last = now
        if msgs:
            bc({"t": "tx", "d": msgs})
        if now - lsave >= 120 and os.environ.get("FH_STATE", "1") != "0":
            lsave = now
            await run_in_threadpool(persist.save, S["eng"].st, STATE)
        if now - lsnap >= 1.0:
            lsnap = now
            bc({"t": "st", "d": sim.snap()})


def bc(m):
    s = "data: " + json.dumps(m, separators=(",", ":")) + "\n\n"
    for q in list(S["subs"]):
        try:
            q.put_nowait(s)
        except asyncio.QueueFull:
            S["subs"].discard(q)  # slow consumer: drop it, it will reconnect


@app.get("/api/stream")
async def stream(req: Request):
    q = asyncio.Queue(maxsize=400)
    S["subs"].add(q)
    q.put_nowait("data: " + json.dumps({"t": "st", "d": S["sim"].snap()}) + "\n\n")

    async def gen():
        try:
            while not await req.is_disconnected():
                try:
                    yield await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            S["subs"].discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- scoring
class Tx(BaseModel):
    uid: str
    mid: str = "shop@upi"
    cat: str = "digital"
    amt: float
    chan: str = "upi"      # upi | ecom | pos | atm | imps
    pers: bool | None = None   # payee is a person/account (defaults from category)
    coll: bool = False         # approving a collect request
    rat: bool = False          # screen-sharing / remote-access app detected
    sim: float | None = None   # hours since SIM change
    ts: float | None = None
    dev: str | None = None
    ip: str | None = None
    city: str | None = None
    lat: float | None = None
    lon: float | None = None
    cty: str | None = None
    commit: bool = True


@app.post("/api/score", dependencies=[Depends(guard)])
async def score(t: Tx):
    if t.cat not in CATS:
        raise HTTPException(422, "unknown cat; one of %s" % sorted(CATS))
    if t.amt <= 0:
        raise HTTPException(422, "amt must be > 0")
    if t.chan not in ("upi", "ecom", "pos", "atm", "imps"):
        raise HTTPException(422, "chan must be upi, ecom, pos, atm or imps")
    x = t.model_dump()
    commit = x.pop("commit")
    x["pers"] = bool(x["pers"]) if x["pers"] is not None else t.cat in PERS_CATS
    x["sim"] = x["sim"] if x["sim"] is not None else 1e4
    x["ts"] = x["ts"] or S["sim"].clk
    c = next((c for c in CITY if c[0] == x["city"]), None)
    if c:
        x["lat"], x["lon"], x["cty"] = x["lat"] or c[1], x["lon"] or c[2], x["cty"] or c[3]
    if x["lat"] is None or x["lon"] is None or not x["cty"]:
        raise HTTPException(422, "give a known city or lat/lon/cty")
    x["city"] = x["city"] or ""
    x["lab"], x["typ"] = 0, "api"
    res = S["eng"].score(x, commit=commit)
    res["model"] = S["ver"]
    S["aud"].log("score", res["id"], res["uid"], res["amt"], res["chan"], res["dname"], res["p"], [h["code"] for h in res["hits"]], S["ver"],
                 dict(commit=commit, src="api"))
    return res


@app.get("/api/case/{cid}")
async def case(cid: str):
    c = S["eng"].cases.get(cid)
    if not c:
        raise HTTPException(404, "case expired or unknown")
    return dict(c, truth=S["sim"].truth.get(cid))


class Cf(BaseModel):
    id: str
    passed: bool


@app.post("/api/confirm", dependencies=[Depends(guard)])
async def confirm(c: Cf):
    """Second phase of a step-up: tell the engine whether the customer passed the challenge."""
    if not S["eng"].confirm(c.id, c.passed):
        raise HTTPException(404, "unknown case, or it was not a step-up")
    S["aud"].log("confirm", c.id, model=S["ver"], detail=dict(passed=c.passed))
    return dict(ok=True)


class Fb(BaseModel):
    id: str
    verdict: str  # fraud | legit
    block: bool = False


@app.post("/api/feedback", dependencies=[Depends(guard)])
async def feedback(f: Fb):
    c = S["eng"].cases.get(f.id)
    if not c:
        raise HTTPException(404, "case expired or unknown")
    if f.verdict == "fraud":
        S["eng"].st.report(c, S["sim"].clk)
        S["fb"]["fraud"] += 1
        if f.block:
            for k in ("d:" + c["dev"] if c["dev"] else None, "i:" + feat.ip24(c["ip"]) if c["ip"] else None):
                if k:
                    S["eng"].st.blk.add(k)
                    S["fb"]["blocks"] += 1
    elif f.verdict == "legit":
        S["fb"]["legit"] += 1
    else:
        raise HTTPException(422, "verdict must be fraud or legit")
    S["reviewed"].add(f.id)
    S["aud"].log("feedback", f.id, c["uid"], c["amt"], c["chan"], c["dname"], c["p"], model=S["ver"], detail=dict(verdict=f.verdict, block=f.block))
    return dict(ok=True, fb=S["fb"], blocklist=len(S["eng"].st.blk))


# ------------------------------------------------------------- sim control
class Ctl(BaseModel):
    spd: float | None = None
    run: bool | None = None
    boost: float | None = None
    fest: float | None = None
    reset: bool = False


@app.post("/api/sim")
async def ctl(c: Ctl):
    s = S["sim"]
    if c.spd is not None:
        s.spd = max(10.0, min(2000.0, c.spd))
    if c.run is not None:
        s.run = c.run
    if c.boost is not None:
        s.boost = max(0.0, min(10.0, c.boost))
    if c.fest is not None:
        s.w.fest = max(1.0, min(4.0, c.fest))
    if c.reset:
        s.reset()
    return dict(s.snap(), fest=s.w.fest)


class Atk(BaseModel):
    kind: str


@app.post("/api/attack")
async def attack(a: Atk):
    kinds = TYPS if a.kind == "mix" else [a.kind]
    if any(k not in TYPS for k in kinds):
        raise HTTPException(422, "kind must be one of %s or mix" % TYPS)
    return dict(kinds=kinds, injected=sum(S["sim"].attack(k) for k in kinds))


# ------------------------------------------------------------- policy + model
@app.get("/api/policy")
async def get_policy():
    return S["eng"].cfg.dict()


@app.post("/api/policy", dependencies=[Depends(guard)])
async def set_policy(d: dict):
    new = S["eng"].cfg.update(d).dict()
    S["aud"].log("policy", model=S["ver"], detail=new)
    return new


@app.post("/api/policy/lab")
async def policy_lab(d: dict):
    c = policy.Cfg().update({**S["eng"].cfg.dict(), **d})
    return whatif.lab(S["h"], c)


DESC = dict(
    lamt="log payment amount", zamt="amount vs this customer's own history (z-score of log amount)",
    rmax="amount vs largest payment on record", c1m="payments in the previous minute", c10m="payments in the previous 10 minutes",
    c1h="payments in the previous hour", c24h="payments in the previous 24 hours", s1h="rupees sent in the previous hour",
    ndev="device never seen on this account", nip="network (IP /24) never seen", ncty="country never seen",
    nmer="payee never paid before", ncat="category never used", hrar="rarity of this hour (IST) for this customer",
    dkm="km from last card-present location", sped="implied km/h from last card-present location", hkm="km from customer centroid",
    devu="other accounts on this device (7d)", ipu="other accounts on this network (7d)", dbad="fraud reports on this device (7d)",
    ibad="fraud reports on this network (7d)", mbad="fraud complaints against this payee (7d)", ecom="online card payment",
    atm="ATM withdrawal", upi="UPI payment", imps="IMPS / net-banking transfer", crsk="category risk prior",
    cold="fewer than 4 prior transactions", tiny="online micro-amount x recent velocity", rnd="round amount >= Rs 1,000",
    lim="amount just under a Rs 50k / 1L / 2L limit", pers="payee is a person or account", fanin="other customers who paid this payee (7d)",
    pfirst="payee never seen on the platform", simc="SIM changed in the last 72 hours", rat="screen-share / remote-access app active",
    coll="payment approves a collect request", xdz="new device x unusual amount", xdc="new device x risky category",
    xhz="far from home x unusual amount", xrz="screen-share x unusual amount", xnz="first-time person payee x unusual amount",
    xsd="new device x recent SIM change", xnf="first-time payee x other customers paying it",
)


@app.get("/api/model")
async def model_card():
    g, rep = S["g"], S["rep"]
    shapes = []
    for j, n in enumerate(g.names):
        e, v = g.el[j], g.sl[j]
        shapes.append(dict(f=n, desc=DESC.get(n, ""), edges=e, v=v))
    return dict(rep=rep, shapes=shapes, b0=g.b0, nfeat=len(g.names))


@app.get("/api/drift")
async def drift_ep():
    """Population stability index of recent traffic against the training distribution, per feature."""
    eng = S["eng"]
    if len(eng.vecs) < 600:
        return dict(n=len(eng.vecs), ready=False, feats=[])
    return dict(drift.psi(eng.vecs, S["g"], S["rep"], DESC), fest=S["w"].fest)


@app.get("/api/users")
async def users(n: int = 12):
    w = S["w"]
    out = []
    for u in random.sample(w.users, min(n, 60)):
        P = S["eng"].st.u.get(u["uid"])
        out.append(dict(uid=u["uid"], city=CITY[u["hc"]][0], dev=u["devs"][0], ip=u["ips"][0] + ".10",
                        txns=P.n if P else 0, typ=round(w.mean(u)), contact=u["ct"][0], merchant=w.mers[u["fp"][0]]["mid"] if u["fp"] else "shop@upi",
                        ben=u["ben"][0], vpa=u["vpa"]))
    return out


@app.get("/api/meta")
async def meta():
    return dict(cities=[c[0] for c in CITY], nin=NIN, cats=sorted(CATS), kinds=TYPS, cfg=S["eng"].cfg.dict(), start=T0 + train.DAYS * DAY,
                fest=S["w"].fest)


@app.get("/api/health")
async def health():
    return dict(ok=True, n=S["sim"].n, p99_us=S["eng"].pct(0.99), model=S["ver"], auth=bool(os.environ.get("FH_API_KEY")))


@app.get("/api/audit", dependencies=[Depends(guard)])
async def audit_log(limit: int = 50, kind: str | None = None):
    return dict(total=S["aud"].count(), rows=S["aud"].recent(limit, kind))


@app.get("/api/queue", dependencies=[Depends(guard)])
async def queue(limit: int = 40):
    """Challenged or declined payments nobody has reviewed yet, newest first."""
    out = []
    for c in reversed(S["eng"].cases.values()):
        if c["dec"] > 0 and c["id"] not in S["reviewed"]:
            out.append(dict(id=c["id"], ts=c["ts"], uid=c["uid"], amt=c["amt"], chan=c["chan"], cat=c["cat"], city=c["city"], dec=c["dec"], p=c["p"],
                            hits=[h["code"] for h in c["hits"]], why=c["why"]))
            if len(out) >= limit:
                break
    return dict(open=len(out), cases=out)


@app.post("/api/backtest", dependencies=[Depends(guard)])
async def backtest_ep(req: Request):
    """Body: the CSV text (content-type text/csv). Replays it through an isolated copy of the engine and returns the report."""
    raw = await req.body()
    if len(raw) > 25_000_000:
        raise HTTPException(413, "file too large (limit 25 MB)")
    try:
        canon, irep = ingest.convert(raw.decode("utf-8-sig", errors="replace"))
        rows, bad = backtest.parse(canon)
        bad = irep["notes"] + [b for b in bad if "unknown or missing category" not in b]
        sm, out = await run_in_threadpool(backtest.run, rows, S["g"], S["eng"].cfg)
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(422, str(e))
    sm["problems"], sm["model"], sm["id"] = bad, S["ver"], hashlib.sha1(raw).hexdigest()[:10]
    S["bt"][sm["id"]] = backtest.to_csv(out)
    while len(S["bt"]) > 4:
        S["bt"].pop(next(iter(S["bt"])))
    S["aud"].log("backtest", detail=dict(id=sm["id"], rows=sm["n"]), model=S["ver"])
    return sm


@app.get("/api/backtest/sample", dependencies=[Depends(guard)])
async def backtest_sample():
    """The built-in 45-day sample file, run through the backtest."""
    sm, out = await run_in_threadpool(lambda: backtest.run(backtest.parse(sample.sample_csv())[0], S["g"], S["eng"].cfg))
    sm["problems"], sm["model"], sm["id"], sm["sample"] = [], S["ver"], "sample", True
    S["bt"]["sample"] = backtest.to_csv(out)
    return sm


class Rt(BaseModel):
    seed: int = 1
    gens: int = 10
    pop: int = 36
    victims: int = 14


RT = dict(lock=None, last=0.0, rounds=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "redteam.json"))


@app.post("/api/redteam/run", dependencies=[Depends(guard)])
async def redteam_run(r: Rt):
    """Let an automated fraudster attack the running engine. Customers are copied into a sandbox; nothing live changes."""
    if RT["lock"] is None:
        RT["lock"] = asyncio.Lock()
    if RT["lock"].locked() or time.time() - RT["last"] < 5:
        raise HTTPException(429, "a red-team run is already in progress or just finished; wait a few seconds")
    async with RT["lock"]:
        clk = S["sim"].clk
        day = (int((clk + 19800) // 86400) + 1) * 86400 - 19800     # the next IST midnight
        g, st, w, cfg = S["g"], S["eng"].st, S["w"], S["eng"].cfg
        res = await run_in_threadpool(lambda: redteam.search(g, st, w, cfg, seed=r.seed, pop=max(8, min(60, r.pop)), gens=max(2, min(15, r.gens)),
                                                            k=max(4, min(30, r.victims)), day_ts=day))
        RT["last"] = time.time()
    res.update(round=0, model=S["ver"])
    S["aud"].log("redteam", model=S["ver"], detail=dict(best=res["best"], evaluated=res["evaluated"], seed=r.seed))
    return res


@app.get("/api/redteam/rounds")
async def redteam_rounds():
    """The recorded hardening experiment (python -m fh.redteam --harden 3)."""
    try:
        return json.load(open(RT["rounds"]))
    except OSError:
        raise HTTPException(404, "no recorded hardening run in this deployment")


@app.get("/api/backtest/{bid}/csv", dependencies=[Depends(guard)])
async def backtest_csv(bid: str):
    if bid not in S["bt"]:
        raise HTTPException(404, "no such backtest (results are kept for the last few runs)")
    return PlainTextResponse(S["bt"][bid], headers={"content-disposition": 'attachment; filename="decisions-%s.csv"' % bid})


@app.get("/")
async def index():
    return FileResponse(os.path.join(WEB, "index.html"))


app.mount("/static", StaticFiles(directory=WEB), name="static")
