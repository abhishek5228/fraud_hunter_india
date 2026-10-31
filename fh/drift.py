"""Population stability (PSI) of recent traffic against the training reference, per feature."""
import numpy as np

SKIP = ("hrar",)   # hour-rarity swings with time of day by construction; a few-hour window would always look drifted


def psi(vecs, g, rep, desc=None):
    """vecs: recent feature vectors. Subtracts the PSI that pure sampling noise would produce."""
    desc = desc or {}
    X = np.asarray(vecs)
    out = []
    for j, n in enumerate(g.names):
        if n in SKIP:
            continue
        live = np.bincount(np.searchsorted(g.edges[j], X[:, j], side="right"), minlength=g.nb[j]) / len(X)
        e, a = np.clip(np.array(rep["ref"][n]), 1e-4, None), np.clip(live, 1e-4, None)
        raw = float(np.sum((a - e) * np.log(a / e)))
        floor = (g.nb[j] - 1) * (1 / len(X) + 1 / rep["ref_n"])
        out.append(dict(f=n, psi=max(0.0, raw - floor), raw=raw, desc=desc.get(n, "")))
    out.sort(key=lambda r: -r["psi"])
    worst = out[0]["psi"]
    return dict(n=len(X), ready=True, feats=out, worst=worst, status="major" if worst > 0.25 else "moderate" if worst > 0.1 else "stable")
