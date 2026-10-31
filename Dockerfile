FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m fh.train          # bake model + warmed feature store into the image
EXPOSE 8000
CMD ["uvicorn", "fh.api:app", "--host", "0.0.0.0", "--port", "8000"]
