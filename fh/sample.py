"""A deterministic sample file for the backtest tool: 400 customers over 45 days, simulated after the training period."""
import random

from .gen import World, T0, DAY

_CACHE = {}


def sample_rows():
    """The same rows every time. Customers keep the per-customer activity of the training world; fraud scales with population."""
    if "r" not in _CACHE:
        w = World(11, nusr=400, nmer=300)
        _CACHE["r"] = w.window(random.Random(404), T0 + 60 * DAY, T0 + 105 * DAY, boost=400 / 1200)
    return _CACHE["r"]


def sample_csv():
    import csv
    import io
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["ts", "uid", "amt", "chan", "mid", "cat", "dev", "ip", "city", "pers", "coll", "rat", "sim", "label"])
    for e in sample_rows():
        wr.writerow([int(e["ts"]), e["uid"], e["amt"], e["chan"], e["mid"], e["cat"], e["dev"] or "", e["ip"] or "", e["city"],
                     int(e["pers"]), int(e["coll"]), int(e["rat"]), "" if e["sim"] >= 1e3 else e["sim"], 2 if (e["lab"] and e.get("app")) else e["lab"]])
    return buf.getvalue()
