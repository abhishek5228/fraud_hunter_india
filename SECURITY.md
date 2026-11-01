# Security

## Reporting a problem

Please do **not** open a public issue for a security problem. Email the maintainer (see the profile on GitHub) with what you found and how to reproduce it. Expect a reply within a few days.

## What this project is

A demonstration risk engine running on **synthetic data**. It has an API key option, an audit log and signed webhooks, but it has not had a security review and is **not ready for real money**. The README lists what is missing (rate limiting on most endpoints, role-based access, horizontal scaling).

## Handling secrets

- Keys and tokens live in environment variables only (`.env.example` lists them). Never commit a `.env`.
- If you paste a key into a chat, a screenshot or a commit by mistake, **revoke it and make a new one**; deleting the message is not enough.
- The private-set-intersection secret is generated into `artifacts/psi.key` (mode 0600) if you do not set `FH_PSI_SECRET`. That file is git-ignored.

## Known limits worth knowing

- Private set intersection here is not audited cryptography, and a malicious member can still probe guessed identifiers (the budget raises the cost only).
- Free-tier AI keys may let the provider use inputs; keep real customer data out.
- The Razorpay webhook is authenticated by its HMAC signature, not by `X-API-Key`.
