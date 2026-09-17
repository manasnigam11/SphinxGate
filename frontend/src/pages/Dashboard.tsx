import React, { useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Badge, Button, Card, StatusIndicator, SectionHeader } from "../components/ui";
import { METRICS, REQUEST_VOLUME, ERROR_RATE_SERIES, PROVIDERS, INCIDENTS } from "../data/mock";

const TIME_RANGES = ["1h", "6h", "24h", "7d", "30d"];

function MetricCard({ title, value, change, positive, sparkData }: {
  title: string; value: string; change: string; positive: boolean; sparkData: { value: number }[];
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wider">{title}</span>
        <Badge variant={positive ? "success" : "error"} className="text-[10px]">
          {change}
        </Badge>
      </div>
      <div className="text-2xl font-semibold text-[var(--foreground)] mono mb-3">{value}</div>
      <div style={{ height: 40 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={sparkData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`spark-${title}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={positive ? "#22c55e" : "#ef4444"} stopOpacity={0.3} />
                <stop offset="100%" stopColor={positive ? "#22c55e" : "#ef4444"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area type="monotone" dataKey="value" stroke={positive ? "#22c55e" : "#ef4444"} strokeWidth={1.5} fill={`url(#spark-${title})`} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
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
          <span className="text-[var(--foreground)] font-medium mono">{typeof p.value === "number" ? p.value.toFixed(p.name === "errors" ? 1 : 0) : p.value}</span>
          <span className="text-[var(--muted-foreground)]">{p.name === "errors" ? "% error" : "req/min"}</span>
        </div>
      ))}
    </div>
  );
}

export function Dashboard() {
  const [timeRange, setTimeRange] = useState("24h");

  const providerStatusVariant = (s: string) => s === "healthy" ? "success" : s === "degraded" ? "warning" : "error";
  const severityVariant = (s: string) => s === "critical" ? "error" : s === "high" ? "warning" : s === "medium" ? "info" : "muted";

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Overview"
        description="Monitor your API infrastructure, providers, and request health."
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
            <Button variant="outline" size="sm">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              Refresh
            </Button>
          </div>
        }
      />

      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
        <MetricCard title="Total Requests" value={METRICS.totalRequests.value} change={METRICS.totalRequests.change} positive={METRICS.totalRequests.positive} sparkData={METRICS.totalRequests.sparkline} />
        <MetricCard title="Success Rate" value={METRICS.successRate.value} change={METRICS.successRate.change} positive={METRICS.successRate.positive} sparkData={METRICS.successRate.sparkline} />
        <MetricCard title="Avg Latency" value={METRICS.avgLatency.value} change={METRICS.avgLatency.change} positive={METRICS.avgLatency.positive} sparkData={METRICS.avgLatency.sparkline} />
        <MetricCard title="Error Rate" value={METRICS.errorRate.value} change={METRICS.errorRate.change} positive={METRICS.errorRate.positive} sparkData={METRICS.errorRate.sparkline} />
      </div>

      {/* Request performance chart */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className="text-sm font-medium text-[var(--foreground)]">Request Performance</div>
            <div className="text-xs text-[var(--muted-foreground)] mt-0.5">Requests per minute · Error rate overlay</div>
          </div>
          <div className="flex items-center gap-4 text-xs text-[var(--muted-foreground)]">
            <div className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-[#2563EB] inline-block rounded-full" />Requests/min</div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-red-500 inline-block rounded-full" />Error rate %</div>
          </div>
        </div>
        <div style={{ height: 224 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={REQUEST_VOLUME.map((d, i) => ({ ...d, errors: ERROR_RATE_SERIES[i]?.value ?? 0 }))} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="reqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563EB" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#2563EB" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="errGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} interval={7} />
              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} domain={[0, 8]} />
              <Tooltip content={<CustomTooltip />} />
              <Area yAxisId="left" type="monotone" dataKey="value" name="requests" stroke="#2563EB" strokeWidth={1.5} fill="url(#reqGrad)" dot={false} />
              <Area yAxisId="right" type="monotone" dataKey="errors" name="errors" stroke="#ef4444" strokeWidth={1.5} fill="url(#errGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        {/* Provider Health */}
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between">
            <div className="text-sm font-medium text-[var(--foreground)]">Provider Health</div>
            <Badge variant={PROVIDERS.some(p => p.status === "down") ? "error" : PROVIDERS.some(p => p.status === "degraded") ? "warning" : "success"} dot>
              {PROVIDERS.some(p => p.status === "down") ? "Issues Detected" : PROVIDERS.some(p => p.status === "degraded") ? "Degraded" : "All Healthy"}
            </Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  {["Provider", "Status", "Latency", "Success", "Errors"].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PROVIDERS.map(p => (
                  <tr key={p.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors">
                    <td className="px-4 py-3 text-sm font-medium text-[var(--foreground)]">{p.name}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <StatusIndicator status={p.status as "healthy" | "degraded" | "down"} />
                        <Badge variant={providerStatusVariant(p.status) as "success" | "warning" | "error"}>
                          {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                        </Badge>
                      </div>
                    </td>
                    <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">
                      {p.status === "down" ? "—" : `${p.latency}ms`}
                    </td>
                    <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">
                      {p.status === "down" ? "—" : `${p.successRate}%`}
                    </td>
                    <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">
                      {p.status === "down" ? "—" : p.errors.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Recent Incidents */}
        <Card className="overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between">
            <div className="text-sm font-medium text-[var(--foreground)]">Recent Incidents</div>
            <Badge variant="warning" dot>{INCIDENTS.filter(i => i.status !== "resolved").length} Active</Badge>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {INCIDENTS.map(inc => (
              <div key={inc.id} className="px-5 py-3.5 hover:bg-[var(--secondary)] transition-colors cursor-pointer">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="mono text-xs text-[var(--muted-foreground)] flex-shrink-0">{inc.id}</span>
                    <span className="text-sm font-medium text-[var(--foreground)] truncate">{inc.title}</span>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Badge variant={severityVariant(inc.severity) as "error" | "warning" | "info" | "muted"}>
                      {inc.severity.toUpperCase()}
                    </Badge>
                    <Badge variant={inc.status === "resolved" ? "success" : inc.status === "mitigating" ? "warning" : "error"}>
                      {inc.status.charAt(0).toUpperCase() + inc.status.slice(1)}
                    </Badge>
                  </div>
                </div>
                <div className="flex items-center gap-3 mt-1.5 text-xs text-[var(--muted-foreground)]">
                  <span>{inc.provider}</span>
                  <span>·</span>
                  <span>{inc.started.split(" ")[1]}</span>
                  {inc.duration && <><span>·</span><span>{inc.duration}</span></>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
