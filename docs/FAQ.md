# FAQ

**Is this real fraud detection?**
It is a real engine running on simulated data. The numbers show the engineering, not real-world performance. Real performance needs a bank's labelled history.

**Why synthetic data?**
Banks do not publish fraud data, and public "UPI fraud" CSVs online are synthetic and often leak the answer. The simulator has eight Indian fraud types and twelve kinds of honest look-alike behaviour, so false alarms have a cost.

**Why not just logistic regression?**
It scores as well here (average precision 0.971 against 0.960). The additive model is shipped because each feature's effect can be inspected and the explanation is exact, not because it is more accurate. Every fit tool prints the logistic baseline next to it.

**Does an OTP step-up stop these scams?**
Often not. A SIM-swapper receives the OTP and a scammed customer approves it. The simulator lets 45 to 60% of those through.

**Can I use my own CSV?**
Yes: `python -m fh.fit data.csv`. It maps columns, removes columns that give the label away, and refuses if there is too little fraud. See README features 36 to 40.

**Is the Razorpay link real money?**
No. It is test mode. Nothing here has touched live money.

**Can it run without a server?**
Open `docs/index.html`. It replays real recorded decisions from disk.

**Where is my data stored?**
In memory, plus a snapshot file and an audit database on the server's disk. Nothing is sent anywhere unless you set a key for an integration (IPinfo, Telegram, Slack, Gemini or Claude).

**What is not done?**
Production hardening (rate limiting on most endpoints, role-based access, horizontal scaling), the FIU-IND report format, and any evidence on real fraud. The README's "Limitations" section is the full list.
