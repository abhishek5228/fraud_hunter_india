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

from . import realdata as rd, psi, shield, graph as mulegraph, copilot, fairness, consortium, integrations as itg, ingest, train, policy, whatif, feat, drift, backtest, audit, persist, sample, redteam
from .engine import Engine
from .geo import CITY
from .gen import T0, DAY, TYPS, CATS, PERS_CATS
from .geo import NIN
from .model import GAM
from .sim import Sim

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
S = {}  # app state
WIRE = []  # last webhook decisions, newest last


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
             ver=model_version(), aud=audit.Audit(os.environ.get("FH_AUDIT_DB", os.path.join(train.ART, "audit.db"))), reviewed=set(), bt={}, ip=itg.IpIntel(), nt=itg.Notifier(), hook=dict(ok=0, bad_sig=0, ignored=0))
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
    return await _decide(t.model_dump(), "api")


async def _decide(x, src, neutral=False):
    """One code path for every entry point (REST, webhook, load test): resolve location, score, guard, audit, alert."""
    commit = x.pop("commit", True)
    x["pers"] = bool(x["pers"]) if x.get("pers") is not None else x["cat"] in PERS_CATS
    x["sim"] = x["sim"] if x.get("sim") is not None else 1e4
    x["ts"] = x.get("ts") or S["sim"].clk
    anon = False
    if x.get("ip") and not (x.get("city") or x.get("lat") is not None):
        g = await run_in_threadpool(S["ip"].lookup, x["ip"])               # real IP -> real place; None when off, private, slow or unknown
        if g and g["lat"] is not None:
            x["city"], x["lat"], x["lon"], x["cty"] = g["city"], g["lat"], g["lon"], g["cty"] or "IN"
        anon = bool(g and g["anon"])
    c = next((c for c in CITY if c[0] == x.get("city")), None)
    if c:
        x["lat"], x["lon"], x["cty"] = x.get("lat") or c[1], x.get("lon") or c[2], x.get("cty") or c[3]
    if (x.get("lat") is None or x.get("lon") is None or not x.get("cty")) and neutral:
        c = CITY[0]                                  # webhook without usable location: a neutral fixed place, so geo signals stay quiet
        x["city"], x["lat"], x["lon"], x["cty"] = c[0], c[1], c[2], c[3]
    if x.get("lat") is None or x.get("lon") is None or not x.get("cty"):
        raise HTTPException(422, "give a known city or lat/lon/cty (or an ip, with a paid IPINFO_TOKEN plan that returns cities)")
    x["city"] = x.get("city") or ""
    x["lab"], x["typ"] = 0, src
    res = S["eng"].score(x, commit=False)
    if anon and x["amt"] >= 10000:                           # escalate only, like every rule: a VPN/proxy/data-centre network on a large payment
        res["hits"].append(dict(lvl=1, code="ANON_NETWORK", msg="Payment came from a VPN, proxy or data-centre network"))
        if res["dec"] == 0:
            res["dec"], res["dname"] = 1, policy.NAMES[1]
            from . import explain
            res["msg"] = explain.customer_msg(1, x["amt"], x["mid"], ["ANON_NETWORK"])
    if commit:
        S["eng"].st.commit(x, upd=res["dec"] == 0)
    res["model"], res["anon"] = S["ver"], anon
    S["aud"].log("score", res["id"], res["uid"], res["amt"], res["chan"], res["dname"], res["p"], [h["code"] for h in res["hits"]], S["ver"],
                 dict(commit=commit, src=src))
    S["nt"].alert(res, src)
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


# ---------------------------------------------------------------- integrations
def _wire(res, ref, method, event):
    WIRE.append(dict(t=time.time(), ref=ref, uid=res["uid"], amt=res["amt"], chan=res["chan"], method=method, event=event, p=res["p"], dec=res["dec"],
                     dname=res["dname"], codes=[h["code"] for h in res["hits"]], why=res["why"], city=res["city"], anon=res["anon"], us=round(res["lat_us"])))
    del WIRE[:-60]


