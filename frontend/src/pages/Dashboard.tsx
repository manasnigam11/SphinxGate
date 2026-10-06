import React, { useState, useEffect, useCallback } from "react";
import { Badge, Button, Card, StatusIndicator, SectionHeader } from "../components/ui";
import {
  fetchTelemetrySummary,
  fetchProviderHealth,
  fetchRecentRequests,
  type TelemetrySummary,
  type ProviderHealthEntry,
  type TelemetryRequest,
  formatRelativeTime,
  healthStatusVariant,
} from "../api";

const TIME_RANGES = ["1h", "6h", "24h", "7d", "30d"] as const;
type TimeRange = typeof TIME_RANGES[number];

function MetricCard({ title, value, sub, variant = "neutral" }: {
  title: string; value: string; sub?: string; variant?: "positive" | "negative" | "neutral";
}) {
  const color = variant === "positive" ? "#22c55e" : variant === "negative" ? "#ef4444" : "#2563EB";
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-2xl font-semibold text-[var(--foreground)] mono mb-1">{value}</div>
      {sub && <div className="text-xs text-[var(--muted-foreground)]">{sub}</div>}
    </Card>
  );
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[var(--card)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-xs shadow-lg">
      <div className="text-[var(--muted-foreground)] mb-1">{label}</div>
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-[var(--foreground)] font-medium mono">{typeof p.value === "number" ? p.value.toFixed(0) : p.value}</span>
          <span className="text-[var(--muted-foreground)]">{p.name}</span>
        </div>
      ))}
    </div>
  );
}

