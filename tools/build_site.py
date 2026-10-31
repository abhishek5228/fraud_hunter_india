"""Build deployable frontends from web/.

    python tools/build_site.py --api https://my-backend.onrender.com   -> dist/site        (live mode, talks to your API)
    python tools/build_site.py --demo                                  -> dist/demo-site   (no backend, recorded real output)
                                                                           dist/fraud-hunter-demo.html (one self-contained file)
Both folders are plain static files: drag them onto Netlify, push to GitHub Pages, or serve with any web server.
"""
import argparse
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB, DIST = os.path.join(ROOT, "web"), os.path.join(ROOT, "dist")


def copy_site(out, api, demo):
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "static"))
    for f in os.listdir(WEB):
        if f == "index.html":
            continue
        if f == "demo.js" and not demo:
            continue
        shutil.copy(os.path.join(WEB, f), os.path.join(out, "static", f))
    with open(os.path.join(out, "static", "config.js"), "w") as fh:
        fh.write('window.FH_API = %s;\n' % json.dumps(api or ""))
        if demo:
            fh.write("window.FH_DEMO = true;\n")
    html = open(os.path.join(WEB, "index.html")).read()
    if demo:
        html = html.replace('<script src="static/lib.js"></script>', '<script src="static/demo.js"></script>\n<script src="static/lib.js"></script>')
        shutil.copy(os.path.join(DIST, "demo-data.json"), os.path.join(out, "demo-data.json"))
    open(os.path.join(out, "index.html"), "w").write(html)
    return html


def single_file(site, out):
    """Inline css, scripts and recorded data into one HTML file (for artifacts, email, or an offline demo)."""
    html = open(os.path.join(site, "index.html")).read()
    css = open(os.path.join(site, "static", "style.css")).read()
    html = html.replace('<link rel="stylesheet" href="static/style.css">', "<style>\n%s\n</style>" % css)
    data = open(os.path.join(site, "demo-data.json")).read().replace("</", "<\\/")
    html = html.replace("</head>", '<script type="application/json" id="demo-data">%s</script>\n</head>' % data)
    def inline(m):
        src = open(os.path.join(site, m.group(1))).read().replace("</script", "<\\/script")
        return "<script>\n%s\n</script>" % src
    html = re.sub(r'<script src="(static/[^"]+)"></script>', inline, html)
    open(out, "w").write(html)
    return len(html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="", help="backend URL for live mode")
    ap.add_argument("--demo", action="store_true", help="backend-free demo using recorded data")
    a = ap.parse_args()
    os.makedirs(DIST, exist_ok=True)
    if a.demo:
        copy_site(os.path.join(DIST, "demo-site"), "", True)
        n = single_file(os.path.join(DIST, "demo-site"), os.path.join(DIST, "fraud-hunter-demo.html"))
        print("dist/demo-site  +  dist/fraud-hunter-demo.html (%.1f MB)" % (n / 1e6))
    else:
        copy_site(os.path.join(DIST, "site"), a.api, False)
        print("dist/site  (API = %r)" % a.api)
