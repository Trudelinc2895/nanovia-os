"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { listAgents, orchestrate, type OrchestrateResponse } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  agent?: string;
  agent_name?: string;
  timestamp: Date;
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="text-purple-400 animate-pulse">Chargement...</div></div>}>
      <ChatInner />
    </Suspense>
  );
}

function ChatInner() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const forceAgent = searchParams.get("agent") || undefined;

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [agents, setAgents] = useState<Array<{ key: string; name: string }>>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | undefined>(forceAgent);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    listAgents().then(setAgents).catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;

    const userMessage: Message = {
      role: "user",
      content: input,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    const sentInput = input;
    setInput("");
    setSending(true);

    try {
      const res: OrchestrateResponse = await orchestrate(
        sentInput,
        conversationId
      );
      setConversationId(res.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          agent: res.agent_used,
          agent_name: res.agent_name,
          timestamp: new Date(),
        },
      ]);
    } catch (err: unknown) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ Erreur: ${err instanceof Error ? err.message : "Impossible de contacter l'IA"}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-purple-400 animate-pulse">Chargement...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur flex-shrink-0">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-gray-500 hover:text-white transition">←</Link>
            <span className="text-white font-bold">⚡ AI Orchestrator</span>
          </div>
          {/* Agent selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Agent:</span>
            <select
              value={selectedAgent || ""}
              onChange={(e) => setSelectedAgent(e.target.value || undefined)}
              className="bg-gray-800 border border-gray-700 text-sm text-white rounded-lg px-3 py-1.5 focus:outline-none focus:border-purple-500"
            >
              <option value="">Auto-détection 🧠</option>
              {agents.map((a) => (
                <option key={a.key} value={a.key}>{a.name}</option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto max-w-4xl mx-auto w-full px-6 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <div className="text-5xl mb-4">🤖</div>
            <h2 className="text-xl font-bold text-white mb-2">KT AI Orchestrator</h2>
            <p className="text-gray-400 max-w-sm text-sm">
              Pose n&apos;importe quelle question. L&apos;IA détecte automatiquement le bon agent (Operator, Ghost Agency, Content Cloner, Decision Engine...).
            </p>
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-left bg-gray-900 border border-gray-800 hover:border-purple-600 rounded-xl p-3 text-sm text-gray-300 transition"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-2xl rounded-2xl px-5 py-3 ${
                msg.role === "user"
                  ? "bg-purple-600 text-white"
                  : "bg-gray-900 border border-gray-800 text-gray-100"
              }`}
            >
              {msg.role === "assistant" && msg.agent_name && (
                <div className="text-xs text-purple-400 mb-1 font-semibold">
                  {getAgentIcon(msg.agent || "")} {msg.agent_name}
                </div>
              )}
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</div>
              <div className="text-xs opacity-40 mt-2">
                {msg.timestamp.toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-gray-900 border border-gray-800 rounded-2xl px-5 py-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-800 bg-gray-900/50 backdrop-blur flex-shrink-0">
        <form onSubmit={sendMessage} className="max-w-4xl mx-auto px-6 py-4 flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Pose ta question à l'IA..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-5 py-3 text-white focus:outline-none focus:border-purple-500 transition"
            disabled={sending}
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white font-semibold px-6 py-3 rounded-xl transition"
          >
            {sending ? "..." : "Envoyer"}
          </button>
        </form>
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "Génère un message de prospection pour un agent immobilier",
  "Aide-moi à décider si je dois lancer mon SaaS maintenant",
  "Crée un post LinkedIn viral sur l'IA et l'entrepreneuriat",
  "Organise ma to-do liste pour cette semaine",
];

function getAgentIcon(agent: string): string {
  const icons: Record<string, string> = {
    operator: "🤖",
    ghost_agency: "👻",
    content_cloner: "📢",
    decision_engine: "🧠",
    offer_generator: "🎯",
    knowledge_weapon: "📚",
  };
  return icons[agent] ?? "⚡";
}