async def _hook(ev):
    tx, why = itg.razorpay_to_tx(ev)
    if tx is None:
        S["hook"]["ignored"] += 1
        return dict(ok=True, ignored=why)
    ref, status, event, method = tx.pop("ref"), tx.pop("status"), tx.pop("event"), tx.pop("method")
    neutral = not tx.get("city")
    res = await _decide(dict(tx, coll=False, rat=False, commit=True), "razorpay", neutral=True)
    _wire(res, ref, method, event)
    S["hook"]["ok"] += 1
    bc({"t": "wire", "d": WIRE[-1]})
    return dict(ok=True, payment=ref, decision=res["dname"], risk=res["score"], reasons=[h["code"] for h in res["hits"]],
                action={0: "capture", 1: "hold for step-up / manual review", 2: "refuse / refund"}[res["dec"]],
                location="neutral (no city supplied; IP gives country/network only on the free plan)" if neutral else "from notes.city")


@app.post("/api/webhook/razorpay")
async def razorpay_hook(req: Request):
    """Razorpay webhook. Authenticated by HMAC signature, not by X-API-Key (Razorpay cannot send custom headers)."""
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "RAZORPAY_WEBHOOK_SECRET is not set on the server")
    raw = await req.body()
    if len(raw) > 200_000:
        raise HTTPException(413, "payload too large")
    if not itg.verify_razorpay(raw, req.headers.get("x-razorpay-signature", ""), secret):
        S["hook"]["bad_sig"] += 1
        raise HTTPException(401, "bad signature")
    try:
        ev = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "body is not JSON")
    return await _hook(ev)


@app.post("/api/webhook/razorpay/replay", dependencies=[Depends(guard)])
async def razorpay_replay(req: Request):
    """Demo/testing: feed a Razorpay-shaped event through the same path WITHOUT a signature (still needs X-API-Key if one is set)."""
    return await _hook(await req.json())


@app.get("/api/wire")
async def wire():
    return dict(events=WIRE[-30:][::-1])


@app.get("/api/integrations")
async def integrations():
    ip = S["ip"]
    return dict(
        razorpay=dict(on=bool(os.environ.get("RAZORPAY_WEBHOOK_SECRET")), url="/api/webhook/razorpay", **S["hook"]),
        ipinfo=dict(on=ip.on, cached=len(ip.cache), cache_hits=ip.hits, errors=ip.errs),
        alerts=S["nt"].status(), auth=bool(os.environ.get("FH_API_KEY")),
        llm=dict(on=bool(copilot.provider()), provider=(copilot.provider() or ("", "", ""))[0], model=(copilot.provider() or ("", "", ""))[2]))


@app.post("/api/llm/check", dependencies=[Depends(guard)])
async def llm_check():
    """One real call to the LLM on a fixture (no customer data), so the key and model name can be tested from the UI."""
    r = await run_in_threadpool(copilot.check)
    S["aud"].log("llm_check", detail=dict(ok=r["ok"]), model=S["ver"])
    return r


@app.post("/api/alerts/test", dependencies=[Depends(guard)])
async def alert_test():
    if not S["nt"].channels:
        raise HTTPException(409, "no alert channel configured (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, or SLACK_WEBHOOK_URL)")
    return await run_in_threadpool(S["nt"].test)


@app.post("/api/loadtest", dependencies=[Depends(guard)])
async def loadtest(n: int = 3000):
    """Time the engine on n fresh payments (isolated copy of the store: nothing here touches live state)."""
    n = max(200, min(n, 20000))

    import copy
    import statistics
    w, sim = S["w"], S["sim"]
    eng = Engine(S["g"], copy.deepcopy(S["eng"].st), S["eng"].cfg, keep=1)      # private copy, taken on the event loop so it is consistent
    evs = list(w.window(random.Random(5), sim.clk, sim.clk + 24 * 3600, 1.0))[:n]

    def run():
        lat, t0 = [], time.perf_counter()
        for x in evs:
            a = time.perf_counter_ns()
            eng.score(x, commit=True)
            lat.append((time.perf_counter_ns() - a) / 1000.0)
        dt = time.perf_counter() - t0
        lat.sort()
        q = lambda f: lat[min(len(lat) - 1, int(f * len(lat)))]
        return dict(n=len(lat), seconds=round(dt, 2), per_sec=round(len(lat) / dt), p50_us=round(q(.5)), p95_us=round(q(.95)), p99_us=round(q(.99)),
                    max_us=round(lat[-1]), mean_us=round(statistics.fmean(lat)),
                    note="single Python process, engine only (features + model + rules + policy). Network and JSON add more; tools/loadtest.py measures HTTP end to end.")
    return await run_in_threadpool(run)


