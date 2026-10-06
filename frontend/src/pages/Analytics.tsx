import React, { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell
} from "recharts";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { fetchTelemetrySummary, type TelemetrySummary } from "../api";

const TIME_WINDOWS = ["1h", "6h", "24h", "7d"] as const;
type TW = typeof TIME_WINDOWS[number];

const PROVIDER_COLORS = [
  "#2563EB", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4", "#ec4899",
];

function ChartCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-4">
        <div className="text-sm font-medium text-[var(--foreground)]">{title}</div>
        {subtitle && <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{subtitle}</div>}
      </div>
      {children}
    </Card>
  );
}

const tooltipStyle = {
  contentStyle: {
    background: "var(--card)",
    border: "1px solid var(--border)",
    borderRadius: "6px",
    fontSize: 11,
    color: "var(--foreground)",
  },
  cursor: { fill: "var(--secondary)" },
};

function StatRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[var(--border)] last:border-0 text-xs">
      <span className="text-[var(--muted-foreground)]">{label}</span>
      <div className="text-right">
        <div className="mono font-medium text-[var(--foreground)]">{value}</div>
        {sub && <div className="text-[var(--muted-foreground)]">{sub}</div>}
      </div>
    </div>
  );
}

export function Analytics() {
  const [window, setWindow] = useState<TW>("1h");
  const [summary, setSummary] = useState<TelemetrySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTelemetrySummary(window);
      setSummary(data);
    } catch {
      setError("Failed to load analytics. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [window]);

  useEffect(() => { refresh(); }, [refresh]);

  // Build provider bar chart data from real stats
  const providerBarData = summary
    ? Object.entries(summary.provider_stats).map(([slug, stats]) => ({
        name: slug,
        requests: stats.total,
        success: stats.successful,
        avg_latency: Math.round(stats.avg_latency_ms),
      }))
    : [];

  // Build failure type data
  const failureData = summary
    ? Object.entries(summary.failure_types).map(([type, count]) => ({
        name: type.replace(/_/g, " "),
        count,
      }))
    : [];

  // Build success/failure split
  const splitData = summary && summary.total_requests > 0
    ? [
        { name: "Success", value: summary.successful_requests },
        { name: "Failed", value: summary.failed_requests },
      ]
    : [];

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Analytics"
        description="Real-time gateway analytics from persisted telemetry."
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center border border-[var(--border)] rounded-[var(--radius)] overflow-hidden">
              {TIME_WINDOWS.map(t => (
                <button
                  key={t}
                  onClick={() => setWindow(t)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${window === t ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"}`}
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
        <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4 text-sm text-red-400">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-sm text-[var(--muted-foreground)]">
          Loading analytics…
        </div>
      ) : !summary || summary.total_requests === 0 ? (
        <Card className="p-12 text-center">
          <div className="text-sm font-medium text-[var(--foreground)] mb-2">No Data Yet</div>
          <div className="text-xs text-[var(--muted-foreground)]">
            Make some requests via the Playground to see real analytics here.
          </div>
        </Card>
      ) : (
        <>
          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
            <Card className="p-5">
              <div className="text-xs text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Request Summary</div>
              <StatRow label="Total Requests" value={String(summary.total_requests)} />
              <StatRow label="Successful" value={String(summary.successful_requests)} sub={`${summary.success_rate ?? 0}%`} />
              <StatRow label="Failed" value={String(summary.failed_requests)} sub={`${summary.error_rate ?? 0}%`} />
            </Card>
            <Card className="p-5">
              <div className="text-xs text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Latency</div>
              <StatRow label="Average" value={`${Math.round(summary.avg_latency_ms)}ms`} />
              <StatRow label="p95" value={`${Math.round(summary.p95_latency_ms)}ms`} />
              <StatRow label="Total tokens" value={summary.total_tokens_used.toLocaleString()} />
            </Card>
            <Card className="p-5">
              <div className="text-xs text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Resilience</div>
              <StatRow label="Total Retries" value={String(summary.total_retries)} />
              <StatRow label="Fallback Activations" value={String(summary.total_fallbacks)} />
              <StatRow
                label="Cache Hit Rate"
                value={summary.cache_hit_rate != null ? `${summary.cache_hit_rate}%` : "N/A"}
                sub={`${summary.cache_hits} hits / ${summary.cache_misses} misses`}
              />
            </Card>
          </div>

          {/* Provider distribution chart */}
          {providerBarData.length > 0 && (
            <ChartCard title="Provider Request Distribution" subtitle="Total requests per provider in this window">
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={providerBarData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <Tooltip {...tooltipStyle} />
                    <Bar dataKey="requests" radius={[3, 3, 0, 0]}>
                      {providerBarData.map((_, i) => (
                        <Cell key={i} fill={PROVIDER_COLORS[i % PROVIDER_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          )}

          {/* Avg latency per provider */}
          {providerBarData.length > 0 && (
            <ChartCard title="Average Latency by Provider" subtitle="Milliseconds">
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={providerBarData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <Tooltip {...tooltipStyle} />
                    <Bar dataKey="avg_latency" name="avg latency ms" radius={[3, 3, 0, 0]}>
                      {providerBarData.map((_, i) => (
                        <Cell key={i} fill={PROVIDER_COLORS[i % PROVIDER_COLORS.length]} opacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          )}

          {/* Failure types */}
          {failureData.length > 0 && (
            <ChartCard title="Failure Type Distribution" subtitle="Count of each failure kind">
              <div style={{ height: 180 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={failureData} layout="vertical" margin={{ top: 0, right: 0, left: 60, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <Tooltip {...tooltipStyle} />
                    <Bar dataKey="count" fill="#ef4444" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          )}
        </>
      )}
    </div>
  );
}
