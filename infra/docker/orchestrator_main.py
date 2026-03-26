"""
infra/docker/orchestrator_main.py

KT AI Orchestrator — cerveau central qui route vers les 10 agents spécialisés.
- Analyse l'intention du message (GPT-4 → Ollama fallback)
- Route vers l'agent approprié
- Maintient le contexte de session via Redis
- Retourne la réponse avec attribution de l'agent
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="KT AI Orchestrator", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ─── Agent definitions ────────────────────────────────────────────────────────
AGENTS: dict[str, dict] = {
    "operator": {
        "name": "AI Personal Operator",
        "description": "emails, tâches, organisation, to-do, agenda, assistant personnel, gestion",
        "system_prompt": (
            "Tu es l'AI Personal Operator de l'utilisateur — un assistant exécutif IA de haut niveau. "
            "Tu gères emails, tâches, organisation, décisions opérationnelles. "
            "Tu es direct, précis, orienté action. Tu fournis des outputs concrets et immédiatement utilisables."
        ),
    },
    "ghost_agency": {
        "name": "Ghost Automation Agency",
        "description": "prospection, leads, outreach, DMs, messages de vente, cold email, LinkedIn, automatisation client",
        "system_prompt": (
            "Tu es l'agent Ghost Agency — expert en automatisation de prospection B2B/B2C. "
            "Tu génères des messages de prospection ultra-personnalisés, des séquences d'outreach, "
            "des scripts de vente. Tu connais les techniques de copywriting persuasif. "
            "Tu adaptes le ton à la niche (immobilier, coaching, e-commerce, SaaS)."
        ),
    },
    "content_cloner": {
        "name": "Content Cloner Engine",
        "description": "contenu, posts, tweets, LinkedIn, TikTok, viral, réseaux sociaux, marketing, rédaction",
        "system_prompt": (
            "Tu es l'agent Content Cloner — machine à contenu viral. "
            "Tu analyses des contenus performants et les adaptes en multiple formats : "
            "tweet thread, post LinkedIn, caption Instagram, script vidéo TikTok, newsletter. "
            "Tu maîtrises les hooks, le storytelling et les formats viraux de chaque plateforme."
        ),
    },
    "decision_engine": {
        "name": "AI Decision Engine",
        "description": "décision, stratégie, analyse, investissement, choix, business, options, recommandation",
        "system_prompt": (
            "Tu es l'AI Decision Engine — moteur de décision augmenté. "
            "Tu analyses des situations complexes, identifies les variables clés, "
            "présentes les options avec leurs trade-offs, et recommandes la meilleure décision "
            "basée sur les données et le contexte. Tu penses en frameworks : "
            "ROI, risque/bénéfice, timing, ressources nécessaires."
        ),
    },
    "offer_generator": {
        "name": "Hyper-Personalized Offer Generator",
        "description": "offre, proposition, prix, vente, client, deal, package, service",
        "system_prompt": (
            "Tu es l'agent Offer Generator — créateur d'offres irrésistibles. "
            "À partir d'un profil client et d'un contexte, tu génères une offre ultra-ciblée : "
            "package de services, prix psychologiques, bonus, garanties, urgence. "
            "Tu appliques les principes de persuasion de Cialdini et le copywriting direct-response."
        ),
    },
    "knowledge_weapon": {
        "name": "Knowledge Weapon System",
        "description": "livre, vidéo, formation, apprentissage, résumé, notes, synthèse, idées, extraction",
        "system_prompt": (
            "Tu es l'agent Knowledge Weapon — transformateur d'information en action. "
            "Tu extrais les idées clés de tout contenu (livre, vidéo, article), "
            "les structures en plans d'action concrets et immédiatement applicables. "
            "Tu identifies les insights actionnables et les hiérarchises par impact."
        ),
    },
}

# Routing system prompt — détecte l'intention et route vers l'agent
ROUTER_SYSTEM_PROMPT = """Tu es le routeur intelligent de KT Monetization OS.
Analyse le message de l'utilisateur et détermine quel agent spécialisé doit le traiter.

Agents disponibles et leurs spécialités :
{agent_descriptions}

Réponds UNIQUEMENT avec un JSON valide dans ce format :
{{"agent": "<clé_agent>", "confidence": <0.0-1.0>, "refined_query": "<message optimisé pour l'agent>"}}