# ---------------------------------------------------------------- scam shield, mule graph, copilot, fairness, consortium
RATE = {}


def _limit(req, per_min=40):
    ip = (req.headers.get("x-forwarded-for", "").split(",")[0].strip() or (req.client.host if req.client else "?"))
    q, now = RATE.setdefault(ip, []), time.time()
    q[:] = [t for t in q if now - t < 60]
    if len(q) >= per_min:
        raise HTTPException(429, "too many checks; try again in a minute")
    q.append(now)
    if len(RATE) > 5000:
        RATE.clear()


class Sh(BaseModel):
    text: str


@app.get("/api/shield/rules")
async def shield_rules():
    return shield._R


@app.post("/api/shield")
async def shield_ep(b: Sh, req: Request):
    """Public on purpose: it only reads the text it is given and returns a verdict. Rate limited per IP."""
    _limit(req)
    if not b.text.strip() or len(b.text) > 4000:
        raise HTTPException(422, "send between 1 and 4000 characters")
    st, now = S["eng"].st, S["sim"].clk
    net = None
    for h in shield.handles(shield.expand(b.text))[:3]:
        fan = sum(1 for t in st.pu.get(h, {}).values() if 0 <= now - t <= 7 * 86400)
        bad = st.nbad("m:" + h, now)
        if fan or bad:
            net = dict(fan_in=max(fan, (net or {}).get("fan_in", 0)), complaints=max(bad, (net or {}).get("complaints", 0)))
    hs = shield.handles(shield.expand(b.text))
    owner = await run_in_threadpool(shield.owner_lookup, hs[0]) if hs and os.environ.get("RAZORPAY_KEY_ID") else None
    return dict(shield.check(b.text, net, owner), network=net)


class Rp(BaseModel):
    handle: str


@app.post("/api/shield/report", dependencies=[Depends(guard)])
async def shield_report(r: Rp):
    """A confirmed complaint about a payment handle (guarded: an open endpoint would let anyone smear a handle). Feeds the payee reputation."""
    if not shield.VPA.fullmatch(r.handle.strip()):
        raise HTTPException(422, "not a UPI handle (name@bank)")
    h = r.handle.strip()
    S["eng"].st.bad["m:" + h].append(S["sim"].clk)
    S["aud"].log("shield_report", detail=dict(handle=mulegraph.mask(h)), model=S["ver"])
    return dict(ok=True, complaints=S["eng"].st.nbad("m:" + h, S["sim"].clk))


@app.get("/api/graph")
async def graph_ep(top: int = 10):
    return mulegraph.build(S["eng"].st, S["sim"].clk, top=max(1, min(top, 30)))


class Vd(BaseModel):
    id: str
    verdict: str          # mule | legit


@app.post("/api/graph/verdict", dependencies=[Depends(guard)])
async def graph_verdict(v: Vd):
    try:
        pay = mulegraph.verdict(S["eng"].st, v.id, v.verdict, S["sim"].clk)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if pay is None:
        raise HTTPException(404, "that hub has aged out of the last week")
    S["aud"].log("graph_verdict", v.id, detail=dict(verdict=v.verdict, payee=mulegraph.mask(pay)), model=S["ver"])
    return dict(ok=True, verdict=v.verdict)


@app.get("/api/case/{cid}/brief", dependencies=[Depends(guard)])
async def brief_ep(cid: str, llm: bool = False):
    c = S["eng"].cases.get(cid)
    if not c:
        raise HTTPException(404, "case expired or unknown")
    b = await run_in_threadpool(copilot.brief, c, llm)
    S["aud"].log("brief", cid, c["uid"], c["amt"], c["chan"], c["dname"], c["p"], model=S["ver"], detail=dict(source=b["source"]))
    return b


