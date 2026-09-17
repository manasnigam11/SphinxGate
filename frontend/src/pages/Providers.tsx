import React, { useState } from "react";
import { Badge, Button, Card, StatusIndicator, SectionHeader } from "../components/ui";
import { PROVIDERS } from "../data/mock";
import type { Provider } from "../types";

function ProviderDetail({ provider, onBack }: { provider: Provider; onBack: () => void }) {
  const statusVariant = provider.status === "healthy" ? "success" : provider.status === "degraded" ? "warning" : "error";
  const circuitVariant = provider.circuitState === "closed" ? "success" : provider.circuitState === "half-open" ? "warning" : "error";

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors cursor-pointer">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-[var(--foreground)]">{provider.name}</h1>
            <Badge variant={statusVariant}>{provider.status.toUpperCase()}</Badge>
          </div>
          <p className="text-xs text-[var(--muted-foreground)] mono mt-1">{provider.slug}</p>
        </div>
        <Button variant="outline" size="sm">Configure</Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2">
        {[
          { label: "Total Requests", value: provider.requests.toLocaleString(), mono: true },
          { label: "Success Rate", value: provider.status === "down" ? "—" : `${provider.successRate}%`, mono: true },
          { label: "Avg Latency", value: provider.status === "down" ? "—" : `${provider.latency}ms`, mono: true },
          { label: "Availability", value: `${provider.availability}%`, mono: true },
        ].map(s => (
          <Card key={s.label} className="p-4">
            <div className="text-xs text-[var(--muted-foreground)] mb-1.5">{s.label}</div>
            <div className={`text-xl font-semibold text-[var(--foreground)] ${s.mono ? "mono" : ""}`}>{s.value}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-1">
        {/* Models */}
        <Card className="col-span-2 overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--border)] text-sm font-medium text-[var(--foreground)]">Available Models</div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--border)]">
                {["Model", "Context", "Input $/M", "Output $/M", "Status", "Latency"].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {provider.models.map(m => (
                <tr key={m.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors">
                  <td className="px-4 py-3 mono text-xs font-medium text-[var(--foreground)]">{m.name}</td>
                  <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">{(m.contextWindow / 1000).toFixed(0)}k</td>
                  <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">${m.inputCost}</td>
                  <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">${m.outputCost || "—"}</td>
                  <td className="px-4 py-3"><Badge variant={m.status === "healthy" ? "success" : m.status === "degraded" ? "warning" : "error"}>{m.status}</Badge></td>
                  <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">{m.latency > 0 ? `${m.latency}ms` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        {/* Circuit breaker state */}
        <Card className="p-5">
          <div className="text-sm font-medium text-[var(--foreground)] mb-4">Circuit Breaker</div>
          <div className={`inline-flex items-center gap-2 px-3 py-2 rounded-[var(--radius)] border mb-4 ${
            provider.circuitState === "closed" ? "bg-green-500/5 border-green-500/20 text-green-500" :
            provider.circuitState === "half-open" ? "bg-amber-500/5 border-amber-500/20 text-amber-500" :
            "bg-red-500/5 border-red-500/20 text-red-400"
          }`}>
            <StatusIndicator status={provider.circuitState} />
            <span className="text-xs font-semibold uppercase tracking-wider">{provider.circuitState.replace("-", " ")}</span>
          </div>
          <div className="flex flex-col gap-3">
            {[
              { label: "Failure threshold", value: "5 failures" },
              { label: "Recovery window", value: "30s" },
              { label: "Last check", value: provider.lastHealthCheck },
            ].map(r => (
              <div key={r.label} className="flex items-center justify-between text-xs">
                <span className="text-[var(--muted-foreground)]">{r.label}</span>
                <span className="mono text-[var(--foreground)]">{r.value}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

export function Providers() {
  const [selected, setSelected] = useState<Provider | null>(null);

  if (selected) {
    return <ProviderDetail provider={selected} onBack={() => setSelected(null)} />;
  }

  const statusVariant = (s: string) => s === "healthy" ? "success" : s === "degraded" ? "warning" : "error";
  const circuitVariant = (s: string) => s === "closed" ? "success" : s === "half-open" ? "warning" : "error";

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Providers"
        description="Manage connected AI providers, inspect model availability, and configure routing."
        actions={
          <Button variant="primary" size="sm">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add Provider
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 max-xl:grid-cols-1">
        {PROVIDERS.map(p => (
          <Card key={p.id} className="p-5 cursor-pointer hover:border-[var(--accent)]/40 transition-colors" onClick={() => setSelected(p)}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-[var(--secondary)] border border-[var(--border)] flex items-center justify-center text-xs font-bold text-[var(--foreground)]">
                    {p.name.charAt(0)}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-[var(--foreground)]">{p.name}</div>
                    <div className="mono text-[10px] text-[var(--muted-foreground)]">{p.slug}</div>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <Badge variant={statusVariant(p.status) as "success" | "warning" | "error"} dot>{p.status}</Badge>
                <Badge variant={circuitVariant(p.circuitState) as "success" | "warning" | "error"} className="mono text-[10px]">
                  {p.circuitState.toUpperCase()}
                </Badge>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-3">
              {[
                { label: "Requests", value: p.requests > 0 ? (p.requests / 1000).toFixed(0) + "k" : "—" },
                { label: "Success", value: p.status === "down" ? "—" : p.successRate + "%" },
                { label: "Latency", value: p.status === "down" ? "—" : p.latency + "ms" },
                { label: "Models", value: String(p.models.length) },
              ].map(s => (
                <div key={s.label}>
                  <div className="text-[10px] text-[var(--muted-foreground)] mb-0.5">{s.label}</div>
                  <div className="mono text-sm font-medium text-[var(--foreground)]">{s.value}</div>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-center justify-between text-xs text-[var(--muted-foreground)]">
              <span>Last checked {p.lastHealthCheck}</span>
              <span>{p.models.map(m => m.name).join(", ")}</span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
