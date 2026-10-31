FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Bake the model and the warmed feature store into the image so the container starts in seconds.
RUN python -m fh.train
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health')" || exit 1
# ONE worker on purpose: the feature store lives in this process's memory (see DEPLOY.md for scaling).
CMD ["sh", "-c", "uvicorn fh.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
