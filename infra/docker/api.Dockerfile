FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -qq && apt-get install -y -qq libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8010

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "2"]
