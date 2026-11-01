#!/usr/bin/env bash
# Send a correctly signed Razorpay-style webhook to a running server.
#   RAZORPAY_WEBHOOK_SECRET=your-secret bash examples/webhook_curl.sh [http://localhost:8000] [amount_in_rupees]
set -euo pipefail
URL="${1:-${FH_URL:-http://localhost:8000}}"
RUPEES="${2:-45000}"
SECRET="${RAZORPAY_WEBHOOK_SECRET:?set RAZORPAY_WEBHOOK_SECRET to the same value the server uses}"
PAISE=$((RUPEES * 100))                                   # Razorpay amounts are in paise
BODY=$(printf '{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_example","amount":%s,"currency":"INR","method":"upi","status":"captured","contact":"+919800000000","created_at":%s,"notes":{"city":"Patna"}}}}}' "$PAISE" "$(date +%s)")
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -sS -X POST "$URL/api/webhook/razorpay" -H "X-Razorpay-Signature: $SIG" -H 'content-type: application/json' -d "$BODY"
echo
