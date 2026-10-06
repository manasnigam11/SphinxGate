import React, { useEffect, useState, useCallback } from "react";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import {
  fetchIncidents,
  fetchIncidentSummary,
  acknowledgeIncident,
  investigateIncident,
  resolveIncident,
  formatTimestamp,
  formatRelativeTime,
  type Incident,
  type IncidentSummary,
} from "../api";

function severityVariant(s: string) {
  if (s === "critical") return "error";
  if (s === "high") return "warning";
  if (s === "medium") return "info";
  return "muted";
}

function statusVariant(status: string) {
  if (status === "resolved") return "success";
  if (status === "acknowledged" || status === "investigating") return "warning";
  return "error";
}

function IncidentDetail({
  incident: initialIncident,
  onBack,
  onUpdate,
}: {
  incident: Incident;
  onBack: () => void;
  onUpdate: () => void;
}) {
  const [incident, setIncident] = useState<Incident>(initialIncident);
  const [actionLoading, setActionLoading] = useState(false);
  const [resolveNote, setResolveNote] = useState("");
  const [showResolveInput, setShowResolveInput] = useState(false);

  const handleAction = async (action: "acknowledge" | "investigate" | "resolve") => {
    setActionLoading(true);
    try {
      let result;
      if (action === "acknowledge") {
        result = await acknowledgeIncident(incident.incident_id);
      } else if (action === "investigate") {
        result = await investigateIncident(incident.incident_id);
      } else if (action === "resolve") {
        result = await resolveIncident(incident.incident_id, resolveNote);
        setShowResolveInput(false);
      }
      if (result) {
        setIncident(result.incident);
        onUpdate();
      }
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to perform action");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors cursor-pointer"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="mono text-sm text-[var(--muted-foreground)]">{incident.incident_id}</span>
            <Badge variant={severityVariant(incident.severity) as any}>{incident.severity.toUpperCase()}</Badge>
            <Badge variant={statusVariant(incident.status) as any}>
              {incident.status.charAt(0).toUpperCase() + incident.status.slice(1)}
            </Badge>
            {incident.fault_injected && (
              <Badge variant="muted" dot>FAULT INJECTED</Badge>
            )}
          </div>
          <h1 className="text-xl font-semibold text-[var(--foreground)] mt-1">{incident.title}</h1>
          <div className="text-xs text-[var(--muted-foreground)] mt-1">
            {incident.provider_display_name} · Started {formatTimestamp(incident.started_at)}
            {incident.duration_seconds !== null ? ` · Duration: ${incident.duration_seconds}s` : ""}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2">
          {incident.status === "open" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleAction("acknowledge")}
              disabled={actionLoading}
            >
              Acknowledge
            </Button>
          )}
          {(incident.status === "open" || incident.status === "acknowledged") && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleAction("investigate")}
              disabled={actionLoading}
            >
              Investigate
            </Button>
          )}
          {incident.status !== "resolved" && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowResolveInput(!showResolveInput)}
              disabled={actionLoading}
            >
              Resolve
            </Button>
          )}
        </div>
      </div>

      {showResolveInput && (
        <Card className="p-4 bg-[var(--secondary)] flex gap-3 items-center">
          <input
            type="text"
            className="flex-1 text-sm bg-[var(--background)] border border-[var(--border)] rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            placeholder="Resolution note (optional)"
            value={resolveNote}
            onChange={(e) => setResolveNote(e.target.value)}
          />
          <Button variant="primary" size="sm" onClick={() => handleAction("resolve")} disabled={actionLoading}>
            Confirm Resolve
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setShowResolveInput(false)}>
            Cancel
          </Button>
        </Card>
      )}

      <div className="grid grid-cols-4 gap-4 max-lg:grid-cols-2">
        {[
          { label: "Errors", value: incident.error_count.toLocaleString() },
          { label: "Affected Requests", value: incident.affected_count.toLocaleString() },
          { label: "Retries", value: incident.retry_count.toLocaleString() },
          { label: "Fallbacks", value: incident.fallback_count.toLocaleString() },
        ].map(s => (
          <Card key={s.label} className="p-4">
            <div className="text-xs text-[var(--muted-foreground)] mb-1.5">{s.label}</div>
            <div className="mono text-xl font-semibold text-[var(--foreground)]">{s.value}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5">
        <Card className="p-5">
          <div className="text-sm font-semibold text-[var(--foreground)] mb-4">Incident Timeline</div>
          <div className="flex flex-col gap-0">
            {incident.timeline.map((e, i) => (
              <div key={i} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1 ${
                    e.event_type === "detection" ? "bg-amber-500" :
                    e.event_type === "action" ? "bg-[var(--primary)]" :
                    e.event_type === "recovery" ? "bg-green-500" :
                    e.event_type === "resolution" ? "bg-green-500" :
                    "bg-[var(--muted-foreground)]"
                  }`} />
                  {i < incident.timeline.length - 1 && <div className="w-px flex-1 bg-[var(--border)] my-1" />}
                </div>
                <div className="pb-4 flex-1">
                  <div className="flex items-center gap-3">
                    <span className="mono text-xs text-[var(--muted-foreground)] flex-shrink-0">
                      {formatTimestamp(e.timestamp).split(", ")[1]}
                    </span>
                    <span className="text-sm text-[var(--foreground)]">{e.event}</span>
                    <Badge
                      variant={
                        e.event_type === "detection" ? "warning" :
                        e.event_type === "action" ? "info" :
                        e.event_type === "resolution" || e.event_type === "recovery" ? "success" : "muted"
                      }
                      className="ml-auto flex-shrink-0 text-[10px]"
                    >
                      {e.event_type}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

export function Incidents() {
  const [selected, setSelected] = useState<Incident | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [summary, setSummary] = useState<IncidentSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [incRes, sumRes] = await Promise.all([
        fetchIncidents(),
        fetchIncidentSummary(),
      ]);
      setIncidents(incRes.incidents);
      setSummary(sumRes);
    } catch (e) {
      console.error("Failed to load incidents", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (selected) {
    return <IncidentDetail incident={selected} onBack={() => setSelected(null)} onUpdate={loadData} />;
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Incidents"
        description="Track, investigate, and resolve provider incidents."
        actions={
          <div className="flex items-center gap-2">
            {summary && (
              <Badge variant={summary.needs_attention > 0 ? "error" : "success"} dot>
                {summary.needs_attention} Needs Attention
              </Badge>
            )}
          </div>
        }
      />

      {loading && incidents.length === 0 ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-6 h-6 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
        </div>
      ) : incidents.length === 0 ? (
        <Card className="p-12 flex flex-col items-center justify-center text-center">
          <svg className="w-12 h-12 text-[var(--muted-foreground)] mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-lg font-medium text-[var(--foreground)]">No Incidents</div>
          <div className="text-sm text-[var(--muted-foreground)] mt-1">
            All systems are running smoothly.
          </div>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {incidents.map(inc => (
            <Card
              key={inc.incident_id}
              className="p-5 cursor-pointer hover:border-[var(--accent)]/30 transition-colors"
              onClick={() => setSelected(inc)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="mono text-xs text-[var(--muted-foreground)]">{inc.incident_id}</span>
                    <Badge variant={severityVariant(inc.severity) as any}>{inc.severity.toUpperCase()}</Badge>
                    <Badge variant={statusVariant(inc.status) as any}>
                      {inc.status.charAt(0).toUpperCase() + inc.status.slice(1)}
                    </Badge>
                    {inc.fault_injected && <Badge variant="muted" dot>FAULT</Badge>}
                  </div>
                  <div className="text-sm font-semibold text-[var(--foreground)] mb-1">{inc.title}</div>
                  <div className="text-xs text-[var(--muted-foreground)]">
                    {inc.provider_display_name} · {formatRelativeTime(inc.started_at)}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  {inc.duration_seconds !== null && (
                    <span className="mono text-xs text-[var(--muted-foreground)]">{inc.duration_seconds}s</span>
                  )}
                  <div className="grid grid-cols-2 gap-4 text-right">
                    <div>
                      <div className="mono text-sm font-semibold text-[var(--foreground)]">{inc.affected_count.toLocaleString()}</div>
                      <div className="text-[10px] text-[var(--muted-foreground)]">affected</div>
                    </div>
                    <div>
                      <div className="mono text-sm font-semibold text-red-400">{inc.error_count.toLocaleString()}</div>
                      <div className="text-[10px] text-[var(--muted-foreground)]">errors</div>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
