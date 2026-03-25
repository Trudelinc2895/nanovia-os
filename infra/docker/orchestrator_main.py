from fastapi import FastAPI
from pydantic import BaseModel
import os, httpx

app = FastAPI(title="KT AI Orchestrator", version="0.1.0")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")

@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-orchestrator", "version": "0.1.0"}

@app.get("/")
def root():
    return {"service": "KT AI Orchestrator", "status": "running"}

class ChatRequest(BaseModel):
    prompt: str
    model: str = "llama3"

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": req.model, "prompt": req.prompt, "stream": False}
            )
            return {"response": resp.json().get("response", ""), "model": req.model}
    except Exception as e:
        return {"error": str(e), "fallback": "Ollama non disponible"}
