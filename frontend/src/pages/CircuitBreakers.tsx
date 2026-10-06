import React, { useState, useEffect, useCallback } from "react";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { fetchCircuitStates, fetchProviderTelemetry, type CircuitSnapshot } from "../api";

type CircuitState = "closed" | "half-open" | "open";

function CircuitStateDisplay({ state }: { state: CircuitState }) {
  const config = {
    closed: { label: "CIRCUIT CLOSED", bg: "bg-green-500/5 border-green-500/20", text: "text-green-500", dot: "bg-green-500" },
    "half-open": { label: "HALF OPEN", bg: "bg-amber-500/5 border-amber-500/20", text: "text-amber-500", dot: "bg-amber-500" },
    open: { label: "CIRCUIT OPEN", bg: "bg-red-500/5 border-red-500/20", text: "text-red-400", dot: "bg-red-500" },
  }[state] ?? { label: "UNKNOWN", bg: "bg-[var(--secondary)] border-[var(--border)]", text: "text-[var(--muted-foreground)]", dot: "bg-[var(--muted-foreground)]" };

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-[var(--radius)] border ${config.bg}`}>
      <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${config.dot} ${state !== "closed" ? "animate-pulse" : ""}`} />
      <span className={`mono text-sm font-semibold tracking-wider ${config.text}`}>{config.label}</span>
    </div>
  );
}

export function CircuitBreakers() {
  const [circuits, setCircuits] = useState<CircuitSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCircuitStates();
      setCircuits(data.providers);
      setLastRefresh(new Date());
    } catch {
      setError("Failed to load circuit state. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const openCount = circuits.filter(c => c.state === "open").length;
  const halfOpenCount = circuits.filter(c => c.state === "half-open").length;

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Circuit Breakers"
        description="Real-time circuit breaker state across all configured providers. Auto-refreshes every 5s."
        actions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-[var(--muted-foreground)] mono">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
            <Button variant="outline" size="sm" onClick={refresh}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              Refresh
            </Button>
          </div>
        }
      />

      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Open", count: openCount, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20" },
          { label: "Half-Open", count: halfOpenCount, color: "text-amber-500", bg: "bg-amber-500/5 border-amber-500/20" },
          { label: "Closed", count: circuits.filter(c => c.state === "closed").length, color: "text-green-500", bg: "bg-green-500/5 border-green-500/20" },
        ].map(s => (
          <Card key={s.label} className={`p-5 border ${s.bg}`}>
            <div className={`text-3xl font-semibold mono ${s.color}`}>{loading ? "—" : s.count}</div>
            <div className="text-xs text-[var(--muted-foreground)] mt-1">{s.label} circuits</div>
          </Card>
        ))}
      </div>

      {error && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4 text-sm text-red-400">{error}</div>
      )}

      {loading && circuits.length === 0 ? (
        <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">Loading circuit states…</div>
      ) : (
        <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
          {circuits.map(c => {
            const state = (c.state ?? "closed") as CircuitState;
            const threshold = 5; // from policy defaults

            return (
              <Card key={c.provider} className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="text-sm font-semibold text-[var(--foreground)]">{c.provider}</div>
                  <Badge variant="muted" className="mono text-[10px]">{c.provider}</Badge>
                </div>

                <CircuitStateDisplay state={state} />

                <div className="grid grid-cols-3 gap-3 mt-4">
                  {[
                    { label: "Failure count", value: `${c.failure_count} / ${threshold}` },
                    {
                      label: "Last failure",
                      value: c.last_failure_time
                        ? new Date(c.last_failure_time * 1000).toLocaleTimeString()
                        : "None",
                    },
                    {
                      label: "State since",
                      value: c.last_state_change
                        ? new Date(c.last_state_change * 1000).toLocaleTimeString()
                        : "—",
                    },
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
                        c.failure_count >= threshold ? "bg-red-500" :
                        c.failure_count >= threshold * 0.6 ? "bg-amber-500" : "bg-green-500"
                      }`}
                      style={{ width: `${Math.min((c.failure_count / threshold) * 100, 100)}%` }}
                    />
                  </div>
                </div>

                {/* State description */}
                <div className="mt-4 pt-4 border-t border-[var(--border)] text-xs text-[var(--muted-foreground)]">
                  {state === "closed" && c.failure_count === 0
                    ? "No failures recorded — circuit fully stable."
                    : state === "closed"
                    ? `${c.failure_count} failure(s) recorded but circuit remains closed.`
                    : state === "half-open"
                    ? "Circuit probing recovery — next request is a test probe."
                    : `Circuit OPEN — requests are being blocked. Waiting for recovery window.`}
                </div>
              </Card>
            );
          })}
          {circuits.length === 0 && !loading && (
            <div className="col-span-2 py-12 text-center text-sm text-[var(--muted-foreground)]">
              No circuit state data available — start the backend to see live data.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
