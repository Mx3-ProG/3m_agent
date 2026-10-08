export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  model?: string | null;
  created_at?: string;
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
  agents: Array<{ id: string; name: string; description: string; state: string }>;
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

