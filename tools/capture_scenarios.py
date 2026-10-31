"""Drive the real UI against a running backend and record every /api/score call the Playground scenarios make.

    python -m uvicorn fh.api:app --port 8000 &       # a fresh backend
    python tools/capture_scenarios.py                # merges 'users' and 'scenarios' into dist/demo-data.json
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("FH_URL", "http://localhost:8000")


async def main():
    users, calls = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1500, "height": 900})

        async def users_route(route):
            r = await route.fetch()
            data = (await r.json())[:5]          # a fixed, small cast so every scenario is about the same customer
            users[:] = data
            await route.fulfill(json=data)
        await pg.route("**/api/users*", users_route)

        async def on_resp(resp):
            if resp.url.endswith("/api/score") and resp.request.method == "POST":
                calls.append(dict(req=json.loads(resp.request.post_data), res=await resp.json()))
        pg.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
        await pg.goto(BASE + "/")
        await pg.click('.tabs button[data-tab=play]')
        await pg.wait_for_selector("#scen button")
        n = len(await pg.query_selector_all("#scen button"))
        for i in range(n):
            await (await pg.query_selector_all("#scen button"))[i].click()
            await pg.wait_for_timeout(2500)
        await b.close()
    path = os.path.join(ROOT, "dist", "demo-data.json")
    data = json.load(open(path))
    data["users"], data["scenarios"] = users, calls
    json.dump(data, open(path, "w"), separators=(",", ":"), default=float)
    print("captured %d scenarios, %d /api/score calls, %d users" % (n, len(calls), len(users)))


asyncio.run(main())
