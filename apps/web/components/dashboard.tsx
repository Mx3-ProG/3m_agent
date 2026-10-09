"use client";

import { FormEvent, useEffect, useState } from "react";
import { AgentStatus, api, CalendarEvent, SystemStatus, Task } from "@/lib/api";

const formatter = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });

export function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [system, setSystem] = useState<SystemStatus>();
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [taskTitle, setTaskTitle] = useState("");
  const [error, setError] = useState<string>();

  async function refresh() {
    try {
      const [taskData, eventData, systemData, agentData] = await Promise.all([
        api<Task[]>("tasks"),
        api<CalendarEvent[]>("calendar/events"),
        api<SystemStatus>("system"),
        api<AgentStatus[]>("agents"),
      ]);
      setTasks(taskData);
      setEvents(eventData);
      setSystem(systemData);
      setAgents(agentData);
      setError(undefined);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Erreur de chargement");
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function addTask(event: FormEvent) {
    event.preventDefault();
    if (!taskTitle.trim()) return;
    await api<Task>("tasks", { method: "POST", body: JSON.stringify({ title: taskTitle }) });
    setTaskTitle("");
    await refresh();
  }

  async function toggleTask(task: Task) {
    await api<Task>(`tasks/${task.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: task.status === "done" ? "open" : "done" }),
    });
    await refresh();
  }

  async function toggleAgent(agent: AgentStatus) {
    await api(`agents/${agent.id}/${agent.enabled ? "disable" : "enable"}`, { method: "POST" });
    await refresh();
  }

  return (
    <section className="dashboard-page">
      <header className="dashboard-header">
        <div><span className="eyebrow">{formatter.format(new Date())}</span><h1>Bonjour, Mathieu.</h1><p>Voici votre espace de contrôle personnel.</p></div>
        <span className="system-pill"><i /> {system ? "Système opérationnel" : "Connexion…"}</span>
      </header>
      {error && <div className="error-banner">{error}</div>}
      <div className="stats-grid">
        <article><span className="card-icon">✓</span><small>Tâches ouvertes</small><strong>{tasks.filter((task) => task.status !== "done").length}</strong><p>{tasks.filter((task) => task.priority === "urgent").length} urgente(s)</p></article>
        <article><span className="card-icon">◇</span><small>Prochains événements</small><strong>{events.length}</strong><p>Calendrier de démonstration</p></article>
        <article><span className="card-icon">◉</span><small>Agents actifs</small><strong>{agents.filter((agent) => agent.enabled).length}</strong><p>{system?.skills.filter((skill) => skill.enabled).length ?? 0} compétences actives</p></article>
        <article><span className="card-icon">⌁</span><small>Fournisseurs configurés</small><strong>{system ? Object.values(system.providers.configured).filter(Boolean).length : "—"}</strong><p>Démo locale toujours disponible</p></article>
      </div>
      <div className="dashboard-grid">
        <article className="panel tasks-panel">
          <div className="panel-heading"><div><span className="eyebrow">Priorités</span><h2>Mes tâches</h2></div></div>
          <form className="quick-task" onSubmit={addTask}><input value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="Ajouter une tâche…" /><button>+</button></form>
          <div className="task-list">
            {tasks.length === 0 && <p className="empty">Aucune tâche. Votre journée est libre.</p>}
            {tasks.slice(0, 6).map((task) => (
              <button key={task.id} className={`task-row ${task.status === "done" ? "done" : ""}`} onClick={() => void toggleTask(task)}>
                <i className={`priority ${task.priority}`} /><span>{task.title}</span><small>{task.status === "done" ? "Terminée" : task.priority}</small>
              </button>
            ))}
          </div>
        </article>
        <article className="panel agenda-panel">
          <div className="panel-heading"><div><span className="eyebrow">À venir</span><h2>Agenda</h2></div><span className="demo-badge">DÉMO</span></div>
          <div className="agenda-list">
            {events.slice(0, 5).map((event) => (
              <div className="agenda-row" key={event.id}>
                <time>{new Date(event.starts_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</time>
                <div><strong>{event.title}</strong><small>{new Date(event.starts_at).toLocaleDateString("fr-FR")}</small></div>
              </div>
            ))}
          </div>
        </article>
        <article className="panel agents-panel">
          <div className="panel-heading"><div><span className="eyebrow">Orchestration</span><h2>Agents</h2></div></div>
          {agents.map((agent) => (
            <div className={`agent-row ${agent.enabled ? "" : "disabled"}`} key={agent.id}>
              <span>{agent.name.slice(0, 1)}</span>
              <div>
                <strong>{agent.name}</strong>
                <small>{agent.description}</small>
                <small>{agent.tool_count} outils · {agent.health.status}{agent.last_used_at ? ` · utilisé ${new Date(agent.last_used_at).toLocaleString("fr-FR")}` : ""}</small>
                {agent.health.provider ? <small>Provider {agent.health.provider.provider} · {agent.health.provider.authorization}</small> : null}
              </div>
              <button
                type="button"
                className="agent-toggle"
                aria-pressed={agent.enabled}
                aria-label={`${agent.enabled ? "Désactiver" : "Activer"} ${agent.name}`}
                onClick={() => void toggleAgent(agent)}
              >
                <i />
              </button>
            </div>
          ))}
        </article>
      </div>
    </section>
  );
}
