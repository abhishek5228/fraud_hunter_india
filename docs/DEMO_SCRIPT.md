# Demo script (about 3 minutes)

Say it plainly and slowly. Each beat has what to do and what to say. Every claim here is in the README or on screen.
Open the live site if it is awake, otherwise the demo link. Both look the same.

## 0:00 The problem (25 s)
Say: "In India most payment fraud now is the customer being talked into paying. A caller, a QR code, a fake refund. The OTP step does not help, because the customer approves it themselves. And the money lands in mule accounts that the bank has to spot from the other side."
Do: stay on **Live ops**. Point at the feed.
Say: "This is Fraud Hunter India. It scores every UPI, IMPS and card payment as it arrives and picks approve, step-up or decline. All the data you see is simulated; I will come back to that."

## 0:25 One attack, end to end (70 s)
Do: **Launch attack > SIM-swap drain**. Click **Challenged or declined**. Open a red **Decline**.
Say: "A fraudster ported the victim's number, bound UPI on a new phone, and is sending near-limit amounts to a stranger."
Do: point at **Why this score**.
Say: "Every bar is the model's own arithmetic. Red raises risk, green lowers it. New device, first payment to this payee, a person rather than a merchant. It is an additive model, so there is no separate explainer that could disagree with it."
Do: point at the **decision ruler**.
Say: "The bar for stepping up or declining depends on how much money is at stake, and on the rail. A hundred rupees and fifty thousand rupees are not treated the same."
Do: scroll to **What the customer sees**, tap **हिन्दी**.
Say: "And the customer gets plain words in Hindi or English, with the 1930 helpline."

## 1:35 What happens next (25 s)
Do: **Review** tab. Open a case, click **Confirm fraud**.
Say: "Analysts confirm or clear what was stopped. Their answer feeds the engine and goes into an audit log with the model version."

## 2:00 Proving it on your data (40 s)
Do: **Backtest** tab. Click **Try the 45-day sample**.
Say: "This is the practical part. A company uploads a CSV of its past payments and sees what this engine would have done. On this sample: 99% of fraud stopped, 3.8% of good customers touched, a cost of about 97 thousand rupees against 1.04 crore for approving everything."
Do: point at **Why payments were flagged**.
Say: "And it shows where it is wrong. Payee fan-in flagged 377 payments and none were fraud. IMPS transfers touch one good customer in five."

## 2:40 Honest close (30 s)
Do: **Model card**, scroll to the limits.
Say: "Everything is synthetic, because real bank data is not public. A plain logistic model scores as well as mine on this data, and the README says so. The weak spot is scams where nothing technical looks odd. The next step is to replace the simulator with real complaint data and add scam-specific friction: first-payee warnings and cooling-off periods."
Do: end on the README / GitHub page.

## If asked
| Question | Answer |
|---|---|
| Why synthetic data? | Bank data is not public. I built a simulator with the Indian fraud types and with legitimate look-alikes (travellers, VPN users, shared kiosk phones) so false alarms are a real cost. I also found and fixed leakage-style bugs along the way; they are in the README. |
| Why not just logistic regression? | It scores as well here. I ship the additive model because each factor's contribution is exact and the shape of every feature can be inspected. Interaction terms are the next step. |
| Does step-up (OTP) stop these scams? | Often not. A SIM-swapper receives the OTP and a scammed customer approves it. The simulator lets 45 to 60% of those through, and the README says so. |
| How would it scale? | State lives in memory, so run one instance, or partition by customer id, or move the store to Redis. See DEPLOY.md. |
| Is it safe for real money? | Not yet. It has an API key, an audit log and a review queue, but it is trained on synthetic data and has no rate limiting or role-based access. DEPLOY.md lists the gaps. |
| Data protection? | The engine needs device ids, IPs and payee ids. On real data that is personal data and needs a lawful basis, retention limits and access control. |

## Numbers you can quote
Held-out 12 days, 53,789 simulated payments, 908 fraud: AUC 0.9987, average precision 0.960, 98.6% of fraud caught, 2.7% of good customers touched, cost 1.34 lakh rupees against 1.66 lakh for the best tuned two-step thresholds. About 12,700 decisions per second on one Python thread. Backtest on the 45-day sample: 99.0% caught, 3.8% touched, 0.22% of good customers declined.
