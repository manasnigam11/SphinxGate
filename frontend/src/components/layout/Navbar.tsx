import React from "react";
import { Badge } from "../ui";

interface NavbarProps {
  page: string;
  theme: "light" | "dark";
  onThemeToggle: () => void;
  environment: string;
  onEnvironmentChange: (e: string) => void;
}

const PAGE_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  playground: "API Playground",
  providers: "Providers",
  requests: "Requests",
  logs: "Logs",
  analytics: "Analytics",
  health: "Provider Health",
  policies: "Resilience Policies",
  "circuit-breakers": "Circuit Breakers",
  "fault-injection": "Fault Injection",
  copilot: "AI Copilot",
  incidents: "Incidents",
};

const SECTION: Record<string, string> = {
  dashboard: "Overview",
  playground: "Playground",
  providers: "Playground",
  requests: "Observability",
  logs: "Observability",
  analytics: "Observability",
  health: "Observability",
  policies: "Resilience",
  "circuit-breakers": "Resilience",
  "fault-injection": "Resilience",
  copilot: "AI Engineering",
  incidents: "AI Engineering",
};

export function Navbar({ page, theme, onThemeToggle, environment, onEnvironmentChange }: NavbarProps) {
  const label = PAGE_LABELS[page] || page;
  const section = SECTION[page];

  return (
    <header className="h-14 border-b border-[var(--border)] bg-[var(--card)] flex items-center justify-between px-5 flex-shrink-0">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-[var(--muted-foreground)]">{section}</span>
        <span className="text-[var(--muted-foreground)]">/</span>
        <span className="font-medium text-[var(--foreground)]">{label}</span>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2">
        {/* System health */}
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius)] bg-[var(--secondary)] border border-[var(--border)]">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse-dot" />
          <span className="text-xs text-[var(--foreground)] font-medium">Degraded</span>
        </div>

        {/* Environment */}
        <div className="bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-2.5 py-1.5 text-xs text-[var(--foreground)] opacity-80 cursor-default">
          Production
        </div>



        {/* Theme toggle */}
        <button
          onClick={onThemeToggle}
          className="p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)] rounded-[var(--radius)] transition-colors cursor-pointer"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
              <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          )}
        </button>


      </div>
    </header>
  );
}
