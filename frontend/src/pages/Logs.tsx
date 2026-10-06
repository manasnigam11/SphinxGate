import React, { useState, useEffect } from "react";
import { Badge, Button, Card, Input, SectionHeader, CodeBlock } from "../components/ui";
import { fetchRecentRequests, TelemetryRequest } from "../api";
import type { LogEntry, LogLevel } from "../types";

const LEVEL_VARIANT: Record<LogLevel, "success" | "warning" | "error" | "muted"> = {
  info: "muted",
  warn: "warning",
  error: "error",
  debug: "muted",
};

const LEVEL_COLOR: Record<LogLevel, string> = {
  info: "text-blue-400",
  warn: "text-amber-500",
  error: "text-red-400",
  debug: "text-[var(--muted-foreground)]",
};

function mapToLogEntry(req: TelemetryRequest): LogEntry {
  let level: LogLevel = "info";
  if (!req.success) {
    level = "error";
  } else if (req.fallback_used || req.retry_count > 0 || req.circuit_state !== "closed") {
    level = "warn";
  }

  const d = new Date(req.timestamp_iso);
  const timeStr = isNaN(d.getTime()) ? req.timestamp_iso : d.toISOString().replace("T", " ").substring(0, 19);

  let lifecycleStr = `HTTP ${req.status_code} ${req.endpoint}`;
  if (req.events && req.events.length > 0) {
    const steps = req.events.map(e => {
      if (e.event_type === "request_started") return "Started";
      if (e.event_type === "request_failed") return `Failed (${e.provider_slug})`;
      if (e.event_type === "retry_attempted") return `Retry (${e.provider_slug})`;
      if (e.event_type === "fallback_attempted") return `Fallback (${e.provider_slug})`;
      if (e.event_type === "request_succeeded") return `Success (${e.provider_slug})`;
      return e.event_type;
    });
    lifecycleStr = steps.join(" → ");
  }

  return {
    id: req.request_id,
    timestamp: timeStr,
    level,
    service: "gateway",
    event: lifecycleStr,
    requestId: req.request_id,
    provider: req.provider_display_name,
    latencyMs: Math.round(req.latency_ms),
    retryCount: req.retry_count,
    message: req.error_message || (req.cache_hit ? "Served from cache" : undefined),
    data: req as any,
  };
}

function LogDetail({ log, onClose }: { log: LogEntry; onClose: () => void }) {
  const json = JSON.stringify({
    timestamp: log.timestamp,
    level: log.level.toUpperCase(),
    service: log.service,
    event: log.event,
    provider: log.provider,
    request_id: log.requestId,
    ...(log.latencyMs !== undefined ? { latency_ms: log.latencyMs } : {}),
    ...(log.retryCount !== undefined ? { retry_count: log.retryCount } : {}),
    ...(log.message ? { message: log.message } : {}),
    raw_data: log.data,
  }, null, 2);

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="w-[520px] bg-[var(--card)] border-l border-[var(--border)] flex flex-col animate-fade-in">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Badge variant={LEVEL_VARIANT[log.level]} className="uppercase mono text-[10px]">{log.level}</Badge>
            <span className="text-sm font-medium text-[var(--foreground)]">{log.event}</span>
          </div>
          <button onClick={onClose} className="p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] rounded cursor-pointer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div className="p-5 flex-1 overflow-auto">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              {[
                ["Service", log.service],
                ["Provider", log.provider],
                ["Request ID", log.requestId],
                ["Timestamp", log.timestamp],
              ].map(([k, v]) => (
                <div key={k}>
                  <div className="text-[10px] text-[var(--muted-foreground)] uppercase tracking-wider mb-1">{k}</div>
                  <div className="mono text-xs text-[var(--foreground)]">{v}</div>
                </div>
              ))}
            </div>
            {log.message && (
              <div className="bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-4 py-3 text-sm text-[var(--foreground)]">
                {log.message}
              </div>
            )}
            <div>
              <div className="text-xs font-medium text-[var(--muted-foreground)] mb-2">Structured Data</div>
              <CodeBlock>{json}</CodeBlock>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Logs() {
  const [search, setSearch] = useState("");
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    fetchRecentRequests(100).then(data => {
      setLogs(data.requests.map(mapToLogEntry));
    }).catch(err => {
      console.error("Failed to fetch logs:", err);
    });
  }, []);

  const filtered = logs.filter(l => {
    const matchSearch = !search || l.event.toLowerCase().includes(search.toLowerCase()) || l.requestId.includes(search) || l.provider.toLowerCase().includes(search.toLowerCase());
    const matchLevel = levelFilter === "all" || l.level === levelFilter;
    return matchSearch && matchLevel;
  });

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Logs"
        description="Structured log stream across all gateway services and providers."
        actions={
          <Button variant="outline" size="sm" onClick={() => {
            fetchRecentRequests(100).then(data => setLogs(data.requests.map(mapToLogEntry)));
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            Refresh Logs
          </Button>
        }
      />

      <Card>
        {/* Filters */}
        <div className="flex items-center gap-3 p-4 border-b border-[var(--border)]">
          <div className="flex-1">
            <Input
              icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>}
              placeholder="Search event, request ID, provider..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1 border border-[var(--border)] rounded-[var(--radius)] overflow-hidden">
            {["all", "error", "warn", "info", "debug"].map(l => (
              <button
                key={l}
                onClick={() => setLevelFilter(l)}
                className={`px-2.5 py-1.5 text-xs font-medium transition-colors cursor-pointer ${levelFilter === l ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]"}`}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Log table */}
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--border)]">
                {["Timestamp", "Level", "Service", "Event", "Request ID", "Provider"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(log => (
                <tr
                  key={log.id}
                  onClick={() => setSelected(log)}
                  className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3 mono text-[10px] text-[var(--muted-foreground)] whitespace-nowrap">{log.timestamp}</td>
                  <td className="px-4 py-3">
                    <span className={`mono text-xs font-semibold uppercase ${LEVEL_COLOR[log.level]}`}>{log.level}</span>
                  </td>
                  <td className="px-4 py-3 mono text-xs text-[var(--muted-foreground)]">{log.service}</td>
                  <td className="px-4 py-3 text-xs text-[var(--foreground)] max-w-xs truncate">{log.event}</td>
                  <td className="px-4 py-3 mono text-xs text-[var(--accent)]">{log.requestId}</td>
                  <td className="px-4 py-3 text-xs text-[var(--foreground)]">{log.provider}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center py-12 text-sm text-[var(--muted-foreground)]">No logs match your filters.</div>
          )}
        </div>
      </Card>

      {selected && <LogDetail log={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
