import React, { useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from "recharts";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { REQUEST_VOLUME, LATENCY_PERCENTILES, PROVIDERS } from "../data/mock";

const DATE_RANGES = ["24h", "7d", "30d", "90d"];

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

const chartTooltipStyle = {
  contentStyle: {
    background: "var(--card)",
    border: "1px solid var(--border)",
    borderRadius: "6px",
    fontSize: 11,
    color: "var(--foreground)",
  },
  cursor: { stroke: "var(--border)", strokeWidth: 1 },
};

const PROVIDER_COMPARISON = PROVIDERS.map(p => ({
  name: p.name,
  requests: p.requests / 1000,
  success: p.status === "down" ? 0 : p.successRate,
  latency: p.status === "down" ? 0 : p.latency,
}));

const LATENCY_DATA = LATENCY_PERCENTILES.p50.map((d, i) => ({
  t: d.timestamp,
  p50: LATENCY_PERCENTILES.p50[i].value,
  p95: LATENCY_PERCENTILES.p95[i].value,
  p99: LATENCY_PERCENTILES.p99[i].value,
}));

const RETRY_DATA = Array.from({ length: 24 }, (_, i) => ({
  hour: `${i}:00`,
  retries: Math.floor(Math.random() * 50 + 10),
  circuit: Math.floor(Math.random() * 5),
}));

export function Analytics() {
  const [range, setRange] = useState("24h");

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Analytics"
        description="Engineering metrics — request volume, latency distribution, provider comparison, and resilience patterns."
        actions={
          <div className="flex items-center border border-[var(--border)] rounded-[var(--radius)] overflow-hidden">
            {DATE_RANGES.map(r => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${range === r ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"}`}
              >
                {r}
              </button>
            ))}
          </div>
        }
      />

      {/* Top row */}
      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        <ChartCard title="Request Volume" subtitle="Requests per 30-minute window">
          <div style={{ height: 192 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={REQUEST_VOLUME} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="vol" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2563EB" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#2563EB" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="timestamp" tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} interval={11} />
                <YAxis tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} />
                <Tooltip {...chartTooltipStyle} />
                <Area type="monotone" dataKey="value" name="req/min" stroke="#2563EB" strokeWidth={1.5} fill="url(#vol)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard title="Latency Distribution" subtitle="P50 · P95 · P99">
          <div style={{ height: 192 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={LATENCY_DATA.filter((_, i) => i % 3 === 0)} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="t" tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} interval={5} />
                <YAxis tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} />
                <Tooltip {...chartTooltipStyle} formatter={(v: number) => [`${v.toFixed(0)}ms`]} />
                <Legend iconType="plainline" iconSize={16} wrapperStyle={{ fontSize: 10, color: "var(--muted-foreground)" }} />
                <Line type="monotone" dataKey="p50" name="P50" stroke="#2563EB" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="p95" name="P95" stroke="#94A3B8" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="p99" name="P99" stroke="#DC2626" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>

      {/* Provider comparison */}
      <ChartCard title="Provider Comparison" subtitle="Request volume (thousands) vs. success rate by provider">
        <div style={{ height: 208 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={PROVIDER_COMPARISON} margin={{ top: 4, right: 0, left: -20, bottom: 0 }} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <YAxis yAxisId="left" tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 105]} tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} />
              <Tooltip {...chartTooltipStyle} />
              <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 10, color: "var(--muted-foreground)" }} />
              <Bar yAxisId="left" dataKey="requests" name="Requests (k)" fill="#2563EB" radius={[3, 3, 0, 0]} />
              <Bar yAxisId="right" dataKey="success" name="Success %" fill="#94A3B8" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      {/* Retry / circuit breaker */}
      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        <ChartCard title="Retry Frequency" subtitle="Retries triggered per hour">
          <div style={{ height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={RETRY_DATA.slice(0, 16)} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} interval={3} />
                <YAxis tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} />
                <Tooltip {...chartTooltipStyle} />
                <Bar dataKey="retries" name="Retries" fill="#2563EB" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard title="Circuit Breaker Activations" subtitle="Trips per hour across all providers">
          <div style={{ height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={RETRY_DATA.slice(0, 16)} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} interval={3} />
                <YAxis tick={{ fontSize: 9, fill: "var(--muted-foreground)" }} />
                <Tooltip {...chartTooltipStyle} />
                <Bar dataKey="circuit" name="Circuit trips" fill="#DC2626" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
