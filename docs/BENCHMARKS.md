# Benchmarks on real public data

Everything else in this repository is measured on a simulator. This page is the part that is **not**: two real, public datasets, with the exact commands to reproduce and the weak results left in.

| Dataset | What it is | Used for |
|---|---|---|
| **ULB / Worldline credit-card fraud** | 284,807 real European card transactions from two days in September 2013, 492 fraud (0.17%). Features are 28 anonymised PCA components, the amount and the time. | Testing the additive model (`fh.fit`, tabular path) |
| **Smishtank** | 1,055 distinct real smishing texts reported by the public (Timko and Rahman, arXiv 2402.18430) | Does Scam Shield catch real scam texts? |
| **UCI SMS Spam Collection** | 5,574 real SMS, 747 spam (Almeida and Hidalgo) | False alarms and spam recall |
| **NUS SMS Corpus** | about 48,000 distinct real everyday SMS, about 7,000 of them sent from India | False alarms on ordinary messages |

**Where I got the copies.** The sandbox this was built in could reach only GitHub, so I used public GitHub mirrors: `KernelBypass/antifraud` for the ULB file (284,807 rows and 492 fraud, matching the published counts) and `Joshoneill6649/smishing-nlp-josh-oneill` for Smishtank, the UCI collection and the NUS corpus. Check them against the original sources before quoting numbers: Kaggle `mlg-ulb/creditcardfraud`, UCI dataset 228, smishtank.com. The data is **not** redistributed here.

## 0. Run it from the console

The **Real data** tab runs all of this without a terminal: it downloads each dataset from its source onto the server (or accepts your own copy as an upload), runs the card-fraud benchmark and the Scam Shield test, and **replays the real card transactions** one by one through the fitted model, showing what the model said and what actually happened. The numbers it produces on the server are the ones in this page (the card-fraud fit is deterministic; Scam Shield uses the same fixed split). Uploads are off unless `FH_API_KEY` or `FH_ALLOW_UPLOADS=1` is set.

## 1. The additive model on real card fraud

```bash
python tools/benchmark_ulb.py creditcard.csv        # about 6 minutes, mostly the random forest
python -m fh.fit creditcard.csv --map label=Class,ts=Time,amt=Amount --mode tabular --max-rows 300000
```

Test set = the **latest 20% of the two days** (56,961 payments, **75 fraud**), trained on the earliest 65%. AP is average precision; intervals are a 300-resample bootstrap of the test set.

| Model | AUC | AP | AP 95% interval | Recall at 1% false alarms | Recall at 0.1% |
|---|---:|---:|---|---:|---:|
| **Additive model (this project)** | 0.980 | 0.760 | 0.667 to 0.840 | 86.7% | 77.3% |
| Logistic regression (this project) | 0.971 | 0.704 | 0.600 to 0.792 | 86.7% | 76.0% |
| Logistic regression (scikit-learn) | 0.973 | 0.706 | 0.609 to 0.792 | 86.7% | 78.7% |
| Random forest (scikit-learn, 200 trees) | 0.941 | 0.792 | 0.705 to 0.870 | 86.7% | 78.7% |
| Gradient boosting (scikit-learn, **untuned defaults**) | 0.769 | 0.475 | 0.360 to 0.592 | 70.7% | 68.0% |

On a **random stratified split** (the way most published numbers are produced, and optimistic because the future leaks into training): additive model AP **0.841** (0.765 to 0.901), logistic 0.783, random forest 0.864 (0.798 to 0.926), untuned boosting 0.461.

**How to read it.**
- On real data the additive model is **competitive, not best**. It beats logistic regression by about 0.05 AP and trails the random forest by about 0.03, but with only 75 fraud in the test set **every one of those gaps is inside the intervals**. Do not quote it as "beats" anything.
- The untuned boosting result is a warning about defaults on 0.17% positives, not a statement about boosting.
- The earlier simulator result that logistic regression ties the additive model does **not** carry over exactly: here the additive model is a little ahead of logistic regression, in line with its learned non-linear shapes helping on real PCA features. With this few fraud, treat that as a lead.
- **This does not test the project's main idea.** ULB has no customer, device or payee identifiers (the features were anonymised with PCA), so the behavioural feature store, the payee graph and the guardrail rules cannot run on it. It tests the **model**, nothing else. No public dataset with customer-level history and Indian payment fraud exists that I could find.

## 2. Scam Shield on real text messages

```bash
python tools/eval_shield.py --smishtank smishtank.csv --uci SMSSpamCollection --nus NUS_SMS_Corpus.json --only test
```

The real messages are split 50/50 by a fixed seed into **DEV** and **TEST**. I changed rules by reading **DEV only**. TEST was never looked at while editing, and it is the half reported below. "Caution" means a warning score of 25 or more, "danger" 60 or more.

