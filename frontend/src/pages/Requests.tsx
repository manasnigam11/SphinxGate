import React, { useState } from "react";
import { Badge, Button, Card, Input, SectionHeader } from "../components/ui";
import { REQUESTS } from "../data/mock";
import type { Request } from "../types";

function statusVariant(s: string): "success" | "error" | "warning" | "muted" {
  if (s === "success") return "success";
  if (s === "timeout" || s === "error") return "error";
  if (s === "rate_limited") return "warning";
  return "muted";
}

function RequestDrawer({ req, onClose }: { req: Request; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-[480px] bg-[var(--card)] border-l border-[var(--border)] flex flex-col overflow-hidden animate-fade-in">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div>
            <div className="text-sm font-semibold text-[var(--foreground)] mono">{req.id}</div>
            <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{req.timestamp}</div>
          </div>
          <button onClick={onClose} className="p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)] rounded cursor-pointer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
          {/* Status */}
          <div className="flex items-center gap-3">
            <Badge variant={statusVariant(req.status)} className="uppercase">{req.status.replace("_", " ")}</Badge>
            <span className="mono text-xs text-[var(--foreground)]">{req.latency > 0 ? `${req.latency}ms` : "—"}</span>
            <Badge variant="muted" className="mono text-[10px]">{req.environment}</Badge>
          </div>

          {/* Error state */}
          {req.error && (
            <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4">
              <div className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">
                {req.error === "upstream_timeout" ? "Upstream Timeout" :
                 req.error === "provider_down" ? "Provider Down" :
                 req.error === "rate_limit_exceeded" ? "Rate Limit Exceeded" : req.error}
              </div>
              {req.error === "upstream_timeout" && <p className="text-xs text-[var(--muted-foreground)]">Provider did not respond within 5000ms.</p>}
              {req.error === "provider_down" && <p className="text-xs text-[var(--muted-foreground)]">Provider is unreachable. Circuit breaker is open.</p>}
              <div className="flex flex-col gap-1.5 mt-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[var(--muted-foreground)]">Retry attempts</span>
                  <span className="mono text-[var(--foreground)]">{req.retries} / 2</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[var(--muted-foreground)]">Circuit breaker</span>
                  <Badge variant={req.circuitState === "open" ? "error" : "warning"} className="mono text-[10px]">
                    {req.circuitState?.toUpperCase()}
                  </Badge>
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <Button variant="outline" size="sm">View in Logs</Button>
                <Button variant="secondary" size="sm">Analyze with AI</Button>
              </div>
            </div>
          )}

          {/* Metadata */}
          <div>
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Request Metadata</div>
            <div className="flex flex-col gap-2">
              {[
                ["Endpoint", req.endpoint],
                ["Provider", req.provider],
                ["Model", req.model],
                ["Tokens", req.tokens > 0 ? String(req.tokens) : "—"],
                ["Retries", String(req.retries)],
                ["Environment", req.environment],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between py-1.5 border-b border-[var(--border)] last:border-0 text-xs">
                  <span className="text-[var(--muted-foreground)]">{k}</span>
                  <span className="mono text-[var(--foreground)]">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Timeline */}
          <div>
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Request Timeline</div>
            {["Received", "Validated", "Routed", req.status !== "success" ? "Failed" : "Completed"].map((step, i, arr) => (
              <div key={step} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-0.5 ${step === "Failed" ? "bg-red-500" : "bg-[var(--primary)]"}`} />
                  {i < arr.length - 1 && <div className="w-px flex-1 bg-[var(--border)] my-1" />}
                </div>
                <div className="pb-3 text-xs">
                  <div className="font-medium text-[var(--foreground)]">{step}</div>
                  <div className="text-[var(--muted-foreground)] mono">{req.timestamp}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function Requests() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selected, setSelected] = useState<Request | null>(null);

  const filtered = REQUESTS.filter(r => {
    const matchSearch = !search || r.id.includes(search) || r.provider.toLowerCase().includes(search.toLowerCase()) || r.model.includes(search);
    const matchStatus = statusFilter === "all" || r.status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Requests"
        description="Inspect and debug individual API requests across all providers."
        actions={
          <Button variant="outline" size="sm">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Export
          </Button>
        }
      />

      <Card>
        {/* Filters */}
        <div className="flex items-center gap-3 p-4 border-b border-[var(--border)]">
          <div className="flex-1">
            <Input
              icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>}
              placeholder="Search request ID, model, provider..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          {["all", "success", "error", "timeout", "rate_limited"].map(f => (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-[var(--radius)] transition-colors cursor-pointer ${statusFilter === f ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"}`}
            >
              {f === "all" ? "All" : f.replace("_", " ").replace(/\b\w/g, l => l.toUpperCase())}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--border)]">
                {["Request ID", "Timestamp", "Provider", "Model", "Status", "Latency", "Tokens", "Retries"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(req => (
                <tr
                  key={req.id}
                  onClick={() => setSelected(req)}
                  className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3 mono text-xs text-[var(--accent)]">{req.id}</td>
                  <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)] whitespace-nowrap">{req.timestamp.split(" ")[1]}</td>
                  <td className="px-4 py-3 text-sm text-[var(--foreground)]">{req.provider}</td>
                  <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">{req.model}</td>
                  <td className="px-4 py-3">
                    <Badge variant={statusVariant(req.status)}>{req.status.replace("_", " ")}</Badge>
                  </td>
                  <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">
                    {req.latency > 0 ? `${req.latency}ms` : "—"}
                  </td>
                  <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">
                    {req.tokens > 0 ? req.tokens.toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">{req.retries}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center py-12 text-sm text-[var(--muted-foreground)]">No requests match your filters.</div>
          )}
        </div>
      </Card>

      {selected && <RequestDrawer req={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
