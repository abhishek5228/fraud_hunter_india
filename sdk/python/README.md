# fraudhunter (Python client)

    pip install "git+https://github.com/abhishekisagemai-bot/fraud_hunter#subdirectory=sdk/python"

```python
from fraudhunter import FraudHunter
fh = FraudHunter("https://fraud-hunter-api.onrender.com", api_key="optional")
d = fh.score(uid="u0042", mid="shop@upi", amt=2500, chan="upi", city="Mumbai")
print(d)            # <Decision APPROVE risk=0 reasons=->
if d.decision == "STEP_UP":
    fh.confirm(d.id, passed=True)      # second phase, after your OTP step
print(fh.shield("Your electricity will be cut tonight, call 9876543210")["level"])
```

Standard library only. Retries only GETs and `score(commit=False)`.
