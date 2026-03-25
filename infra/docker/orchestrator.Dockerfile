FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0 httpx==0.28.1 redis==5.2.1

# Orchestrateur minimal — sera étendu avec LangChain + Ollama
COPY infra/docker/orchestrator_main.py ./main.py

EXPOSE 8020

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]
