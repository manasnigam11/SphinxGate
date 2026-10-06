import React, { useState, useEffect, useCallback } from "react";
import { Badge, Button, Card, StatusIndicator, SectionHeader } from "../components/ui";
import {
  fetchProviderHealth,
  fetchCircuitStates,
  type ProviderHealthEntry,
  type CircuitSnapshot,
  formatRelativeTime,
} from "../api";

export function ProviderHealth() {
  const [providers, setProviders] = useState<ProviderHealthEntry[]>([]);
  const [circuits, setCircuits] = useState<CircuitSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [health, circ] = await Promise.all([
        fetchProviderHealth(),
        fetchCircuitStates(),
      ]);
      setProviders(health.providers);
      setCircuits(circ.providers);
    } catch {
      setError("Failed to load provider health. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const circuitMap = Object.fromEntries(circuits.map(c => [c.provider, c]));

  const healthy = providers.filter(p => p.health_status === "healthy").length;
  const degraded = providers.filter(p => p.health_status === "degraded").length;
  const down = providers.filter(p => p.health_status === "down").length;
  const overall = down > 0 ? "degraded" : degraded > 0 ? "degraded" : "healthy";

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Provider Health"
        description="Real-time health monitoring across all configured API providers."
        actions={
          <Button variant="outline" size="sm" onClick={refresh}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            Refresh
          </Button>
        }
      />

      {error && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4 text-sm text-red-400">{error}</div>
      )}

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
              {loading ? "LOADING" : overall.toUpperCase()}
            </div>
            <div className="text-xs text-[var(--muted-foreground)] mt-1">
              {providers.length} providers configured
              {down > 0 && ` · ${down} down`}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-6">
            {[
              { label: "Healthy", count: healthy, color: "text-green-500" },
              { label: "Degraded", count: degraded, color: "text-amber-500" },
              { label: "Down", count: down, color: "text-red-400" },
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
      {loading ? (
        <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">Loading provider data…</div>
      ) : (
        <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
          {providers.map(p => {
            const circuit = circuitMap[p.slug] ?? { state: p.circuit_state, failure_count: p.failure_count };
            const stats = p.recent_stats ?? {};
            const totalReqs = stats.total_requests ?? 0;
            const successReqs = stats.successful_requests ?? 0;
            const successPct = totalReqs > 0 ? Math.round((successReqs / totalReqs) * 100) : null;

            return (
              <Card key={p.slug} className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-[var(--secondary)] border border-[var(--border)] flex items-center justify-center text-sm font-bold text-[var(--foreground)]">
                      {p.display_name.charAt(0)}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-[var(--foreground)]">{p.display_name}</div>
                      <div className="text-[10px] text-[var(--muted-foreground)] mono">{p.slug}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <StatusIndicator
                      status={p.health_status === "unknown" ? "degraded" : p.health_status as "healthy" | "degraded" | "down"}
                    />
                    <Badge variant={
                      p.health_status === "healthy" ? "success" :
                      p.health_status === "degraded" ? "warning" :
                      p.health_status === "down" ? "error" : "muted"
                    }>
                      {p.health_status.toUpperCase()}
                    </Badge>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  {/* Active Health Block */}
                  <div className="bg-[var(--secondary)] rounded-[var(--radius)] p-3 border border-[var(--border)]">
                    <div className="text-[10px] text-[var(--muted-foreground)] mb-2 uppercase tracking-wide">Active Health Probe</div>
                    <div className="flex flex-col gap-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">Status</span>
                        <span className={`font-medium ${
                          p.active_health?.state === "healthy" ? "text-green-500" :
                          p.active_health?.state === "degraded" ? "text-amber-500" :
                          p.active_health?.state === "unhealthy" ? "text-red-400" : "text-[var(--foreground)]"
                        }`}>{p.active_health?.state?.toUpperCase() || "UNKNOWN"}</span>
                      </div>
                      {p.active_health?.state !== "healthy" && p.active_health?.last_failure_reason && (
                        <div className="text-red-400 text-[11px] leading-tight mb-1 truncate" title={p.active_health.last_failure_reason}>
                          {p.active_health.last_failure_reason}
                        </div>
                      )}
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">Last Checked</span>
                        <span className="mono">{p.active_health?.last_checked_at ? formatRelativeTime(p.active_health.last_checked_at) : "Never"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">Latency</span>
                        <span className="mono">{p.active_health?.probe_latency_ms ? `${Math.round(p.active_health.probe_latency_ms)}ms` : "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">Success / Fail</span>
                        <span className="mono text-[var(--foreground)]">{p.active_health?.consecutive_successes || 0} / {p.active_health?.consecutive_failures || 0}</span>
                      </div>
                    </div>
                  </div>

                  {/* Circuit Breaker Block */}
                  <div className="bg-[var(--secondary)] rounded-[var(--radius)] p-3 border border-[var(--border)] flex flex-col">
                    <div className="text-[10px] text-[var(--muted-foreground)] mb-2 uppercase tracking-wide">Circuit Breaker</div>
                    <div className="flex flex-col gap-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">State</span>
                        <span className={`font-medium ${
                          circuit.state === "closed" ? "text-green-500" : circuit.state === "half-open" ? "text-amber-500" : "text-red-400"
                        }`}>{circuit.state.toUpperCase()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">Failures</span>
                        <span className="mono">{circuit.failure_count} / {p.failure_threshold || 5}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--muted-foreground)]">Traffic</span>
                        <span className="mono">{totalReqs} reqs/1h</span>
                      </div>
                    </div>
                    {/* Failure bar */}
                    <div className="mt-auto pt-3">
                      <div className="h-1.5 bg-[var(--muted)] rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            circuit.failure_count >= (p.failure_threshold || 5) ? "bg-red-500" :
                            circuit.failure_count > 0 ? "bg-amber-500" : "bg-green-500"
                          }`}
                          style={{ width: `${Math.min((circuit.failure_count / (p.failure_threshold || 5)) * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Footer Keys/Time row */}
                <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
                  <span className="flex items-center gap-1">
                    {p.requires_api_key
                      ? p.configured
                        ? <><span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" /> Key configured</>
                        : <><span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" /> No API key</>
                      : <><span className="w-1.5 h-1.5 rounded-full bg-blue-500 inline-block" /> Public API</>
                    }
                  </span>
                  {p.active_health?.last_success_at ? (
                    <span>Last OK: {formatRelativeTime(p.active_health.last_success_at)}</span>
                  ) : p.active_health?.last_failure_at ? (
                    <span className="text-red-400">Last Fail: {formatRelativeTime(p.active_health.last_failure_at)}</span>
                  ) : null}
                </div>
              </Card>
            );
          })}
          {providers.length === 0 && (
            <div className="col-span-2 py-12 text-center text-sm text-[var(--muted-foreground)]">
              No provider data available.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
