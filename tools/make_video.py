"""Film the dashboard (backend-free demo build) with captions -> docs/demo.mp4

    python tools/make_video.py preview     # screenshots of the busiest moments, to check the look
    python tools/make_video.py             # full recording + encode (about 3 minutes)
"""
import asyncio
import os
import shutil
import subprocess
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "file://" + os.path.join(ROOT, "dist", "fraud-hunter-demo.html")
W, H = 1440, 810
PREVIEW = len(sys.argv) > 1 and sys.argv[1] == "preview"

JS = """
window.cap = (t, sub) => { let d = document.getElementById('vcap'); if (!d) { d = document.createElement('div'); d.id = 'vcap';
  d.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:1180px;background:rgba(13,26,45,.94);color:#fff;padding:12px 22px;border-radius:12px;font:600 21px/1.35 Inter,system-ui,sans-serif;z-index:99999;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.35)';
  document.body.append(d); } d.innerHTML = t + (sub ? '<div style="font:400 15px/1.4 Inter,system-ui,sans-serif;color:#b9c6dc;margin-top:4px">' + sub + '</div>' : ''); d.style.display = t ? 'block' : 'none'; };
window.addEventListener('DOMContentLoaded', () => { const c = document.createElement('div'); c.style.cssText = 'position:fixed;width:18px;height:18px;border-radius:50%;background:rgba(43,71,255,.55);border:2px solid #fff;z-index:99998;pointer-events:none;left:-40px;top:-40px;transition:left .35s,top .35s';
  document.body.append(c); document.addEventListener('mousemove', e => { c.style.left = e.clientX - 9 + 'px'; c.style.top = e.clientY - 9 + 'px'; }); });
"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        vd = "/tmp/vid"
        shutil.rmtree(vd, ignore_errors=True)
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=None if PREVIEW else vd, record_video_size={"width": W, "height": H})
        await ctx.add_init_script(JS)
        pg = await ctx.new_page()
        shots = []

        async def say(t, sub="", sec=3.0, shot=None):
            await pg.evaluate("([t,s]) => window.cap(t,s)", [t, sub])
            if PREVIEW and shot:
                await pg.screenshot(path="/tmp/shots/v_%s.png" % shot)
            await pg.wait_for_timeout(300 if PREVIEW else int(sec * 1000))

        async def move(sel):
            el = await pg.query_selector(sel)
            bb = await el.bounding_box()
            await pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, steps=12)

        async def click(sel):
            if sel.startswith(".tabs"):                  # never leave a caption about one screen over another
                await pg.evaluate("window.cap('')")
            await move(sel)
            await pg.wait_for_timeout(150 if PREVIEW else 400)
            await pg.click(sel)

        await pg.goto(PAGE)
        await pg.wait_for_timeout(6000 if not PREVIEW else 4000)
        await say("Fraud Hunter India", "A real-time risk engine for UPI, IMPS and card payments. Everything you see is simulated data.", 5.5, "1_intro")
        await say("Every payment is decided in about 100 microseconds", "Approve, ask for a step-up, or decline. Green rows went straight through.", 4.5)

        # --- SIM swap attack
        await click("#atkb")
        await say("Launch a SIM-swap attack", "The fraudster ports the victim's number, binds UPI on a new phone and drains the account.", 3.5, "2_menu")
        await click('#atkp button[data-k="sim_swap"]')
        await pg.wait_for_timeout(500 if PREVIEW else 7500)
        await click('.chip[data-f="flag"]')
        rows = await pg.query_selector_all("#feed .row")
        pick = None
        for r in rows:
            t = await r.inner_text()
            if "Decline" in t and ("SIM" in t or "MULE" in t):
                pick = r
                break
        pick = pick or rows[0]
        bb = await pick.bounding_box()
        await pg.mouse.move(bb["x"] + 120, bb["y"] + 18, steps=14)
        await pick.click()
        await say("The engine stopped it", "Click any payment to see exactly why.", 3.5, "3_case")
        await pg.evaluate("document.querySelector('#insp').scrollIntoView({behavior:'instant', block:'start'}); window.scrollBy(0,-70)")
        await say("Why this score", "Every bar is the model's own arithmetic: red raises risk, green lowers it. No approximation.", 5.5, "4_why")
        await pg.evaluate("document.querySelector('#insp .wf').scrollIntoView({behavior:'smooth', block:'center'})")
        await pg.wait_for_timeout(500 if PREVIEW else 2500)
        await pg.evaluate("document.querySelector('#insp .phone').scrollIntoView({behavior:'instant', block:'center'})")
        await say("And what the customer sees", "In plain words, with the 1930 helpline. Tap Hindi:", 3.0)
        await click("#insp .phone >> xpath=../div[contains(@class,'chips')]/button[2]")
        await say("Hindi and English, same message", "Never share your PIN or OTP. Report it on cybercrime.gov.in.", 4.5, "5_hindi")
        await pg.evaluate("window.scrollTo(0,0)")

        # --- review
        await click('.tabs button[data-tab="review"]')
        await pg.wait_for_timeout(1200)
        rows = await pg.query_selector_all("#rlist .row")
        if rows:
            bb = await rows[0].bounding_box()
            await pg.mouse.move(bb["x"] + 120, bb["y"] + 18, steps=10)
            await rows[0].click()
            await pg.wait_for_timeout(1000)
        await say("Analysts review what was stopped", "Their answer feeds the engine and is written to an audit log.", 4.0, "6_review")
        btn = await pg.query_selector("#rinsp .btn.bad")
        if btn:
            await click("#rinsp .btn.bad")
        await say("Confirm fraud: the payee and device are now remembered", "", 3.0)

        # --- backtest
        await click('.tabs button[data-tab="backtest"]')
        await pg.wait_for_selector("#bt-out .kpi", timeout=20000)
        await say("Try it on your own history", "Upload a CSV of past payments. Nothing live is touched.", 4.5, "7_backtest")
        await say("What would it have caught?", "On the 45-day sample: 99% of fraud stopped, 3.8% of good customers touched, cost 97 thousand rupees against 1.04 crore for approving everything.", 8.0, "8_report")
        await pg.evaluate("window.scrollTo({top: 330, behavior:'instant'})")
        await say("It shows its weak spots too", "Payee fan-in flagged 377 payments that were all good. IMPS touched 20% of good customers.", 6.0)
        await pg.evaluate("window.scrollTo(0,0)")

        # --- red team
        await click('.tabs button[data-tab="redteam"]')
        await pg.wait_for_selector("#rt-out .kpi", timeout=20000)
        await say("Now the engine attacks itself", "An automated fraudster tries 360 strategies against real customer histories. The production engine decides every payment.", 7.0, "r1_intro")
        await pg.evaluate("document.querySelector('#rt-out').children[2].scrollIntoView({block:'start'}); window.scrollBy(0,-95)")
        await say("It found a blind spot", "Eight payments just under the 50,000 rupee limit, to a gift-card shop, from the victim's own phone: about 2.6 lakh rupees per customer.", 9.0, "r2_found")
        await pg.evaluate("document.querySelector('#rt-out').children[3].scrollIntoView({block:'start'}); window.scrollBy(0,-95)")
        await say("Splitting under the limit is the lever that matters", "Equal parts earn the attacker about 6 thousand. Just-under-limit parts earn about 1.6 lakh.", 7.0, "r3_levers")
        await pg.evaluate("document.querySelector('#rt-out').children[4].scrollIntoView({block:'start'}); window.scrollBy(0,-95)")
        await say("Patch it, then attack again", "Training on what it found cut the attacker's median haul by 86% for 0.4 points more friction. It narrows the hole, it does not close it.", 10.0, "r4_harden")
        await pg.evaluate("window.scrollTo(0,0)")

        # --- policy lab
        await click('.tabs button[data-tab="lab"]')
        await pg.wait_for_timeout(1500)
        await say("Fraud versus friction is a business choice", "Drag risk aversion: stricter catches more fraud but stops more good customers.", 4.5, "9_lab")
        await move("#s-risk")
        await pg.evaluate("const e=document.getElementById('s-risk'); e.value=0.602; e.dispatchEvent(new Event('input'))")
        await pg.wait_for_timeout(600 if PREVIEW else 2500)
        await pg.evaluate("const e=document.getElementById('s-risk'); e.value=-0.602; e.dispatchEvent(new Event('input'))")
        await say("Too strict or too lax both cost money", "Strict stops good customers; lax lets fraud through. The valley in the chart is the best trade.", 5.0)
        await pg.evaluate("const e=document.getElementById('s-risk'); e.value=0; e.dispatchEvent(new Event('input'))")
        await pg.wait_for_timeout(800)
        await say("At the default setting it beats tuned thresholds", "The bar rises with the amount at stake and the payment rail.", 5.0)

        # --- festival drift
        await click('.tabs button[data-tab="live"]')
        await pg.evaluate("fetch('/api/sim',{method:'POST',body:JSON.stringify({spd:900})})")
        await click("#fest")
        await say("Festival surge: traffic stops looking like the training data", "The drift monitor watches the shape of recent payments.", 5.0, "10_fest")
        await pg.wait_for_timeout(500 if PREVIEW else 9000)
        d = await pg.query_selector("#drift")
        await d.scroll_into_view_if_needed()
        await say("Major drift: time to retrain", "That is how you find out before the model quietly gets worse.", 5.0, "11_drift")
        await pg.evaluate("window.scrollTo(0,0)")

        # --- model card, honest
        await click('.tabs button[data-tab="model"]')
        await pg.wait_for_timeout(1000)
        await pg.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior:'instant'})")
        await say("Honest about its limits", "Trained on synthetic data. A plain logistic model scores as well. Scams without a screen-share are the hardest case.", 7.5, "12_limits")
        await pg.evaluate("window.scrollTo(0,0)")
        await say("Fraud Hunter India", "36 tests, one-file demo, Docker and Render ready. github.com/abhishek5228/fraud_hunter_india", 6.0, "13_end")

        if not PREVIEW:
            path = await pg.video.path()
            await ctx.close()
            await b.close()
            out = os.path.join(ROOT, "docs", "demo.mp4")
            tmp = out + ".part.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                            "-movflags", "+faststart", tmp], check=True)
            os.replace(tmp, out)
            print("wrote", out, "%.1f MB" % (os.path.getsize(out) / 1e6))
        else:
            await b.close()


asyncio.run(main())
