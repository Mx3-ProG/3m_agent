"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, type AssistantMessage, type ConversationSummary, streamChat } from "@/lib/api";

type ConversationState =
  | "idle"
  | "listening"
  | "transcribing"
  | "thinking"
  | "planning"
  | "calling_agent"
  | "executing_tool"
  | "speaking"
  | "responding"
  | "waiting_confirmation"
  | "error";
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
type MicrophoneMode = "push" | "continuous";

const stateLabels: Record<ConversationState, string> = {
  idle: "Prêt",
  listening: "Je vous écoute…",
  transcribing: "Transcription…",
  thinking: "Réflexion…",
  planning: "Planification…",
  calling_agent: "Appel de l’agent…",
  executing_tool: "Exécution de l’outil…",
  speaking: "Réponse vocale…",
  responding: "Préparation de la réponse…",
  waiting_confirmation: "Confirmation requise",
  error: "Une erreur est survenue",
};

const busyStates = new Set<ConversationState>([
  "thinking",
  "planning",
  "calling_agent",
  "executing_tool",
  "responding",
]);

export function Conversation() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const [state, setState] = useState<ConversationState>("idle");
  const [error, setError] = useState<string>();
  const [activity, setActivity] = useState<string>();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [microphoneMode, setMicrophoneMode] = useState<MicrophoneMode>("push");
  const [continuousActive, setContinuousActive] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const continuousRef = useRef(false);
  const busyRef = useRef(false);
  const speakingRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("conversation");
    if (!id) return;
    setConversationId(id);
    Promise.all([
      api<ConversationSummary>(`conversations/${id}`),
      api<AssistantMessage[]>(`conversations/${id}/messages`),
    ])
      .then(([, history]) => setMessages(history))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Erreur de reprise"));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(text: string) {
    const clean = text.trim();
    if (!clean || busyStates.has(state)) return;
    setError(undefined);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: clean }]);
    setInput("");
    setState("thinking");
    busyRef.current = true;
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setActivity("Connexion à l’orchestrateur…");
    try {
      const response = await streamChat(
        {
          message: clean,
          conversation_id: conversationId,
          provider: provider || undefined,
          model: model || undefined,
        },
        (progress) => {
          if (progress.state in stateLabels) setState(progress.state as ConversationState);
          setActivity(progress.label);
        },
      );
      setConversationId(response.conversation_id);
      if (!conversationId) {
        window.history.replaceState(null, "", `/?conversation=${response.conversation_id}`);
      }
      setMessages((current) => [
        ...current,
        {
          id: response.message_id,
          role: "assistant",
          content: response.response,
          provider: response.provider,
          model: response.model,
          state: response.state,
          agents_used: response.agents_used,
          tools_used: response.tools_used,
          confirmation_id: response.confirmation_id,
        },
      ]);
      const settledState =
        response.state === "waiting_confirmation"
          ? "waiting_confirmation"
          : response.state === "error"
            ? "error"
            : "idle";
      setActivity(undefined);
      window.dispatchEvent(new Event("3m:conversations-changed"));
      if (voiceEnabled) speak(response.response, settledState);
      else finishTurn(settledState);
    } catch (caught) {
      busyRef.current = false;
      setState("error");
      setActivity(undefined);
      setError(caught instanceof Error ? caught.message : "Erreur inconnue");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function speak(text: string, settledState: ConversationState = "idle") {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    if (!("speechSynthesis" in window)) {
      finishTurn(settledState);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "fr-FR";
    utterance.rate = 1.02;
    utterance.onstart = () => {
      speakingRef.current = true;
      setState("speaking");
    };
    utterance.onend = () => {
      speakingRef.current = false;
      finishTurn(settledState);
    };
    utterance.onerror = () => {
      speakingRef.current = false;
      finishTurn(settledState);
    };
    window.speechSynthesis.speak(utterance);
  }

  function finishTurn(settledState: ConversationState) {
    busyRef.current = false;
    if (continuousRef.current && settledState !== "error") {
      setState("listening");
      window.setTimeout(startListening, 250);
    } else {
      setState(settledState);
    }
  }

  function stopAudio() {
    window.speechSynthesis?.cancel();
    speakingRef.current = false;
    busyRef.current = false;
    if (continuousRef.current) {
      setState("listening");
      window.setTimeout(startListening, 100);
    } else {
      setState("idle");
    }
  }

  function startListening() {
    if (busyRef.current || speakingRef.current || recognitionRef.current) return;
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
        busyRef.current = true;
        recognition.stop();
        void sendMessage(transcript);
      }
    };
    recognition.onerror = () => {
      setError("Le microphone n’a pas pu être utilisé. Vérifiez son autorisation dans le navigateur.");
      setState("error");
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      if (continuousRef.current && !busyRef.current && !speakingRef.current) {
        setState("listening");
        window.setTimeout(startListening, 300);
      } else if (!continuousRef.current && !busyRef.current) {
        setState("idle");
      }
    };
    recognitionRef.current = recognition;
    recognition.start();
    setError(undefined);
    setState("listening");
  }

  function disableMicrophone() {
    continuousRef.current = false;
    setContinuousActive(false);
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    window.speechSynthesis?.cancel();
    speakingRef.current = false;
    busyRef.current = false;
    setState("idle");
  }

  function toggleMicrophone() {
    if (microphoneMode === "continuous") {
      if (continuousRef.current) {
        disableMicrophone();
      } else {
        continuousRef.current = true;
        setContinuousActive(true);
        startListening();
      }
      return;
    }
    if (state === "listening") {
      disableMicrophone();
    } else {
      startListening();
    }
  }

  function changeMicrophoneMode(mode: MicrophoneMode) {
    disableMicrophone();
    setMicrophoneMode(mode);
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

      {continuousActive ? (
        <div className="privacy-indicator" role="status">
          <i /> Micro actif — conversation continue
          <button type="button" onClick={disableMicrophone}>Couper</button>
        </div>
      ) : null}

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
                {message.role === "assistant" && (
                  <div className="execution-meta">
                    {message.tools_used?.map((tool) => <code key={tool}>{tool}</code>)}
                    {message.agents_used?.map((agent) => <span key={agent}>{agent}</span>)}
                    {message.state === "waiting_confirmation" ? <strong>Confirmation requise</strong> : null}
                    {message.provider ? <small>{message.provider} · {message.model}</small> : null}
                  </div>
                )}
              </article>
            ))}
            {busyStates.has(state) ? (
              <div className="live-progress" role="status">
                <div className="thinking"><i /><i /><i /></div>
                <span>{activity ?? stateLabels[state]}</span>
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="composer-area">
        {error && <div className="error-banner" role="alert">{error}</div>}
        <form className="composer" onSubmit={submit}>
          <button type="button" className={`mic-button ${state === "listening" || continuousActive ? "active" : ""}`} onClick={toggleMicrophone} aria-label={continuousActive ? "Désactiver le microphone" : "Activer le microphone"}>●</button>
          <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Écrivez ou utilisez le microphone…" aria-label="Message" />
          {(state === "speaking" || state === "listening") && <button type="button" className="stop-button" onClick={stopAudio} aria-label="Interrompre">■</button>}
          <button className="send-button" type="submit" disabled={!input.trim() || busyStates.has(state)}>↑</button>
        </form>
        <div className="conversation-options">
          <div className="microphone-mode" aria-label="Mode du microphone">
            <button type="button" className={microphoneMode === "push" ? "active" : ""} onClick={() => changeMicrophoneMode("push")}>Appuyer pour parler</button>
            <button type="button" className={microphoneMode === "continuous" ? "active" : ""} onClick={() => changeMicrophoneMode("continuous")}>Conversation continue</button>
          </div>
          <label className="voice-toggle"><input type="checkbox" checked={voiceEnabled} onChange={(event) => setVoiceEnabled(event.target.checked)} /> Voix de 3M</label>
        </div>
      </div>
    </section>
  );
}
