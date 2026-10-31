.PHONY: setup train run test site demo
setup:  ; pip install -r requirements.txt
train:  ; python -m fh.train
run:    ; uvicorn fh.api:app --port 8000 --workers 1
test:   ; python -m pytest -q tests
site:   ; python tools/build_site.py --api $(API)          # make site API=https://your-backend.example.com
demo:  ; bash tools/rebuild_demo.sh
