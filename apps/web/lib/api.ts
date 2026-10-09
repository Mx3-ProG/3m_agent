export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  model?: string | null;
  created_at?: string;
  state?: string;
  agents_used?: string[];
  tools_used?: string[];
  confirmation_id?: string | null;
};

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at: string;
  status: "active" | "archived";
  summary: string;
  active_topic: string;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  response: string;
  provider: string;
  model: string;
  state: string;
  agents_used: string[];
  tools_used: string[];
  confirmation_id: string | null;
};

export type OrchestrationProgress = {
  state: string;
  label?: string;
  agent_id?: string;
  tool_name?: string;
  agents?: string[];
  detail?: string;
};

export type AgentStatus = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  status: string;
  health: {
    status: string;
    healthy: boolean;
    error: string | null;
    provider?: { provider: string; available: boolean; authorization: string };
  };
  tool_count: number;
  last_used_at: string | null;
};

export type Task = {
  id: string;
  title: string;
  description: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "open" | "in_progress" | "done";
  due_at: string | null;
  created_at: string;
};

export type CalendarEvent = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  location: string;
  source: string;
};

export type SystemStatus = {
  status: string;
  agents: AgentStatus[];
  skills: Array<{ id: string; name: string; version: string; enabled: boolean }>;
  providers: { available: string[]; configured: Record<string, boolean> };
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: `Erreur ${response.status}` }));
    throw new Error(body.detail ?? `Erreur ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function streamChat(
  body: Record<string, unknown>,
  onProgress: (progress: OrchestrationProgress) => void,
): Promise<ChatResponse> {
  const response = await fetch("/api/backend/conversations/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({ detail: `Erreur ${response.status}` }));
    throw new Error(payload.detail ?? `Erreur ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResponse | undefined;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      if (!block || block.startsWith(":")) continue;
      const event = block.match(/^event:\s*(.+)$/m)?.[1];
      const data = block.match(/^data:\s*(.+)$/m)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data) as OrchestrationProgress | ChatResponse;
      if (event === "result") result = payload as ChatResponse;
      else if (event === "error") {
        throw new Error((payload as OrchestrationProgress).detail ?? "Erreur d’orchestration");
      } else onProgress(payload as OrchestrationProgress);
    }
    if (done) break;
  }
  if (!result) throw new Error("La réponse progressive s’est terminée sans résultat.");
  return result;
}
