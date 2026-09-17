import React from "react";
import { Badge, Card, StatusIndicator, SectionHeader } from "../components/ui";
import { PROVIDERS, HEALTH_TIMELINE } from "../data/mock";

export function ProviderHealth() {
  const hasDown = PROVIDERS.some(p => p.status === "down");
  const hasDegraded = PROVIDERS.some(p => p.status === "degraded");
  const overall = hasDown || hasDegraded ? (hasDown ? "degraded" : "degraded") : "healthy";

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Provider Health"
        description="Real-time health monitoring across all connected API providers."
      />

      {/* Overall status */}
      <Card className="p-6">
        <div className="flex items-center gap-6">
          <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${
            overall === "healthy" ? "bg-green-500/10 border border-green-500/20" : "bg-amber-500/10 border border-amber-500/20"
          }`}>
            <StatusIndicator status={overall as "healthy" | "degraded"} size="md" />
          </div>
          <div>
            <div className="text-xs text-[var(--muted-foreground)] uppercase tracking-wider mb-1">System Health</div>
            <div className={`text-2xl font-semibold ${overall === "healthy" ? "text-green-500" : "text-amber-500"}`}>
              {overall.toUpperCase()}
            </div>
            <div className="text-xs text-[var(--muted-foreground)] mt-1">
              {PROVIDERS.filter(p => p.status === "healthy").length}/{PROVIDERS.length} providers operational
              {hasDown && ` · ${PROVIDERS.filter(p => p.status === "down").length} provider(s) down`}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-6">
            {[
              { label: "Healthy", count: PROVIDERS.filter(p => p.status === "healthy").length, color: "text-green-500" },
              { label: "Degraded", count: PROVIDERS.filter(p => p.status === "degraded").length, color: "text-amber-500" },
              { label: "Down", count: PROVIDERS.filter(p => p.status === "down").length, color: "text-red-400" },
            ].map(s => (
              <div key={s.label} className="text-center">
                <div className={`text-2xl font-semibold mono ${s.color}`}>{s.count}</div>
                <div className="text-xs text-[var(--muted-foreground)]">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Provider cards */}
      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        {PROVIDERS.map(p => (
          <Card key={p.id} className="p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[var(--secondary)] border border-[var(--border)] flex items-center justify-center text-sm font-bold text-[var(--foreground)]">
                  {p.name.charAt(0)}
                </div>
                <div>
                  <div className="text-sm font-semibold text-[var(--foreground)]">{p.name}</div>
                  <div className="text-[10px] text-[var(--muted-foreground)]">Last check: {p.lastHealthCheck}</div>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <StatusIndicator status={p.status as "healthy" | "degraded" | "down"} />
                <Badge variant={p.status === "healthy" ? "success" : p.status === "degraded" ? "warning" : "error"}>
                  {p.status.toUpperCase()}
                </Badge>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: "Latency", value: p.status === "down" ? "—" : `${p.latency}ms` },
                { label: "Availability", value: `${p.availability}%` },
                { label: "Circuit", value: p.circuitState.replace("-", " ").toUpperCase() },
              ].map(s => (
                <div key={s.label} className="bg-[var(--secondary)] rounded-[var(--radius)] p-3 border border-[var(--border)]">
                  <div className="text-[10px] text-[var(--muted-foreground)] mb-1">{s.label}</div>
                  <div className={`mono text-sm font-medium ${
                    s.label === "Circuit"
                      ? p.circuitState === "closed" ? "text-green-500" : p.circuitState === "half-open" ? "text-amber-500" : "text-red-400"
                      : "text-[var(--foreground)]"
                  }`}>{s.value}</div>
                </div>
              ))}
            </div>

            {/* Uptime bar */}
            <div>
              <div className="flex items-center justify-between mb-1.5 text-xs">
                <span className="text-[var(--muted-foreground)]">Availability (90d)</span>
                <span className="mono text-[var(--foreground)]">{p.availability}%</span>
              </div>
              <div className="h-1.5 bg-[var(--muted)] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${p.status === "healthy" ? "bg-green-500" : p.status === "degraded" ? "bg-amber-500" : "bg-red-500"}`}
                  style={{ width: `${p.availability}%` }}
                />
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Health timeline */}
      <Card className="p-5">
        <div className="text-sm font-medium text-[var(--foreground)] mb-4">Health Timeline</div>
        <div className="flex flex-col gap-0">
          {HEALTH_TIMELINE.map((e, i) => (
            <div key={i} className="flex gap-4">
              <div className="flex flex-col items-center">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1 ${
                  e.status === "healthy" ? "bg-green-500" : e.status === "degraded" ? "bg-amber-500" : e.status === "warn" ? "bg-amber-400" : "bg-red-500"
                }`} />
                {i < HEALTH_TIMELINE.length - 1 && <div className="w-px flex-1 bg-[var(--border)] my-1" />}
              </div>
              <div className="pb-4 flex-1 flex items-center gap-4">
                <span className="mono text-xs text-[var(--muted-foreground)] w-12 flex-shrink-0">{e.time}</span>
                <span className="text-xs text-[var(--foreground)]">{e.event}</span>
                <Badge
                  variant={e.status === "healthy" ? "success" : e.status === "error" ? "error" : "warning"}
                  className="ml-auto flex-shrink-0 text-[10px]"
                >
                  {e.status}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
