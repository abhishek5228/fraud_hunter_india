"""Film a full tour of the console, with captions at the bottom of the screen -> docs/demo.mp4 (about 6 minutes)

It films the FULL backend, not the static demo, so the Real data tab, Scam Shield, the real-card replay, the mule graph and the
Razorpay path all work. Start a server with the real files first (the Real data tab fetches them, or put them in FH_DATA_DIR):

    FH_STATE=0 FH_DATA_DIR=/tmp/vdata uvicorn fh.api:app --port 8020
    FH_URL=http://localhost:8020 python tools/make_video.py preview     # screenshots of each scene, to check the look
    FH_URL=http://localhost:8020 python tools/make_video.py             # record and encode

Needs playwright and ffmpeg. Nothing in the video is spoken; every explanation is the caption."""
import asyncio
import os
import shutil
import subprocess
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.environ.get("FH_URL", "http://localhost:8020").rstrip("/") + "/"
W, H = 1440, 810
PREVIEW = len(sys.argv) > 1 and sys.argv[1] == "preview"

JS = """
window.cap = (t, sub) => { let d = document.getElementById('vcap'); if (!d) { d = document.createElement('div'); d.id = 'vcap';
  d.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);width:max-content;max-width:1180px;background:rgba(13,26,45,.95);color:#fff;padding:12px 22px;border-radius:12px;font:600 21px/1.35 Inter,system-ui,sans-serif;z-index:99999;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.35)';
  document.body.append(d); } d.innerHTML = t + (sub ? '<div style="font:400 15px/1.4 Inter,system-ui,sans-serif;color:#b9c6dc;margin-top:4px">' + sub + '</div>' : ''); d.style.display = t ? 'block' : 'none'; };
window.addEventListener('DOMContentLoaded', () => { const c = document.createElement('div'); c.style.cssText = 'position:fixed;width:18px;height:18px;border-radius:50%;background:rgba(43,71,255,.55);border:2px solid #fff;z-index:99998;pointer-events:none;left:-30px;top:-30px';
  document.body.append(c); document.addEventListener('mousemove', e => { c.style.left = e.clientX - 9 + 'px'; c.style.top = e.clientY - 9 + 'px'; }); });
"""

