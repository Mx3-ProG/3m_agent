"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, AssistantMessage } from "@/lib/api";

type ConversationState = "idle" | "listening" | "transcribing" | "thinking" | "speaking" | "error";
type SpeechRecognitionInstance = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};

const stateLabels: Record<ConversationState, string> = {
  idle: "Prêt",
  listening: "Je vous écoute…",
  transcribing: "Transcription…",
  thinking: "Réflexion…",
  speaking: "Réponse vocale…",
  error: "Une erreur est survenue",
};

export function Conversation() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const [state, setState] = useState<ConversationState>("idle");
  const [error, setError] = useState<string>();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(text: string) {
    const clean = text.trim();
    if (!clean || state === "thinking") return;
    setError(undefined);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: clean }]);
    setInput("");
    setState("thinking");
    try {
      const response = await api<{
        conversation_id: string;
        message_id: string;
        response: string;
        provider: string;
        model: string;
      }>("conversations/chat", {
        method: "POST",
        body: JSON.stringify({
          message: clean,
          conversation_id: conversationId,
          provider: provider || undefined,
          model: model || undefined,
        }),
      });
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.response,
          provider: response.provider,
          model: response.model,
        },
      ]);
      if (voiceEnabled) speak(response.response);
      else setState("idle");
    } catch (caught) {
      setState("error");
      setError(caught instanceof Error ? caught.message : "Erreur inconnue");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function speak(text: string) {
    if (!("speechSynthesis" in window)) {
      setState("idle");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "fr-FR";
    utterance.rate = 1.02;
    utterance.onstart = () => setState("speaking");
    utterance.onend = () => setState("idle");
    utterance.onerror = () => setState("idle");
    window.speechSynthesis.speak(utterance);
  }

  function stopAudio() {
    window.speechSynthesis?.cancel();
    recognitionRef.current?.stop();
    setState("idle");
  }

  function toggleMicrophone() {
    if (state === "listening") {
      recognitionRef.current?.stop();
      setState("transcribing");
      return;
    }
    const scope = window as typeof window & {
      SpeechRecognition?: new () => SpeechRecognitionInstance;
      webkitSpeechRecognition?: new () => SpeechRecognitionInstance;
    };
    const Constructor = scope.SpeechRecognition ?? scope.webkitSpeechRecognition;
    if (!Constructor) {
      setError("La reconnaissance vocale du navigateur n’est pas disponible. Utilisez la saisie texte.");
      setState("error");
      return;
    }
    const recognition = new Constructor();
    recognition.lang = "fr-FR";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      let transcript = "";
      let final = false;
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript;
        final ||= event.results[index].isFinal;
      }
      setInput(transcript);
      if (final) {
        setState("transcribing");
        recognition.stop();
        void sendMessage(transcript);
      }
    };
    recognition.onerror = () => {
      setError("Le microphone n’a pas pu être utilisé. Vérifiez son autorisation dans le navigateur.");
      setState("error");
    };
    recognition.onend = () => setState((current) => (current === "listening" ? "idle" : current));
    recognitionRef.current = recognition;
    recognition.start();
    setError(undefined);
    setState("listening");
  }

  return (
    <section className="conversation-page">
      <header className="topbar">
        <div><span className="eyebrow">Conversation</span><h1>Parlez à 3M</h1></div>
        <div className="model-controls">
          <select value={provider} onChange={(event) => setProvider(event.target.value)} aria-label="Fournisseur LLM">
            <option value="">Par défaut local</option>
            <option value="demo">Démo locale</option>
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
          <input value={model} onChange={(event) => setModel(event.target.value)} aria-label="Modèle" placeholder="Modèle par défaut" />
        </div>
      </header>

      <div className="conversation-stage">
        {messages.length === 0 ? (
          <div className="hero-orb-wrap">
            <div className={`orb ${state}`} aria-hidden="true"><div /><div /><div /></div>
            <p className="state-label"><i /> {stateLabels[state]}</p>
            <h2>Bonjour, je suis <em>3M.</em></h2>
            <p>Votre assistant personnel local. Parlez-moi de votre journée, de vos tâches ou de ce que vous souhaitez accomplir.</p>
            <div className="suggestions">
              {["Organise mes priorités", "Que puis-je faire aujourd’hui ?", "Aide-moi à planifier un projet"].map((suggestion) => (
                <button key={suggestion} onClick={() => void sendMessage(suggestion)}>{suggestion}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="message-list" aria-live="polite">
            {messages.map((message) => (
              <article key={message.id} className={`message ${message.role}`}>
                <span>{message.role === "assistant" ? "3M" : "Vous"}</span>
                <p>{message.content}</p>
                {message.provider && <small>{message.provider} · {message.model}</small>}
              </article>
            ))}
            {state === "thinking" && <div className="thinking"><i /><i /><i /></div>}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="composer-area">
        {error && <div className="error-banner" role="alert">{error}</div>}
        <form className="composer" onSubmit={submit}>
          <button type="button" className={`mic-button ${state === "listening" ? "active" : ""}`} onClick={toggleMicrophone} aria-label="Activer ou désactiver le microphone">●</button>
          <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Écrivez ou utilisez le microphone…" aria-label="Message" />
          {(state === "speaking" || state === "listening") && <button type="button" className="stop-button" onClick={stopAudio} aria-label="Interrompre">■</button>}
          <button className="send-button" type="submit" disabled={!input.trim() || state === "thinking"}>↑</button>
        </form>
        <label className="voice-toggle"><input type="checkbox" checked={voiceEnabled} onChange={(event) => setVoiceEnabled(event.target.checked)} /> Lecture vocale navigateur</label>
      </div>
    </section>
  );
}
