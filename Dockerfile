FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN mkdir -p /data && rm -rf /app/data && ln -s /data /app/data

ENV PORT=8080
CMD gunicorn -w 1 -k gthread --threads 4 --timeout 300 -b 0.0.0.0:${PORT} firecan_main:app