@app.get("/api/fairness")
async def fairness_ep(refresh: bool = False):
    f = S.get("fair")
    if f is None or refresh or f["ver"] != S["ver"]:
        import copy
        st = copy.deepcopy(S["eng"].st)           # copy on the event loop so it is consistent; the replay runs off-loop
        r = await run_in_threadpool(fairness.run, S["g"], st, S["w"], S["eng"].cfg, S["sim"].clk)
        f = S["fair"] = dict(r, ver=S["ver"])
    return f


@app.get("/api/consortium")
async def consortium_status():
    st = S["eng"].st
    psi_banks = {v["bank"] for v in getattr(st, "cons_plain", {}).values()}
    return dict(on=bool(consortium.key()), imported=len(getattr(st, "cons", {})), banks=sorted({v["bank"] for v in getattr(st, "cons", {}).values()} | psi_banks),
                psi=dict(matched=len(getattr(st, "cons_plain", {})), peers=[u for u in os.environ.get("FH_PSI_PEERS", "").split(",") if u.strip()]))


@app.post("/api/consortium/export", dependencies=[Depends(guard)])
async def consortium_export(bank: str = "this-bank"):
    try:
        return consortium.export(S["eng"].st, S["sim"].clk, bank[:40])
    except ValueError as e:
        raise HTTPException(503, str(e))


@app.post("/api/consortium/import", dependencies=[Depends(guard)])
async def consortium_import(req: Request):
    try:
        new = consortium.ingest(S["eng"].st, await req.json(), now=None)
    except ValueError as e:
        raise HTTPException(422 if consortium.key() else 503, str(e))
    S["aud"].log("consortium_import", detail=dict(new=new), model=S["ver"])
    return dict(ok=True, new=new, total=len(S["eng"].st.cons))


# ---------------------------------------------------------------- private set intersection (no shared key)
PSI_USE = []


def _party():
    if "psi" not in S:
        S["psi"] = psi.Party.load(os.path.join(train.ART, "psi.key"))
    return S["psi"]


@app.get("/api/psi/set", dependencies=[Depends(guard)])
async def psi_set(bank: str = "this-bank"):
    """Our flagged payees, blinded with our secret and shuffled. Reveals nothing to someone who does not already hold the same payee."""
    items = consortium.evidence(S["eng"].st, S["sim"].clk)
    return dict(bank=bank[:40], ts=int(time.time()), n=len(items), set=await run_in_threadpool(_party().published_set, items))


@app.post("/api/psi/reblind", dependencies=[Depends(guard)])
async def psi_reblind(req: Request):
    """Blind a peer's questions with our secret. Budget: 6 calls per hour, 10,000 values each, every call audited."""
    now = time.time()
    PSI_USE[:] = [t for t in PSI_USE if now - t < 3600]
    if len(PSI_USE) >= 6:
        raise HTTPException(429, "query budget used up (6 per hour); this limits how many guessed payees a peer can test")
    body = await req.json()
    try:
        out = await run_in_threadpool(_party().reblind, body.get("q", []))
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(422, str(e))
    PSI_USE.append(now)
    S["aud"].log("psi_reblind", detail=dict(n=len(out)), model=S["ver"])
    return dict(r=out)


class PsiSync(BaseModel):
    peer: str
    bank: str = "peer"
    key: str | None = None