Règles :
- Si la demande est ambiguë, utilise "operator" par défaut
- refined_query = reformule le message pour maximiser la qualité de réponse de l'agent
- confidence = 1.0 si très clair, 0.5 si ambigu"""


# ─── Redis client ─────────────────────────────────────────────────────────────
_redis: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ─── LLM calls ────────────────────────────────────────────────────────────────

async def call_openai(messages: list[dict], model: str = "gpt-4o-mini") -> str:
    if not OPENAI_API_KEY:
        raise ValueError("No OpenAI key")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": model, "messages": messages, "temperature": 0.3},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def call_ollama(messages: list[dict], model: str = "llama3") -> str:
    # Convert to single prompt for Ollama
    prompt = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


async def llm_call(messages: list[dict], fast: bool = False) -> str:
    """Try OpenAI first, fall back to Ollama."""
    model = "gpt-4o-mini" if fast else "gpt-4o"
    try:
        return await call_openai(messages, model=model)
    except Exception as e:
        logger.warning(f"[orchestrator] OpenAI failed ({e}), falling back to Ollama")
        try:
            return await call_ollama(messages)
        except Exception as e2:
            raise HTTPException(503, f"All LLM backends unavailable: {e2}")


# ─── Intent routing ───────────────────────────────────────────────────────────

async def detect_intent(message: str) -> dict[str, Any]:
    """Detect which agent should handle this message."""
    agent_descriptions = "\n".join(
        f'- "{key}": {cfg["description"]}' for key, cfg in AGENTS.items()
    )
    prompt = ROUTER_SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": message},
    ]
    raw = await llm_call(messages, fast=True)

    try:
        # Extract JSON even if surrounded by markdown
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        logger.warning(f"[orchestrator] Failed to parse routing response: {raw}")
        return {"agent": "operator", "confidence": 0.5, "refined_query": message}


# ─── Schemas ──────────────────────────────────────────────────────────────────

class OrchestrateRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    force_agent: str | None = None  # bypass routing for testing


class OrchestrateResponse(BaseModel):
    response: str
    agent_used: str
    agent_name: str
    confidence: float
    session_id: str


class ChatRequest(BaseModel):
    prompt: str
    model: str = "llama3"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-orchestrator", "version": "1.0.0"}


@app.get("/")
def root():
    return {"service": "KT AI Orchestrator", "status": "running", "agents": list(AGENTS.keys())}


@app.get("/agents")
def list_agents():
    """List all available agents and their capabilities."""
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in AGENTS.items()
    ]


@app.post("/route", response_model=OrchestrateResponse)
async def orchestrate(req: OrchestrateRequest):
    """
    Main orchestration endpoint.
    1. Detects intent (which agent handles this)
    2. Loads conversation context from Redis
    3. Calls the appropriate agent with full context
    4. Saves response to Redis
    5. Returns response with agent attribution
    """
    import uuid
    session_id = req.session_id or str(uuid.uuid4())

    # Step 1: Route to appropriate agent
    if req.force_agent and req.force_agent in AGENTS:
        routing = {"agent": req.force_agent, "confidence": 1.0, "refined_query": req.message}
    else:
        routing = await detect_intent(req.message)

    agent_key = routing.get("agent", "operator")
    if agent_key not in AGENTS:
        agent_key = "operator"

    agent = AGENTS[agent_key]
    refined_query = routing.get("refined_query", req.message)
    confidence = routing.get("confidence", 0.8)

    logger.info(f"[orchestrator] Routing '{req.message[:50]}...' → {agent_key} (conf={confidence:.2f})")

    # Step 2: Load conversation history from Redis
    redis = await get_redis()
    history_key = f"session:{session_id}:history"
    raw_history = await redis.lrange(history_key, -20, -1)  # last 20 messages
    history: list[dict] = [json.loads(h) for h in raw_history]

    # Step 3: Build messages array
    messages = [{"role": "system", "content": agent["system_prompt"]}]
    messages.extend(history)
    messages.append({"role": "user", "content": refined_query})

    # Step 4: Call LLM
    response_text = await llm_call(messages)

    # Step 5: Save to Redis (TTL 24h)
    await redis.rpush(history_key, json.dumps({"role": "user", "content": req.message}))
    await redis.rpush(history_key, json.dumps({"role": "assistant", "content": response_text}))
    await redis.expire(history_key, 86400)

    return OrchestrateResponse(
        response=response_text,
        agent_used=agent_key,
        agent_name=agent["name"],
        confidence=confidence,
        session_id=session_id,
    )


@app.post("/chat")
async def chat_legacy(req: ChatRequest):
    """Legacy endpoint — kept for backward compatibility."""
    try:
        response = await llm_call([{"role": "user", "content": req.prompt}])
        return {"response": response, "model": "gpt-4o-mini"}
    except Exception as e:
        return {"error": str(e), "fallback": "LLM non disponible"}

