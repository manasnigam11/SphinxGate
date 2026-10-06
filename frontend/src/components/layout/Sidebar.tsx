import React, { useState } from "react";
import { Tooltip } from "../ui";

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "OVERVIEW",
    items: [
      { id: "dashboard", label: "Dashboard", icon: <GridIcon /> },
    ],
  },
  {
    label: "PLAYGROUND",
    items: [
      { id: "playground", label: "API Playground", icon: <PlayIcon /> },
      { id: "providers", label: "Providers", icon: <ServerIcon /> },
    ],
  },
  {
    label: "OBSERVABILITY",
    items: [
      { id: "requests", label: "Requests", icon: <ActivityIcon /> },
      { id: "logs", label: "Logs", icon: <FileTextIcon /> },
      { id: "analytics", label: "Analytics", icon: <BarChartIcon /> },
      { id: "health", label: "Provider Health", icon: <HeartIcon /> },
    ],
  },
  {
    label: "RESILIENCE",
    items: [
      { id: "policies", label: "Policies", icon: <ShieldIcon /> },
      { id: "circuit-breakers", label: "Circuit Breakers", icon: <ZapIcon /> },
      { id: "fault-injection", label: "Fault Injection", icon: <AlertTriangleIcon /> },
    ],
  },
  {
    label: "AI ENGINEERING",
    items: [
      { id: "copilot", label: "AI Copilot", icon: <BotIcon /> },
      { id: "incidents", label: "Incidents", icon: <FlagIcon /> },
    ],
  },
];

interface SidebarProps {
  active: string;
  onNav: (id: string) => void;
}

export function Sidebar({ active, onNav }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`flex flex-col h-screen border-r border-[var(--border)] bg-[var(--card)] transition-all duration-200 flex-shrink-0 ${collapsed ? "w-14" : "w-56"}`}
    >
      {/* Logo */}
      <div className={`flex items-center gap-2.5 h-14 px-4 border-b border-[var(--border)] flex-shrink-0`}>
        <div className="w-7 h-7 rounded-lg bg-[var(--accent)] flex items-center justify-center flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        {!collapsed && (
          <div>
            <div className="text-sm font-semibold text-[var(--foreground)] leading-none">SphinxGate</div>
            <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">API Infrastructure</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 scrollbar-hide">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-1">
            {!collapsed && (
              <div className="px-4 py-1.5 text-[10px] font-semibold tracking-widest text-[var(--muted-foreground)]">
                {group.label}
              </div>
            )}
            {collapsed && <div className="my-2 mx-3 h-px bg-[var(--border)]" />}
            {group.items.map((item) => {
              const isActive = active === item.id;
              const btn = (
                <button
                  key={item.id}
                  onClick={() => onNav(item.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-[var(--radius)] mx-1 text-sm font-medium transition-colors cursor-pointer text-left ${
                    isActive
                      ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"
                  }`}
                  style={{ width: collapsed ? "calc(100% - 8px)" : "calc(100% - 8px)" }}
                >
                  <span className="flex-shrink-0">{item.icon}</span>
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </button>
              );
              return collapsed ? (
                <Tooltip key={item.id} label={item.label}>{btn}</Tooltip>
              ) : btn;
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-[var(--border)] p-2 flex flex-col gap-1">
        {!collapsed && (
          <>
            <button className="flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] rounded-[var(--radius)] hover:bg-[var(--secondary)] transition-colors cursor-pointer">
              <BookIcon /><span>Documentation</span>
            </button>
            <button className="flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] rounded-[var(--radius)] hover:bg-[var(--secondary)] transition-colors cursor-pointer">
              <HelpIcon /><span>Help & Support</span>
            </button>
          </>
        )}

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] rounded-[var(--radius)] hover:bg-[var(--secondary)] transition-colors cursor-pointer mt-1"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {collapsed ? <><polyline points="9 18 15 12 9 6"/></> : <><polyline points="15 18 9 12 15 6"/></>}
          </svg>
        </button>
      </div>
    </aside>
  );
}

// Icon components
function GridIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>; }
function PlayIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>; }
function ServerIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>; }
function ActivityIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>; }
function FileTextIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>; }
function BarChartIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>; }
function HeartIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>; }
function ShieldIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>; }
function ZapIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>; }
function AlertTriangleIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>; }
function BotIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>; }
function FlagIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>; }
function KeyIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>; }
function SettingsIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M19.07 19.07l-1.41-1.41M4.93 19.07l1.41-1.41M20 12h2M2 12h2M12 20v2M12 2v2"/></svg>; }
function BookIcon() { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>; }
function HelpIcon() { return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>; }
