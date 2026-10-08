"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Conversation", icon: "◉" },
  { href: "/dashboard", label: "Vue d’ensemble", icon: "⌁" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-shell">
      <aside className="sidebar">
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
        <div className="sidebar-bottom">
          <div className="status-line"><i /> Système local</div>
          <small>Données stockées sur ce Mac</small>
        </div>
      </aside>
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

