# Contributing

Thanks for looking. This is a small project with a few strong opinions, listed below so your change does not fight them.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m fh.train                       # about 35 seconds; writes artifacts/
python -m pytest -q tests                # 95 tests, about a minute
python -m uvicorn fh.api:app --port 8000 # http://localhost:8000
```

## Ground rules

1. **No real payment data, ever.** Everything here is synthetic. Do not add a real customer's phone number, UPI ID, account number or card number, even in a test or a screenshot.
2. **No secrets in git.** Keys and tokens come from environment variables (see `.env.example`). `.env` is git-ignored; keep it that way.
3. **Rules can only escalate.** A guardrail in `fh/rules.py` may turn an approve into a step-up or a decline. It must never turn a decline into an approve.
4. **Features see state before the payment.** Anything computed in `fh/feat.py` must come from state *before* the payment is committed. A test enforces this; keep it green.
5. **Say what you did not test.** If you could only test against a fake (a payment API, an LLM), say so in the pull request and in the docs.
6. **Report the bad numbers too.** If a change makes accuracy or friction worse somewhere, show it in the pull request. Hiding it is the one thing that is not allowed.

## Changing the web console

`web/` has no build step. After changing it, rebuild the backend-free demo with `make demo` (it runs the whole sequence and fails if the Playground scenarios are missing). Do not run `tools/build_demo.py` on its own.

## Commits

One commit, one real change, with a message that says what changed and why: `Add private set intersection`, `Fix velocity ignoring declined attempts`. No empty commits, and no splitting one change into many to make a history look busy.

## Pull requests

Include: what changed, why, how you tested it (the command), and anything you could not test. Add or update a test for any behaviour you change.