ASHA = "Dear customer, your electricity connection will be disconnected tonight 9:30 PM because last month bill is not updated. Call 9876543210 immediately."


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        vd = "/tmp/vid"
        shutil.rmtree(vd, ignore_errors=True)
        os.makedirs("/tmp/shots", exist_ok=True)
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=None if PREVIEW else vd, record_video_size={"width": W, "height": H})
        await ctx.add_init_script(JS)
        pg = await ctx.new_page()

        async def say(t, sub="", sec=4.0, shot=None):
            await pg.evaluate("([t,s]) => window.cap(t,s)", [t, sub])
            if PREVIEW and shot:
                await pg.screenshot(path="/tmp/shots/v_%s.png" % shot)
            await pg.wait_for_timeout(250 if PREVIEW else int(sec * 1000))

        async def move(sel):
            el = pg.locator(sel).first
            await el.scroll_into_view_if_needed()
            bb = await el.bounding_box()
            await pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, steps=12)

        async def click(sel):
            if sel.startswith(".tabs"):
                await pg.evaluate("window.cap('')")      # never leave a caption about one screen over another
            await move(sel)
            await pg.wait_for_timeout(150 if PREVIEW else 400)
            await pg.locator(sel).first.click()

        async def top():
            await pg.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")

        async def tab(name):
            await click('.tabs button[data-tab="%s"]' % name)
            await pg.wait_for_timeout(600 if PREVIEW else 1500)
            await top()

        async def wait_for(sel, ms=240000):
            await pg.wait_for_selector(sel, timeout=ms)

        await pg.goto(URL)
        await pg.wait_for_timeout(5000 if not PREVIEW else 3000)

        # ---------------------------------------------------------------- 1. the problem and the live console
        await say("Fraud Hunter India", "A real-time risk engine for Indian digital payments: UPI, IMPS, card and ATM.", 5.5, "01_intro")
        await say("Most fraud in India now is the customer being talked into paying", "A fake officer, a QR code, a refund trick. The customer approves it themselves, so an OTP does not help.", 8.0)
        await say("So every payment gets one of three answers", "Approve, step-up (ask for more proof) or decline, in about a millisecond, with the reasons attached.", 6.5, "02_feed")
        await say("This feed is SIMULATED", "There is no public stream of real Indian payments. The provenance strip says so on every tab. Real data comes later in this video.", 7.0)

        # ---------------------------------------------------------------- 2. one attack end to end
        await click("#atkb")
        await say("Launch a SIM-swap attack", "The fraudster ports the victim's number, binds UPI on a new phone and drains the account.", 4.5, "03_menu")
        await click('#atkp button[data-k="sim_swap"]')
        await pg.wait_for_timeout(500 if PREVIEW else 8000)
        await click('.chip[data-f="flag"]')
        rows = await pg.query_selector_all("#feed .row")
        pick = None
        for r in rows:
            t = await r.inner_text()
            if "Decline" in t and ("SIM" in t or "MULE" in t):
                pick = r
                break
        pick = pick or (rows[0] if rows else None)
        if pick:
            bb = await pick.bounding_box()
            await pg.mouse.move(bb["x"] + 120, bb["y"] + 18, steps=14)
            await pick.click()
        await say("The engine stopped it", "Click any payment to see exactly why it was scored the way it was.", 4.5, "04_case")
        await pg.evaluate("document.querySelector('#insp').scrollIntoView({behavior:'instant', block:'start'}); window.scrollBy(0,-70)")
        await say("Why this score", "Every bar is the model's own arithmetic: red raises the risk, green lowers it. A new device, a first payment to this payee, a person instead of a shop.", 8.0, "05_why")
        await pg.evaluate("document.querySelector('#insp .wf').scrollIntoView({behavior:'smooth', block:'center'})")
        await pg.wait_for_timeout(500 if PREVIEW else 2500)
        await say("The bar for stepping up moves with the amount", "Cheap payments are approved at risks that would stop a large one. The decision is the lowest expected cost, not a fixed cutoff.", 7.5)
        try:
            await pg.evaluate("document.querySelector('#insp .phone').scrollIntoView({behavior:'instant', block:'center'})")
            await say("And the customer sees plain words", "With the 1930 helpline. Tap Hindi:", 3.5)
            await click("#insp .phone >> xpath=../div[contains(@class,'chips')]/button[2]")
            await say("Hindi and English, same message", "Never share your PIN or OTP. Report it on cybercrime.gov.in.", 5.0, "06_hindi")
        except Exception:
            pass
        await top()

        # ---------------------------------------------------------------- 3. analyst review
        await tab("review")
        rows = await pg.query_selector_all("#rlist .row")
        if rows:
            bb = await rows[0].bounding_box()
            await pg.mouse.move(bb["x"] + 120, bb["y"] + 18, steps=10)
            await rows[0].click()
            await pg.wait_for_timeout(800)
        await say("Analysts review what was stopped", "Their answer feeds the engine and is written to an audit log with the model version.", 5.0, "07_review")
        if await pg.query_selector("#rinsp .btn.bad"):
            await click("#rinsp .btn.bad")
        await say("Confirm fraud: the payee and device are remembered", "Wrongly blocked? Mark it legitimate and the engine learns that too.", 4.5)

        # ---------------------------------------------------------------- 4. real data
        await tab("real")
        await say("Now real data", "Everything on this tab uses public research datasets, not the simulator. The server downloads each from its source and checks the counts.", 7.5, "08_real")
        await say("284,807 real card payments, 492 of them fraud", "ULB / Worldline, two days in September 2013. Smishing texts, UCI spam and about 2,000 real Indian SMS sit beside it.", 7.5)
        await click("#rd-ulb .btn.pri")
        await say("Fit the model on the real card data", "The earliest 65% of the file trains the additive model; the latest 20% is the test it has never seen.", 6.0, "09_fit")
        await wait_for("#rd-ulb table", 300000)
        await pg.evaluate("document.querySelector('#rd-ulb').scrollIntoView({behavior:'instant', block:'start'}); window.scrollBy(0,-70)")
        await say("AUC 0.980 on real fraud, with honest intervals", "Only 75 fraud cases in the test set, so the intervals are wide, and the gaps between models sit inside them. The caption under the table says so.", 9.5, "10_ulb")
        await click("#rd-shield .btn.pri")
        await wait_for("#rd-shield table", 300000)
        await pg.evaluate("document.querySelector('#rd-shield').scrollIntoView({behavior:'instant', block:'start'}); window.scrollBy(0,-70)")
        await say("Scam Shield on real text messages", "About 64% of real smishing is flagged on a held-out half, while about 0.04% of ordinary messages (none of 664 real Indian ones) are. It started at 7.8%.", 10.0, "11_shield_bench")
        await say("It still misses a good part", "Mostly US data, wording it has not seen is caught less, and the Indian bank-scam rules are not validated on real Indian scams. All of that is in the README.", 8.0)

        # ---------------------------------------------------------------- 5. live ops on real card data
        await tab("live")
        await click('#srcbar button[data-src="real"]')
        await pg.wait_for_timeout(1500 if PREVIEW else 5000)
        await say("Live ops, now on real card data", "Real transactions in time order, scored one at a time. Each row shows what the model said and what really happened.", 8.0, "12_realfeed")
        try:
            await click('#real-live button:has-text("Jump to the next real fraud")')
            await pg.wait_for_timeout(500 if PREVIEW else 3500)
        except Exception:
            pass
        await say("A real fraud, and whether the model flagged it", "The counters count real fraud caught and missed, and the genuine payments it flagged by mistake.", 7.5, "13_realfraud")
        await click('#srcbar button[data-src="sim"]')
        await pg.wait_for_timeout(1000)

        # ---------------------------------------------------------------- 6. scam shield
        await tab("shield")
        await say("Scam Shield: check before you pay", "Everything so far protects the bank. Asha needed to check the SMS before she called the number.", 6.5, "14_shield")
        await pg.fill("#sh-text", ASHA)
        await say("Asha's SMS", "A bill-disconnection threat with a number to call. One of the most common scams in India.", 5.0)
        await click("#sh-go")
        await pg.wait_for_timeout(700 if PREVIEW else 1500)
        await say("Danger: do not pay", "It names the pattern in English and Hindi and says what to do instead. It never says 'safe', only 'no known scam pattern', because wording cannot prove a payee is honest.", 9.0, "15_verdict")
        try:
            await click("#sh-real button >> nth=0")
            await click("#sh-go")
            await pg.wait_for_timeout(700 if PREVIEW else 1500)
            await say("Try a real message from the public datasets", "The label is shown with it, so you can see when it is right and when it misses.", 6.0, "16_realmsg")
        except Exception:
            pass

        # ---------------------------------------------------------------- 7. mule graph
        await tab("live")
        await click("#atkb")
        await click('#atkp button[data-k="upi_scam"]')
        await pg.wait_for_timeout(500 if PREVIEW else 9000)
        await tab("mules")
        await say("Mule graph: the accounts that collect stolen money", "A mule payee is one that many unrelated customers paid for the first time this week, often with devices in common.", 8.0, "17_mules")
        try:
            await click("#mu-list .hub >> nth=0")
            await pg.wait_for_timeout(500 if PREVIEW else 1200)
            await say("Four kinds of evidence give a confidence score", "Fan-in, first-time senders, shared devices and complaints. Mark a hub mule or legitimate: a legitimate shop is exempted so it is not flagged again.", 8.5, "18_hub")
        except Exception:
            pass

        # ---------------------------------------------------------------- 8. razorpay
        await tab("wire")
        await say("Live wire: real Razorpay test-mode events", "A signed webhook goes through the same engine as everything else. Signatures are checked; the amount is converted from paise.", 8.0, "19_wire")
        await pg.fill("#w-amt", "2500000")
        await click("#w-send")
        await pg.wait_for_timeout(600 if PREVIEW else 2500)
        await say("A 25 lakh payment from a stranger: not approved", "It is above the UPI limit of 10 lakh, and a new customer sending a very large sum is escalated. It was approved before I found that and added the rules.", 9.0, "20_big")
        await click("#w-load")
        await pg.wait_for_timeout(1500 if PREVIEW else 9000)
        await say("Speed", "The load test fires payments through the whole path and shows the measured latency and throughput on this server.", 6.0, "21_load")

        # ---------------------------------------------------------------- 9. backtest, red team, policy
        await tab("backtest")
        await click("#bt-sample")
        await wait_for("#bt-out .kpi", 120000)
        await say("Try it on your own history", "Upload a CSV of past payments and see what this engine would have caught, what it would have cost good customers, and where it is wrong.", 8.0, "22_backtest")
        await pg.evaluate("window.scrollTo({top: 330, behavior:'instant'})")
        await say("It shows its weak spots too", "Payee fan-in flagged many payments that were all good, and IMPS touched one good customer in five.", 7.0)
        await top()

        await tab("redteam")
        await click("#rt-run")
        await wait_for("#rt-out .kpi", 180000)
        await say("Now the engine attacks itself", "An automated fraudster tries hundreds of strategies against real customer histories and keeps whatever earns the most.", 8.0, "23_rt")
        await pg.evaluate("document.querySelector('#rt-out').children[2].scrollIntoView({block:'start'}); window.scrollBy(0,-95)")
        await say("It found a blind spot", "Payments just under the limit, to a gift-card shop, from the victim's own phone. Then I train on what it found and attack again: smaller, not closed.", 9.5, "24_found")
        await top()

        await tab("lab")
        await say("Fraud versus friction is a business choice", "Drag risk aversion: stricter catches more fraud and stops more good customers. The valley in the chart is the best trade.", 7.5, "25_lab")
        await move("#s-risk")
        await pg.evaluate("const e=document.getElementById('s-risk'); e.value=0.602; e.dispatchEvent(new Event('input'))")
        await pg.wait_for_timeout(500 if PREVIEW else 2500)
        await pg.evaluate("const e=document.getElementById('s-risk'); e.value=0; e.dispatchEvent(new Event('input'))")
        await pg.wait_for_timeout(500 if PREVIEW else 1500)

        # ---------------------------------------------------------------- 10. honest close
        await tab("model")
        await pg.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior:'instant'})")
        await say("Honest about its limits", "The payments are synthetic, a plain logistic model scores almost as well, and scams with no technical trace are the hardest case.", 9.0, "26_limits")
        await top()
        await tab("live")
        await say("Ready for a real system, carefully", "Shadow mode scores every payment but always answers approve and records what it would have done, so it can run beside a real system before it blocks anything.", 9.5, "27_shadow")
        await say("Fraud Hunter India", "154 tests, real-data benchmarks, public repo: github.com/antrikakashyap/fraud_hunter", 7.0, "28_end")

        if not PREVIEW:
            path = await pg.video.path()
            await ctx.close()
            await b.close()
            out = os.path.join(ROOT, "docs", "demo.mp4")
            tmp = out + ".part.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                            "-movflags", "+faststart", tmp], check=True)
            os.replace(tmp, out)
            print("wrote", out, "%.1f MB" % (os.path.getsize(out) / 1e6))
        else:
            await b.close()


asyncio.run(main())
