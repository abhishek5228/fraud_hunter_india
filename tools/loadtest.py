"""HTTP load test against a running server: real network, JSON, auth, all of it.

    python tools/loadtest.py http://localhost:8000 --n 2000 --workers 16 [--key $FH_API_KEY]

Uses commit=false so it does not teach the engine fake customers. Prints throughput and latency percentiles.
"""
import argparse, json, random, threading, time, urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url"); ap.add_argument("--n", type=int, default=2000); ap.add_argument("--workers", type=int, default=16); ap.add_argument("--key")
    a = ap.parse_args()
    hdr = {"content-type": "application/json", **({"x-api-key": a.key} if a.key else {})}
    lat, err, lock, r = [], [0], threading.Lock(), random.Random(1)
    jobs = [json.dumps(dict(uid="u%04d" % r.randrange(1, 250), mid="shop%d@upi" % r.randrange(50), amt=round(r.lognormvariate(6.5, 1.2), 2),
                            chan=r.choice(["upi", "upi", "ecom", "pos"]), city=r.choice(["Mumbai", "Delhi", "Patna", "Pune"]), commit=False)).encode() for _ in range(a.n)]
    it = iter(jobs)

    def work():
        while True:
            with lock:
                b = next(it, None)
            if b is None:
                return
            t = time.perf_counter()
            try:
                urllib.request.urlopen(urllib.request.Request(a.url.rstrip("/") + "/api/score", b, hdr), timeout=15).read()
                d = (time.perf_counter() - t) * 1000
                with lock:
                    lat.append(d)
            except Exception:
                with lock:
                    err[0] += 1
    t0 = time.perf_counter()
    th = [threading.Thread(target=work) for _ in range(a.workers)]
    [x.start() for x in th]; [x.join() for x in th]
    dt = time.perf_counter() - t0
    lat.sort()
    q = lambda f: lat[min(len(lat) - 1, int(f * len(lat)))] if lat else float("nan")
    print("%d ok, %d errors in %.1fs = %.0f req/s | p50 %.1f ms  p95 %.1f ms  p99 %.1f ms  max %.1f ms" % (len(lat), err[0], dt, len(lat) / dt, q(.5), q(.95), q(.99), lat[-1] if lat else 0))


if __name__ == "__main__":
    main()
