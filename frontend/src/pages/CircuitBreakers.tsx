import React from "react";
import { Badge, Card, SectionHeader } from "../components/ui";
import { PROVIDERS } from "../data/mock";
import type { CircuitState } from "../types";

const CIRCUIT_EVENTS: Record<string, { time: string; state: CircuitState; event: string }[]> = {
  "p2": [
    { time: "14:31:00", state: "closed", event: "Failure count 1 — latency exceeded threshold" },
    { time: "14:31:50", state: "closed", event: "Failure count 2 — timeout on /chat/completions" },
    { time: "14:32:04", state: "closed", event: "Failure count 4 — threshold approaching" },
    { time: "14:32:08", state: "open", event: "Circuit opened — 5 consecutive failures" },
    { time: "14:33:08", state: "half-open", event: "Recovery probe sent" },
    { time: "14:34:42", state: "closed", event: "Recovery confirmed — circuit closed" },
    { time: "14:38:00", state: "open", event: "Circuit opened — new failure burst" },
    { time: "14:42:00", state: "half-open", event: "Recovery probe pending" },
  ],
  "p4": [
    { time: "14:38:00", state: "open", event: "Circuit opened — connection refused" },
  ],
};

function CircuitStateDisplay({ state }: { state: CircuitState }) {
  const config = {
    closed: { label: "CIRCUIT CLOSED", bg: "bg-green-500/5 border-green-500/20", text: "text-green-500", dot: "bg-green-500" },
    "half-open": { label: "HALF OPEN", bg: "bg-amber-500/5 border-amber-500/20", text: "text-amber-500", dot: "bg-amber-500" },
    open: { label: "CIRCUIT OPEN", bg: "bg-red-500/5 border-red-500/20", text: "text-red-400", dot: "bg-red-500" },
  }[state];

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-[var(--radius)] border ${config.bg}`}>
      <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${config.dot} ${state !== "closed" ? "animate-pulse-dot" : ""}`} />
      <span className={`mono text-sm font-semibold tracking-wider ${config.text}`}>{config.label}</span>
    </div>
  );
}

export function CircuitBreakers() {
  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Circuit Breakers"
        description="Monitor real-time circuit breaker state across all configured providers."
      />

      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        {PROVIDERS.map(p => {
          const events = CIRCUIT_EVENTS[p.id] || [];
          const failureCount = p.circuitState === "closed" ? Math.floor(Math.random() * 3) : p.circuitState === "half-open" ? 5 : 5;

          return (
            <Card key={p.id} className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="text-sm font-semibold text-[var(--foreground)]">{p.name}</div>
                <Badge variant="muted" className="mono text-[10px]">{p.slug}</Badge>
              </div>

              <CircuitStateDisplay state={p.circuitState} />

              <div className="grid grid-cols-3 gap-3 mt-4">
                {[
                  { label: "Failure count", value: `${failureCount} / 5` },
                  { label: "Last failure", value: p.circuitState === "closed" && failureCount === 0 ? "None" : "2m ago" },
                  { label: "Recovery window", value: "30s" },
                ].map(s => (
                  <div key={s.label} className="bg-[var(--secondary)] rounded-[var(--radius)] p-3 border border-[var(--border)]">
                    <div className="text-[10px] text-[var(--muted-foreground)] mb-1">{s.label}</div>
                    <div className="mono text-sm font-medium text-[var(--foreground)]">{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Failure bar */}
              <div className="mt-4">
                <div className="text-[10px] text-[var(--muted-foreground)] mb-1.5">Failure threshold progress</div>
                <div className="h-1.5 bg-[var(--muted)] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      failureCount >= 5 ? "bg-red-500" : failureCount >= 3 ? "bg-amber-500" : "bg-green-500"
                    }`}
                    style={{ width: `${(failureCount / 5) * 100}%` }}
                  />
                </div>
              </div>

              {/* Event history */}
              {events.length > 0 && (
                <div className="mt-4 pt-4 border-t border-[var(--border)]">
                  <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Event History</div>
                  <div className="flex flex-col gap-0 max-h-40 overflow-y-auto">
                    {[...events].reverse().map((e, i) => (
                      <div key={i} className="flex items-center gap-3 py-1.5 border-b border-[var(--border)] last:border-0">
                        <span className="mono text-[10px] text-[var(--muted-foreground)] flex-shrink-0">{e.time}</span>
                        <Badge
                          variant={e.state === "closed" ? "success" : e.state === "half-open" ? "warning" : "error"}
                          className="mono text-[9px] flex-shrink-0"
                        >
                          {e.state.toUpperCase()}
                        </Badge>
                        <span className="text-[10px] text-[var(--muted-foreground)] truncate">{e.event}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {events.length === 0 && (
                <div className="mt-4 pt-4 border-t border-[var(--border)] text-xs text-[var(--muted-foreground)]">No events recorded — circuit stable.</div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