export function Dashboard() {
  const [timeRange, setTimeRange] = useState<TimeRange>("1h");
  const [summary, setSummary] = useState<TelemetrySummary | null>(null);
  const [providers, setProviders] = useState<ProviderHealthEntry[]>([]);
  const [recentRequests, setRecentRequests] = useState<TelemetryRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, healthData, requestsData] = await Promise.all([
        fetchTelemetrySummary(timeRange),
        fetchProviderHealth(),
        fetchRecentRequests(6),
      ]);
      setSummary(summaryData);
      setProviders(healthData.providers);
      setRecentRequests(requestsData.requests);
    } catch (e) {
      setError("Failed to load dashboard data. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => { refresh(); }, [refresh]);

  const providerStatusVariant = (s: string) => s === "healthy" ? "success" : s === "degraded" ? "warning" : s === "unknown" ? "muted" : "error";

  const successRate = summary?.success_rate != null
    ? `${summary.success_rate}%`
    : (loading ? "—" : "0%");

  const errorRate = summary?.error_rate != null
    ? `${summary.error_rate}%`
    : (loading ? "—" : "0%");

  const cacheHitRate = summary?.cache_hit_rate != null
    ? `${summary.cache_hit_rate}%`
    : (loading ? "—" : "N/A");

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Overview"
        description="Live gateway telemetry — requests, providers, and resilience health."
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center border border-[var(--border)] rounded-[var(--radius)] overflow-hidden">
              {TIME_RANGES.map(t => (
                <button
                  key={t}
                  onClick={() => setTimeRange(t)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${timeRange === t ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"}`}
                >
                  {t}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={refresh}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              Refresh
            </Button>
          </div>
        }
      />

      {error && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Metric cards — real data */}
      <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
        <MetricCard
          title="Total Requests"
          value={loading ? "—" : String(summary?.total_requests ?? 0)}
          sub={`Last ${timeRange}`}
        />
        <MetricCard
          title="Success Rate"
          value={successRate}
          sub={`${summary?.successful_requests ?? 0} successful`}
          variant={(summary?.success_rate ?? 100) >= 95 ? "positive" : "negative"}
        />
        <MetricCard
          title="Avg Latency"
          value={loading ? "—" : `${Math.round(summary?.avg_latency_ms ?? 0)}ms`}
          sub={`p95: ${Math.round(summary?.p95_latency_ms ?? 0)}ms`}
        />
        <MetricCard
          title="Cache Hit Rate"
          value={cacheHitRate}
          sub={`${summary?.cache_hits ?? 0} hits / ${summary?.cache_misses ?? 0} misses`}
          variant={(summary?.cache_hit_rate ?? 0) > 0 ? "positive" : "neutral"}
        />
      </div>

      {/* Secondary metrics */}
      <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
        <MetricCard
          title="Error Rate"
          value={errorRate}
          sub={`${summary?.failed_requests ?? 0} failed`}
          variant={(summary?.error_rate ?? 0) > 5 ? "negative" : "positive"}
        />
        <MetricCard
          title="Total Retries"
          value={loading ? "—" : String(summary?.total_retries ?? 0)}
          sub="Automatic retry attempts"
        />
        <MetricCard
          title="Fallbacks Used"
          value={loading ? "—" : String(summary?.total_fallbacks ?? 0)}
          sub="Fallback provider activations"
        />
        <MetricCard
          title="Tokens Used"
          value={loading ? "—" : (summary?.total_tokens_used ?? 0).toLocaleString()}
          sub="LLM tokens (all providers)"
        />
      </div>

      {/* Provider health — REAL data */}
      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between">
            <div className="text-sm font-medium text-[var(--foreground)]">Provider Health</div>
            <Badge
              variant={providers.some(p => p.health_status === "down") ? "error" : providers.some(p => p.health_status === "degraded") ? "warning" : "success"}
              dot
            >
              {providers.some(p => p.health_status === "down") ? "Issues Detected" : providers.some(p => p.health_status === "degraded") ? "Degraded" : providers.length === 0 ? "No Data" : "All Healthy"}
            </Badge>
          </div>
          {loading ? (
            <div className="p-5 text-xs text-[var(--muted-foreground)]">Loading provider data…</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--border)]">
                    {["Provider", "Status", "Circuit", "Requests", "Avg Latency"].map(h => (
                      <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {providers.map(p => (
                    <tr key={p.slug} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors">
                      <td className="px-4 py-3 text-sm font-medium text-[var(--foreground)]">{p.display_name}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <StatusIndicator status={p.health_status === "unknown" ? "degraded" : p.health_status as "healthy" | "degraded" | "down"} />
                          <Badge variant={providerStatusVariant(p.health_status) as "success" | "warning" | "error" | "muted"}>
                            {p.health_status.charAt(0).toUpperCase() + p.health_status.slice(1)}
                          </Badge>
                        </div>
                      </td>
                      <td className="px-4 py-3 mono text-xs">
                        <span className={p.circuit_state === "closed" ? "text-green-500" : p.circuit_state === "half-open" ? "text-amber-500" : "text-red-400"}>
                          {p.circuit_state.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">
                        {p.recent_stats?.total_requests ?? 0}
                      </td>
                      <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">
                        {p.recent_stats?.avg_latency_ms ? `${Math.round(p.recent_stats.avg_latency_ms)}ms` : "—"}
                      </td>
                    </tr>
                  ))}
                  {providers.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-xs text-[var(--muted-foreground)] text-center">
                        No provider data yet — make some requests via the Playground.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Recent requests — REAL data */}
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between">
            <div className="text-sm font-medium text-[var(--foreground)]">Recent Requests</div>
            <Badge variant="muted">{recentRequests.length} shown</Badge>
          </div>
          {loading ? (
            <div className="p-5 text-xs text-[var(--muted-foreground)]">Loading…</div>
          ) : recentRequests.length === 0 ? (
            <div className="p-5 text-xs text-[var(--muted-foreground)]">
              No requests yet — use the Playground to send some.
            </div>
          ) : (
            <div className="divide-y divide-[var(--border)]">
              {recentRequests.map(req => (
                <div key={req.request_id} className="px-5 py-3 hover:bg-[var(--secondary)] transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="mono text-xs text-[var(--muted-foreground)] flex-shrink-0">{req.request_id}</span>
                      <span className="text-xs text-[var(--foreground)] truncate">{req.provider_display_name}</span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {req.cache_hit && <Badge variant="info" className="text-[9px]">CACHE</Badge>}
                      <Badge variant={req.success ? "success" : "error"} className="text-[9px]">
                        {req.success ? "OK" : req.error_type ?? "ERR"}
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-[var(--muted-foreground)]">
                    <span>{req.latency_ms}ms</span>
                    <span>·</span>
                    <span>{req.circuit_state}</span>
                    <span>·</span>
                    <span>{formatRelativeTime(req.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Failure distribution */}
      {summary && Object.keys(summary.failure_types).length > 0 && (
        <Card className="p-5">
          <div className="text-sm font-medium text-[var(--foreground)] mb-4">Failure Distribution</div>
          <div className="flex flex-wrap gap-3">
            {Object.entries(summary.failure_types).map(([type, count]) => (
              <div key={type} className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] px-3 py-2">
                <div className="text-xs font-mono text-red-400">{type}</div>
                <div className="text-sm font-semibold text-[var(--foreground)] mono">{count}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