| On the TEST half | Before (15 rules) | Now (26 rules, 3 narrowed) |
|---|---:|---:|
| Real smishing flagged (caution or higher), n=528 | **7.8%** | **45.3%** |
| Real smishing rated danger | 0.0% | 6.6% |
| Real SMS spam flagged (UCI), n=321 | 4.0% | 5.6% |
| Ordinary UCI messages falsely flagged, n=2,259 | 0.22% | 0.09% |
| Ordinary NUS messages falsely flagged, n=24,311 | 0.09% | 0.03% |
| &nbsp;&nbsp;of those, sent from India, n=3,487 | 0.09% | 0.06% |
| Ordinary Indian telecom messages falsely flagged, n=664 | not measured | 0.00% |
| Precision on this mix (528 smishing vs 27,234 ordinary) | 60.3% | 96.0% |

The "Now" column was re-measured on 2026-11-02 after the Indian collection (below) was added. Re-running the 26 rules as they stood before that change gives 46.4% smishing, 5.6% UCI spam and 0.04% NUS false alarms, so two cells in the earlier version of this table (UCI spam 4.7%, NUS 0.05%) were slightly off. They are corrected here.

### Real Indian messages (added 2026-11-02)

The **Indian Telecom SMS Spam Collection** (junioralive, MIT licence, 2,063 distinct real messages: 1,327 ordinary and 736 spam) is the only real Indian text collection I could fetch. Two honest limits come first. Its "spam" is almost all **promotion** (Airtel, Vi, Jio, banks selling loans, rummy and shop offers), with only a handful of real scams (for example "part-time job, earn per day" bait). So it cannot measure scam recall. What it can measure is **false alarms on real Indian messages**: bank, telecom and chat.

| On this collection | Before the fix | After the fix |
|---|---:|---:|
| Ordinary messages falsely flagged, all 1,327 | 9 (0.68%) | **0 (0.00%)** |
| Ordinary messages falsely flagged, TEST half only (664) | 4 (0.60%) | 0 (0.00%) |
| Spam flagged at caution or higher, all 736 | not recorded | 301 (40.9%), 2 rated danger |

What the nine false alarms were: eight were friends talking about a **power cut** (matched the electricity-bill rule) or "my account is blocked" (matched the account-locked and KYC rules), and one was "account it blocked for pulse". I narrowed three rules so they need scam wording: the electricity rule now needs a bill, connection, supply or meter; and the account-locked and KYC rules need the message to address "your" or "aapka" account. That cost 6 of 528 smishing messages (46.4% to 45.3%).

**This is not a clean held-out result.** I read the false alarms across the whole file, including the TEST half, before changing the rules, so the 0.00% above is tuned on the data it is measured on. The 41% spam figure is not a scam-detection rate: those messages are promotions, and a "caution" on them means "unwanted offer with a link", not "fraud".

**What the real data taught me (all of it was fixed on DEV):**
1. The first version caught **7.8%** of real smishing. The rules were written for Indian bank and UPI scams (OTP, PIN, screen-share, KYC) and real smishing is mostly parcel fees, "your account is locked", fake refunds, subscription failures and bait messages. I added eleven generic rules for those.
2. Real ordinary texts exposed **false alarms I would not have found by hand**: "you won't" matched the prize rule (`you won`), a friend discussing an `.apk` file, a "KBC" joke, Singlish "ok.lol." read as a web address, and "his mother expired" matched an urgent-threat rule. All fixed, each now has a regression test.
3. DEV recall reached 54.1% and TEST recall is now 45.3%. The gap between the two is the honest cost of tuning on the data you can see.

**What these numbers do not mean.**
- The smishing data is mostly **US and English** (USPS, Netflix, banks). It is real, but not Indian. **I could not reach a labelled corpus of real Indian bank-scam messages.** The one real Indian collection I found (above) is promotions and chat, with almost no scams. The Indian-specific rules (electricity bills, KYC, digital arrest, UPI handles) are therefore **not validated on real Indian scam texts**. They are validated only against real Indian ordinary texts (0.06% false alarms on 3,487).
- **More than half of real smishing is still missed**, for example link-only messages, "wrong number" openers and dating baits with no keyword.
- **Precision depends on how common scams are.** 94.6% is for a mix of about 2% smishing. If 1 text in 1,000 were smishing, the same rates would give roughly 48% precision, so a warning would be right about half the time. That is still a reasonable warning for a "pause and check" nudge, and a poor one for blocking.
- Spam is a different thing from smishing. The rules are not trying to catch promotional spam, and they catch few.

## 3. Browser and server agree

The browser and the server read the same `fh/shield_rules.json`. A test (`tests/test_shield_parity.py`) runs the browser implementation in Node and the server's in Python on every fixture text, and a one-off run over 9,629 real messages and all 26 rules found **0 disagreements**.
