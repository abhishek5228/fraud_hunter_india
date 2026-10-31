"""FastAPI service: scoring API, SSE live stream, policy lab, model card, analyst feedback."""
import os
import json
import time
import pickle
import asyncio
import random
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import train, policy, whatif, feat
from .engine import Engine
from .geo import CITY
from .gen import T0, DAY, TYPS, CATS
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


@asynccontextmanager
async def life(app):
    g, w, rep, h, eng = load()
    S.update(g=g, w=w, rep=rep, h=h, eng=eng, sim=Sim(eng, w, T0 + train.DAYS * DAY), subs=set(), fb=dict(fraud=0, legit=0, blocks=0))
    task = asyncio.create_task(pump())
    yield
    task.cancel()


app = FastAPI(title="Fraud Hunter", version="1.0", lifespan=life)


async def pump():
    sim, last, lsnap = S["sim"], time.time(), 0.0
    while True:
        await asyncio.sleep(0.1)
        now = time.time()
        msgs = sim.tick(now - last)
        last = now
        if msgs:
            bc({"t": "tx", "d": msgs})
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
    mid: str = "m_api"
    cat: str = "digital"
    amt: float
    chan: str = "ecom"
    ts: float | None = None
    dev: str | None = None
    ip: str | None = None
    city: str | None = None
    lat: float | None = None
    lon: float | None = None
    cty: str | None = None
    commit: bool = True


@app.post("/api/score")
async def score(t: Tx):
    if t.cat not in CATS:
        raise HTTPException(422, "unknown cat; one of %s" % sorted(CATS))
    if t.amt <= 0:
        raise HTTPException(422, "amt must be > 0")
    x = t.model_dump()
    commit = x.pop("commit")
    x["ts"] = x["ts"] or S["sim"].clk
    c = next((c for c in CITY if c[0] == x["city"]), None)
    if c:
        x["lat"], x["lon"], x["cty"] = x["lat"] or c[1], x["lon"] or c[2], x["cty"] or c[3]
    if x["lat"] is None or x["lon"] is None or not x["cty"]:
        raise HTTPException(422, "give a known city or lat/lon/cty")
    x["city"] = x["city"] or ""
    x["lab"], x["typ"] = 0, "api"
    res = S["eng"].score(x, commit=commit)
    return res


@app.get("/api/case/{cid}")
async def case(cid: str):
    c = S["eng"].cases.get(cid)
    if not c:
        raise HTTPException(404, "case expired or unknown")
    return dict(c, truth=S["sim"].truth.get(cid))


class Fb(BaseModel):
    id: str
    verdict: str  # fraud | legit
    block: bool = False


@app.post("/api/feedback")
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
    return dict(ok=True, fb=S["fb"], blocklist=len(S["eng"].st.blk))


# ------------------------------------------------------------- sim control
class Ctl(BaseModel):
    spd: float | None = None
    run: bool | None = None
    boost: float | None = None
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
    if c.reset:
        s.reset()
    return s.snap()


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


@app.post("/api/policy")
async def set_policy(d: dict):
    return S["eng"].cfg.update(d).dict()


@app.post("/api/policy/lab")
async def policy_lab(d: dict):
    c = policy.Cfg().update({**S["eng"].cfg.dict(), **d})
    return whatif.lab(S["h"], c)


DESC = dict(
    lamt="log transaction amount", zamt="amount vs this customer's own history (z-score of log amount)",
    rmax="amount vs largest purchase on record", c1m="charges in the previous minute", c10m="charges in the previous 10 minutes",
    c1h="charges in the previous hour", c24h="charges in the previous 24 hours", s1h="dollars spent in the previous hour",
    ndev="device never seen on this account", nip="network (IP /24) never seen", ncty="country never seen",
    nmer="merchant never used", ncat="category never used", hrar="rarity of this hour for this customer",
    dkm="km from last card-present location", sped="implied km/h from last card-present location", hkm="km from customer centroid",
    devu="other accounts on this device (7d)", ipu="other accounts on this network (7d)", dbad="fraud reports on this device (7d)",
    ibad="fraud reports on this network (7d)", mbad="fraud reports at this merchant (7d)", ecom="online purchase",
    atm="ATM withdrawal", crsk="category risk prior", cold="fewer than 4 prior transactions", tiny="micro-amount x recent velocity",
    rnd="round amount >= $100", xdz="new device x unusual amount", xdc="new device x risky category", xhz="far from home x unusual amount",
)


@app.get("/api/model")
async def model_card():
    g, rep = S["g"], S["rep"]
    shapes = []
    for j, n in enumerate(g.names):
        e, v = g.el[j], g.sl[j]
        shapes.append(dict(f=n, desc=DESC.get(n, ""), edges=e, v=v))
    return dict(rep=rep, shapes=shapes, b0=g.b0, nfeat=len(g.names))


@app.get("/api/users")
async def users(n: int = 12):
    w = S["w"]
    out = []
    for u in random.sample(w.users, min(n, 60)):
        P = S["eng"].st.u.get(u["uid"])
        out.append(dict(uid=u["uid"], city=CITY[u["hc"]][0], dev=u["devs"][0], ip=u["ips"][0] + ".10",
                        txns=P.n if P else 0, typ=round(w.mean(u), 2)))
    return out


@app.get("/api/meta")
async def meta():
    return dict(cities=[c[0] for c in CITY], cats=sorted(CATS), kinds=TYPS, cfg=S["eng"].cfg.dict(), start=T0 + train.DAYS * DAY)


@app.get("/api/health")
async def health():
    return dict(ok=True, n=S["sim"].n, p99_us=S["eng"].pct(0.99))


@app.get("/")
async def index():
    return FileResponse(os.path.join(WEB, "index.html"))


app.mount("/static", StaticFiles(directory=WEB), name="static")
