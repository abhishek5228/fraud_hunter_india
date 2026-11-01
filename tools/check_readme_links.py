"""Check that every local file and every in-page anchor linked from the README exists.

    python tools/check_readme_links.py [README.md ...]

Exits 1 and lists the problems if anything is broken. Only local links are checked (no network).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slug(h):
    h = re.sub(r"<[^>]+>", "", h).strip().lower()
    return re.sub(r"[^\w\- ]", "", h).replace(" ", "-")


def check(path):
    text = open(os.path.join(ROOT, path), encoding="utf-8").read()
    problems = []
    for a, b in re.findall(r'\]\(([^)\s]+)\)|src="([^"]+)"', text):
        p = a or b
        if p and not p.startswith(("http", "#", "mailto:")) and not os.path.exists(os.path.join(ROOT, p.split("#")[0])):
            problems.append("%s: missing file %s" % (path, p))
    heads = {slug(m) for m in re.findall(r"^#{1,4} (.+)$", text, re.M)}
    for a in re.findall(r"\]\(#([^)]+)\)", text):
        if a not in heads:
            problems.append("%s: broken anchor #%s" % (path, a))
    return problems


if __name__ == "__main__":
    bad = [p for f in (sys.argv[1:] or ["README.md"]) for p in check(f)]
    print("\n".join(bad) if bad else "all local links and anchors resolve")
    sys.exit(1 if bad else 0)
