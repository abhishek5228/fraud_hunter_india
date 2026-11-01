.PHONY: setup train run test site demo lint clean links
setup:  ; pip install -r requirements.txt
train:  ; python -m fh.train
run:    ; uvicorn fh.api:app --port 8000 --workers 1
test:   ; python -m pytest -q tests
site:   ; python tools/build_site.py --api $(API)          # make site API=https://your-backend.example.com
demo:  ; bash tools/rebuild_demo.sh
lint:  ; ruff check .
clean: ; rm -rf .pytest_cache dist && find . -name __pycache__ -type d -prune -exec rm -rf {} +
links: ; python tools/check_readme_links.py README.md README.hi.md
