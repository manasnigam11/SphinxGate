import React, { useState } from "react";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { INCIDENTS } from "../data/mock";
import type { Incident } from "../types";

function severityVariant(s: string) {
  if (s === "critical") return "error";
  if (s === "high") return "warning";
  if (s === "medium") return "info";
  return "muted";
}

function IncidentDetail({ incident, onBack }: { incident: Incident; onBack: () => void }) {
  const [showAI, setShowAI] = useState(false);
  const ai = incident.aiAnalysis;

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors cursor-pointer">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="mono text-sm text-[var(--muted-foreground)]">{incident.id}</span>
            <Badge variant={severityVariant(incident.severity) as "error" | "warning" | "info" | "muted"}>{incident.severity.toUpperCase()}</Badge>
            <Badge variant={incident.status === "resolved" ? "success" : incident.status === "mitigating" ? "warning" : "error"}>
              {incident.status.charAt(0).toUpperCase() + incident.status.slice(1)}
            </Badge>
          </div>
          <h1 className="text-xl font-semibold text-[var(--foreground)] mt-1">{incident.title}</h1>
          <div className="text-xs text-[var(--muted-foreground)] mt-1">{incident.provider} · Started {incident.started.split(" ")[1]}{incident.duration ? ` · Duration: ${incident.duration}` : ""}</div>
        </div>
        {!showAI && (
          <Button variant="primary" size="sm" onClick={() => setShowAI(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg>
            Analyze with AI
          </Button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-2">
        {[
          { label: "Affected Requests", value: incident.affectedRequests.toLocaleString() },
          { label: "Failure Rate", value: `${incident.failureRate}%` },
          { label: "Peak Latency", value: incident.peakLatency > 0 ? `${incident.peakLatency}ms` : "—" },
        ].map(s => (
          <Card key={s.label} className="p-4">
            <div className="text-xs text-[var(--muted-foreground)] mb-1.5">{s.label}</div>
            <div className="mono text-xl font-semibold text-[var(--foreground)]">{s.value}</div>
          </Card>
        ))}
      </div>

      <div className={`grid gap-5 ${showAI && ai ? "grid-cols-2 max-lg:grid-cols-1" : "grid-cols-1"}`}>
        {/* Timeline */}
        <Card className="p-5">
          <div className="text-sm font-semibold text-[var(--foreground)] mb-4">Incident Timeline</div>
          <div className="flex flex-col gap-0">
            {incident.timeline.map((e, i) => (
              <div key={i} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1 ${
                    e.type === "detection" ? "bg-amber-500" :
                    e.type === "action" ? "bg-[var(--primary)]" :
                    e.type === "recovery" ? "bg-green-500" : "bg-[var(--muted-foreground)]"
                  }`} />
                  {i < incident.timeline.length - 1 && <div className="w-px flex-1 bg-[var(--border)] my-1" />}
                </div>
                <div className="pb-4 flex-1">
                  <div className="flex items-center gap-3">
                    <span className="mono text-xs text-[var(--muted-foreground)] flex-shrink-0">{e.timestamp}</span>
                    <span className="text-sm text-[var(--foreground)]">{e.event}</span>
                    <Badge
                      variant={e.type === "detection" ? "warning" : e.type === "action" ? "info" : e.type === "recovery" ? "success" : "muted"}
                      className="ml-auto flex-shrink-0 text-[10px]"
                    >
                      {e.type}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* AI Analysis */}
        {showAI && ai && (
          <div className="flex flex-col gap-4 animate-fade-in">
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-6 h-6 rounded-md bg-[var(--accent)]/10 border border-[var(--accent)]/20 flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg>
                </div>
                <div className="text-sm font-semibold text-[var(--foreground)]">Incident Analysis</div>
                <Badge variant="info" className="ml-auto">{ai.confidence}% confidence</Badge>
              </div>

              <p className="text-sm text-[var(--muted-foreground)] leading-relaxed mb-4">{ai.summary}</p>

              <div className="flex flex-col gap-3">
                <div>
                  <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Observed Patterns</div>
                  {ai.observedPatterns.map((p, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-[var(--foreground)] py-1">
                      <span className="text-[var(--accent)] mt-px">•</span>{p}
                    </div>
                  ))}
                </div>
                <div className="pt-3 border-t border-[var(--border)]">
                  <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Likely Cause</div>
                  <p className="text-xs text-[var(--foreground)]">{ai.likelyCause}</p>
                </div>
                <div className="pt-3 border-t border-[var(--border)]">
                  <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Actions Taken</div>
                  {ai.actionsTaken.map((a, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-green-500 py-0.5">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                      {a}
                    </div>
                  ))}
                </div>
                <div className="pt-3 border-t border-[var(--border)]">
                  <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Recommendations</div>
                  {ai.recommendations.map((r, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs py-1">
                      <span className="text-amber-500 flex-shrink-0 mt-px">→</span>
                      <span className="text-[var(--foreground)]">{r}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

export function Incidents() {
  const [selected, setSelected] = useState<Incident | null>(null);

  if (selected) return <IncidentDetail incident={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Incidents"
        description="Track, investigate, and resolve provider incidents."
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="error" dot>{INCIDENTS.filter(i => i.status !== "resolved").length} Active</Badge>
          </div>
        }
      />

      <div className="flex flex-col gap-3">
        {INCIDENTS.map(inc => (
          <Card
            key={inc.id}
            className="p-5 cursor-pointer hover:border-[var(--accent)]/30 transition-colors"
            onClick={() => setSelected(inc)}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2">
                  <span className="mono text-xs text-[var(--muted-foreground)]">{inc.id}</span>
                  <Badge variant={severityVariant(inc.severity) as "error" | "warning" | "info" | "muted"}>{inc.severity.toUpperCase()}</Badge>
                  <Badge variant={inc.status === "resolved" ? "success" : inc.status === "mitigating" ? "warning" : "error"}>
                    {inc.status.charAt(0).toUpperCase() + inc.status.slice(1)}
                  </Badge>
                </div>
                <div className="text-sm font-semibold text-[var(--foreground)] mb-1">{inc.title}</div>
                <div className="text-xs text-[var(--muted-foreground)]">{inc.provider} · {inc.started}</div>
              </div>
              <div className="flex flex-col items-end gap-2 flex-shrink-0">
                {inc.duration && <span className="mono text-xs text-[var(--muted-foreground)]">{inc.duration}</span>}
                <div className="grid grid-cols-2 gap-4 text-right">
                  <div>
                    <div className="mono text-sm font-semibold text-[var(--foreground)]">{inc.affectedRequests.toLocaleString()}</div>
                    <div className="text-[10px] text-[var(--muted-foreground)]">affected</div>
                  </div>
                  <div>
                    <div className="mono text-sm font-semibold text-red-400">{inc.failureRate}%</div>
                    <div className="text-[10px] text-[var(--muted-foreground)]">failure rate</div>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
