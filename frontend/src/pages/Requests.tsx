import React, { useState, useEffect, useCallback } from "react";
import { Badge, Button, Card, Input, SectionHeader } from "../components/ui";
import {
  fetchRecentRequests,
  fetchRequestDetail,
  type TelemetryRequest,
  type ResilienceEvent,
  formatTimestamp,
  formatRelativeTime,
} from "../api";

function statusVariant(success: boolean, errorType?: string | null): "success" | "error" | "warning" | "muted" {
  if (success) return "success";
  if (errorType === "gateway_rate_limit") return "warning";
  return "error";
}

function statusLabel(success: boolean, errorType?: string | null): string {
  if (success) return "success";
  if (!errorType) return "error";
  return errorType.replace(/_/g, " ");
}

function RequestDrawer({ req, onClose }: { req: TelemetryRequest; onClose: () => void }) {
  const [detail, setDetail] = useState<TelemetryRequest | null>(null);

  useEffect(() => {
    fetchRequestDetail(req.request_id)
      .then(setDetail)
      .catch(() => setDetail(req));
  }, [req.request_id]);

  const r = detail ?? req;

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-[480px] bg-[var(--card)] border-l border-[var(--border)] flex flex-col overflow-hidden animate-fade-in">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div>
            <div className="text-sm font-semibold text-[var(--foreground)] mono">{r.request_id}</div>
            <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{formatTimestamp(r.timestamp)}</div>
          </div>
          <button onClick={onClose} className="p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)] rounded cursor-pointer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
          {/* Status row */}
          <div className="flex items-center gap-3">
            <Badge variant={statusVariant(r.success, r.error_type)} className="uppercase">
              {statusLabel(r.success, r.error_type)}
            </Badge>
            <span className="mono text-xs text-[var(--foreground)]">{r.latency_ms > 0 ? `${r.latency_ms}ms` : "0ms"}</span>
            {r.cache_hit && <Badge variant="info" className="mono text-[10px]">CACHE HIT</Badge>}
          </div>

          {/* Error state */}
          {!r.success && (
            <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4">
              <div className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">
                {r.error_type ?? "Error"}
              </div>
              {r.error_message && (
                <p className="text-xs text-[var(--muted-foreground)]">{r.error_message}</p>
              )}
              <div className="flex flex-col gap-1.5 mt-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[var(--muted-foreground)]">Retry attempts</span>
                  <span className="mono text-[var(--foreground)]">{r.retry_count}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[var(--muted-foreground)]">Circuit breaker</span>
                  <Badge
                    variant={r.circuit_state === "open" ? "error" : r.circuit_state === "half-open" ? "warning" : "success"}
                    className="mono text-[10px]"
                  >
                    {r.circuit_state.toUpperCase()}
                  </Badge>
                </div>
              </div>
            </div>
          )}

          {/* Request Metadata */}
          <div>
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Request Metadata</div>
            <div className="flex flex-col gap-2">
              {[
                ["Request ID", r.request_id],
                ["Endpoint", r.endpoint],
                ["Provider", r.provider_display_name],
                ["Category", r.provider_category],
                ["Tokens Used", r.tokens_used > 0 ? String(r.tokens_used) : "—"],
                ["Retry Count", String(r.retry_count)],
                ["Fallback Used", r.fallback_used ? "Yes" : "No"],
                ["Cache Hit", r.cache_hit ? "Yes" : "No"],
                ["Circuit State", r.circuit_state],
                ["HTTP Status", String(r.status_code)],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between py-1.5 border-b border-[var(--border)] last:border-0 text-xs">
                  <span className="text-[var(--muted-foreground)]">{k}</span>
                  <span className="mono text-[var(--foreground)]">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Resilience Events */}
          {r.events && r.events.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Resilience Events</div>
              <div className="flex flex-col gap-0">
                {r.events.map((ev, i) => (
                  <div key={i} className="flex items-start gap-2 py-1.5 border-b border-[var(--border)] last:border-0 text-xs">
                    <span className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${
                      ev.event_type.includes("succeeded") || ev.event_type === "circuit_closed" ? "bg-green-500" :
                      ev.event_type.includes("failure") || ev.event_type.includes("exhausted") || ev.event_type === "circuit_opened" ? "bg-red-500" :
                      "bg-amber-500"
                    }`} />
                    <div className="flex-1 min-w-0">
                      <span className="mono text-[var(--accent)]">{ev.event_type}</span>
                      <span className="text-[var(--muted-foreground)] ml-2">{ev.provider_slug}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function Requests() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selected, setSelected] = useState<TelemetryRequest | null>(null);
  const [requests, setRequests] = useState<TelemetryRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRecentRequests(200);
      setRequests(data.requests);
    } catch {
      setError("Failed to load requests. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = requests.filter(r => {
    const matchSearch = !search ||
      r.request_id.includes(search) ||
      r.provider.toLowerCase().includes(search.toLowerCase()) ||
      r.provider_display_name.toLowerCase().includes(search.toLowerCase()) ||
      (r.error_type ?? "").includes(search);
    const matchStatus = statusFilter === "all" ||
      (statusFilter === "success" && r.success) ||
      (statusFilter === "error" && !r.success);
    return matchSearch && matchStatus;
  });

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Requests"
        description="Inspect and debug individual gateway requests from real telemetry."
        actions={
          <Button variant="outline" size="sm" onClick={load}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            Refresh
          </Button>
        }
      />

      {error && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4 text-sm text-red-400">{error}</div>
      )}

      <Card>
        {/* Filters */}
        <div className="flex items-center gap-3 p-4 border-b border-[var(--border)]">
          <div className="flex-1">
            <Input
              icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>}
              placeholder="Search request ID, provider..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          {["all", "success", "error"].map(f => (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-[var(--radius)] transition-colors cursor-pointer ${statusFilter === f ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"}`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        {/* Table */}
        {loading ? (
          <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">Loading telemetry…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  {["Request ID", "Time", "Provider", "Endpoint", "Status", "Latency", "Tokens", "Cache", "Retries"].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(req => (
                  <tr
                    key={req.request_id}
                    onClick={() => setSelected(req)}
                    className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 mono text-xs text-[var(--accent)]">{req.request_id}</td>
                    <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)] whitespace-nowrap">{formatRelativeTime(req.timestamp)}</td>
                    <td className="px-4 py-3 text-sm text-[var(--foreground)]">{req.provider_display_name}</td>
                    <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">{req.endpoint}</td>
                    <td className="px-4 py-3">
                      <Badge variant={statusVariant(req.success, req.error_type)}>
                        {statusLabel(req.success, req.error_type)}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">
                      {req.latency_ms > 0 ? `${req.latency_ms}ms` : "0ms"}
                    </td>
                    <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">
                      {req.tokens_used > 0 ? req.tokens_used.toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {req.cache_hit ? (
                        <Badge variant="info" className="text-[9px]">HIT</Badge>
                      ) : (
                        <span className="text-xs text-[var(--muted-foreground)]">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 mono text-xs text-[var(--foreground)]">{req.retry_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="text-center py-12 text-sm text-[var(--muted-foreground)]">
                {requests.length === 0
                  ? "No requests recorded yet — use the Playground to send some."
                  : "No requests match your filters."}
              </div>
            )}
          </div>
        )}
      </Card>

      {selected && <RequestDrawer req={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
