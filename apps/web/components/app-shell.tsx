"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { api, type ConversationSummary } from "@/lib/api";

const navigation = [
  { href: "/", label: "Conversation", icon: "◉" },
  { href: "/dashboard", label: "Vue d’ensemble", icon: "⌁" },
];

function conversationGroup(value: string) {
  const now = new Date();
  const date = new Date(value);
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.floor((startToday.getTime() - startDate.getTime()) / 86_400_000);
  if (days <= 0) return "Aujourd’hui";
  if (days === 1) return "Hier";
  if (days <= 7) return "7 derniers jours";
  return "Plus ancien";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const groupedConversations = conversations.reduce<Record<string, ConversationSummary[]>>(
    (groups, conversation) => {
      const group = conversationGroup(conversation.last_message_at);
      groups[group] = [...(groups[group] ?? []), conversation];
      return groups;
    },
    {},
  );

  async function refreshConversations() {
    try {
      setConversations(await api<ConversationSummary[]>("conversations?limit=30"));
    } catch {
      setConversations([]);
    }
  }

  useEffect(() => {
    void refreshConversations();
    const refresh = () => void refreshConversations();
    window.addEventListener("3m:conversations-changed", refresh);
    return () => window.removeEventListener("3m:conversations-changed", refresh);
  }, []);

  async function newConversation() {
    const conversation = await api<ConversationSummary>("conversations", {
      method: "POST",
      body: JSON.stringify({}),
    });
    window.location.assign(`/?conversation=${conversation.id}`);
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${historyOpen ? "open" : ""}`}>
        <Link href="/" className="brand" aria-label="Accueil 3M">
          <span className="brand-mark">3M</span>
          <span>
            <strong>3M</strong>
            <small>Personal Intelligence</small>
          </span>
        </Link>
        <nav aria-label="Navigation principale">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "nav-item active" : "nav-item"}
            >
              <span>{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
        <button type="button" className="new-conversation" onClick={() => void newConversation()}>
          <span>＋</span> Nouvelle conversation
        </button>
        <section className="conversation-library" aria-label="Conversations enregistrées">
          <span className="sidebar-label">Conversations</span>
          {conversations.length === 0 ? <small>Aucune conversation</small> : null}
          {Object.entries(groupedConversations).map(([group, items]) => (
            <div className="conversation-group" key={group}>
              <small className="conversation-group-label">{group}</small>
              {items.map((conversation) => (
                <a
                  key={conversation.id}
                  href={`/?conversation=${conversation.id}`}
                  onClick={() => setHistoryOpen(false)}
                >
                  <strong>{conversation.title}</strong>
                  <small>
                    {new Date(conversation.last_message_at).toLocaleDateString("fr-FR", {
                      day: "numeric",
                      month: "short",
                    })}
                  </small>
                </a>
              ))}
            </div>
          ))}
        </section>
        <div className="sidebar-bottom">
          <div className="status-line"><i /> Système local</div>
          <small>Données stockées sur ce Mac</small>
        </div>
      </aside>
      <button
        type="button"
        className="mobile-history-toggle"
        aria-label="Afficher les conversations"
        aria-expanded={historyOpen}
        onClick={() => setHistoryOpen((current) => !current)}
      >
        ☰
      </button>
      <main>{children}</main>
      <nav className="mobile-nav" aria-label="Navigation mobile">
        {navigation.map((item) => (
          <Link key={item.href} href={item.href} className={pathname === item.href ? "active" : ""}>
            <span>{item.icon}</span>
            <small>{item.label}</small>
          </Link>
        ))}
      </nav>
    </div>
  );
}