@app.post("/api/psi/sync", dependencies=[Depends(guard)])
async def psi_sync(b: PsiSync):
    """Ask a peer bank which of OUR payees it has flagged. The peer must be listed in FH_PSI_PEERS (stops this being used to make the server fetch arbitrary URLs)."""
    import urllib.request
    allowed = [u.strip().rstrip("/") for u in os.environ.get("FH_PSI_PEERS", "").split(",") if u.strip()]
    peer = b.peer.rstrip("/")
    if peer not in allowed:
        raise HTTPException(403, "peer is not listed in FH_PSI_PEERS")
    hdr_ = {"content-type": "application/json", **({"x-api-key": b.key or os.environ.get("FH_PSI_PEER_KEY", "")} if (b.key or os.environ.get("FH_PSI_PEER_KEY")) else {})}

    def call(path, body=None):
        r = urllib.request.Request(peer + path, None if body is None else json.dumps(body).encode(), hdr_)
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read(50_000_000))
    st = S["eng"].st
    mine = list(st.pu)[:psi.MAX_QUERY]
    try:
        got = await run_in_threadpool(lambda: psi.sync(_party(), mine, lambda: call("/api/psi/set")["set"], lambda q: call("/api/psi/reblind", {"q": q})["r"]))
    except (OSError, ValueError, KeyError) as e:
        raise HTTPException(502, "peer sync failed: %s" % type(e).__name__)
    for m in got:
        st.cons_plain[m] = dict(bank=b.bank[:40], ts=int(time.time()))
    S["aud"].log("psi_sync", detail=dict(asked=len(mine), matched=len(got), peer=b.bank[:40]), model=S["ver"])
    return dict(ok=True, asked=len(mine), matched=len(got), total=len(st.cons_plain))


# ---------------------------------------------------------------- real public datasets (the "Real data" tab)
def _uploads_ok():
    return bool(os.environ.get("FH_API_KEY")) or os.environ.get("FH_ALLOW_UPLOADS") == "1"


@app.get("/api/realdata")
async def realdata_list(verify: bool = False):
    ds = await run_in_threadpool(lambda: [rd.status(i, verify) for i in rd.DATASETS])
    return dict(datasets=ds, recorded=rd.RECORDED, jobs=list(rd.JOBS.values())[-4:], uploads=_uploads_ok(), can_replay="ulb" in rd.STATE, data_dir=rd.data_dir())


def _known(i):
    if i not in rd.DATASETS:
        raise HTTPException(404, "unknown dataset")


@app.post("/api/realdata/{i}/fetch", dependencies=[Depends(guard)])
async def realdata_fetch(i: str):
    """Download the dataset from its fixed source address (never an address supplied by the caller)."""
    _known(i)
    try:
        jid = rd.start("fetch " + i, lambda prog: dict(dataset=i, bytes=rd.fetch(i, lambda n: prog(0.5, "%.1f MB" % (n / 1e6))), status=rd.status(i, True)))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return dict(job=jid)


@app.post("/api/realdata/{i}/upload", dependencies=[Depends(guard)])
async def realdata_upload(i: str, req: Request):
    _known(i)
    if not _uploads_ok():
        raise HTTPException(403, "uploads are off on this server: set FH_API_KEY (recommended) or FH_ALLOW_UPLOADS=1")
    try:
        n = await rd.receive(i, req)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:                                     # an unreadable file is the user's problem to see, not a server error
        raise HTTPException(422, "could not read that file (%s)" % type(e).__name__)
    S["aud"].log("realdata_upload", detail=dict(dataset=i, bytes=n), model=S["ver"])
    return dict(ok=True, bytes=n, status=await run_in_threadpool(rd.status, i, True))


@app.post("/api/realdata/run/{which}", dependencies=[Depends(guard)])
async def realdata_run(which: str):
    fn = dict(ulb=rd.bench_ulb, shield=rd.bench_shield).get(which)
    if not fn:
        raise HTTPException(404, "which must be ulb or shield")
    try:
        jid = rd.start("benchmark " + which, fn)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    S["aud"].log("realdata_run", detail=dict(which=which), model=S["ver"])
    return dict(job=jid)


@app.get("/api/realdata/job/{jid}")
async def realdata_job(jid: str):
    j = rd.JOBS.get(jid)
    if not j:
        raise HTTPException(404, "unknown or expired job")
    return j


@app.get("/api/realdata/replay")
async def realdata_replay(offset: int = 0, n: int = 25, to_fraud: bool = False):
    try:
        return rd.replay(offset, n, to_fraud)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/realdata/sample")
async def realdata_sample(kind: str = "smish"):
    if kind not in ("smish", "spam", "ham", "india"):
        raise HTTPException(422, "kind must be smish, spam, ham or india")
    try:
        r = await run_in_threadpool(rd.sample_text, kind)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return dict(r, verdict=shield.check(r["text"]))
