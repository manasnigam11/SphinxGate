import React, { useState, useEffect } from "react";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { fetchIncidents, fetchCopilotAnalysis, askCopilot } from "../api";
import type { Incident, AIAnalysis } from "../types";

function AIAnalysisPanel({ incident }: { incident: Incident }) {
  const [ai, setAi] = useState<AIAnalysis | null>(null);
  const [thinking, setThinking] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [chatHistory, setChatHistory] = useState<{role: "user"|"assistant", content: string}[]>([]);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  useEffect(() => {
    setThinking(true);
    setError(null);
    setAi(null);
    setChatHistory([]);
    setAskError(null);
    setQuestion("");
    fetchCopilotAnalysis(incident.incident_id)
      .then((data) => {
        setAi(data);
        setThinking(false);
      })
      .catch((err) => {
        setError(err.message);
        setThinking(false);
      });
  }, [incident.incident_id]);

  if (thinking) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <div className="flex gap-1.5">
          {[0,1,2].map(i => (
            <span key={i} className="w-2 h-2 bg-[var(--primary)] rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </div>
        <div className="text-xs text-[var(--muted-foreground)]">Analyzing incident {incident.incident_id}...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-center p-8">
        <div className="text-sm font-medium text-red-500">Analysis Failed</div>
        <div className="text-xs text-[var(--muted-foreground)]">{error}</div>
      </div>
    );
  }

  if (!ai) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-center p-8">
        <div className="text-sm font-medium text-[var(--foreground)]">No AI analysis available</div>
        <div className="text-xs text-[var(--muted-foreground)]">This incident does not have a recorded analysis.</div>
      </div>
    );
  }

  const handleAsk = async () => {
    if (!question.trim() || asking) return;
    const userQ = question;
    setQuestion("");
    setChatHistory(prev => [...prev, { role: "user", content: userQ }]);
    setAsking(true);
    setAskError(null);
    try {
      const res = await askCopilot(incident.incident_id, userQ);
      setChatHistory(prev => [...prev, { role: "assistant", content: res.answer }]);
    } catch (err: any) {
      setAskError(err.message || "Failed to ask copilot");
      setChatHistory(prev => [...prev, { role: "assistant", content: "Error: " + (err.message || "Failed to ask copilot") }]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-5 overflow-y-auto animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-2 pb-4 border-b border-[var(--border)]">
        <div className="w-8 h-8 rounded-lg bg-[var(--accent)]/10 border border-[var(--accent)]/20 flex items-center justify-center">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg>
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold text-[var(--foreground)]">Incident Analysis</div>
          <div className="mono text-[10px] text-[var(--muted-foreground)]">{incident.incident_id} · {incident.provider_slug}</div>
        </div>
        <Badge variant="info" className="mono">{ai.confidence}% confidence</Badge>
      </div>

      {/* Summary */}
      <div className="bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] p-4">
        <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Summary</div>
        <p className="text-sm text-[var(--foreground)] leading-relaxed">{ai.summary}</p>
      </div>

      {/* Observed Patterns */}
      <div>
        <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Observed Patterns</div>
        <div className="flex flex-col gap-1">
          {ai.observedPatterns?.map((p, i) => (
            <div key={i} className="flex items-start gap-2.5 bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--primary)] flex-shrink-0 mt-1.5" />
              <span className="text-xs text-[var(--foreground)]">{p}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Likely cause */}
      <div className="bg-amber-500/5 border border-amber-500/20 rounded-[var(--radius)] p-4">
        <div className="text-[10px] font-semibold text-amber-500 uppercase tracking-wider mb-2">Probable Root Cause</div>
        <p className="text-sm text-[var(--foreground)]">{ai.likelyCause}</p>
      </div>

      {/* Actions taken */}
      <div>
        <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Actions Taken</div>
        <div className="flex flex-col gap-1">
          {ai.actionsTaken?.map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-green-500">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              {a}
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      <div>
        <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Recommended Engineering Actions</div>
        <div className="flex flex-col gap-2">
          {ai.recommendations?.map((r, i) => (
            <div key={i} className="flex items-start gap-2.5 bg-[var(--accent)]/5 border border-[var(--accent)]/15 rounded-[var(--radius)] px-3 py-2.5">
              <span className="text-[var(--accent)] flex-shrink-0">→</span>
              <span className="text-xs text-[var(--foreground)]">{r}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Affected components */}
      <div>
        <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-2">Affected Components</div>
        <div className="flex flex-wrap gap-1.5">
          {ai.affectedComponents?.map(c => (
            <Badge key={c} variant="muted" className="mono text-[10px]">{c}</Badge>
          ))}
        </div>
      </div>

      {/* Chat History */}
      {chatHistory.length > 0 && (
        <div className="flex flex-col gap-3 pt-4 border-t border-[var(--border)]">
          {chatHistory.map((msg, idx) => (
            <div key={idx} className={`flex flex-col gap-1 ${msg.role === "user" ? "items-end" : "items-start"}`}>
              <div className={`text-xs font-semibold ${msg.role === "user" ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"}`}>
                {msg.role === "user" ? "You" : "Copilot"}
              </div>
              <div className={`text-sm px-3 py-2 rounded-lg ${msg.role === "user" ? "bg-[var(--primary)]/10 text-[var(--foreground)]" : "bg-[var(--secondary)] text-[var(--foreground)]"} max-w-[85%] whitespace-pre-wrap`}>
                {msg.content}
              </div>
            </div>
          ))}
          {asking && (
            <div className="flex flex-col gap-1 items-start">
              <div className="text-xs font-semibold text-[var(--muted-foreground)]">Copilot</div>
              <div className="text-sm px-3 py-2 rounded-lg bg-[var(--secondary)] text-[var(--foreground)] max-w-[85%]">
                <div className="flex gap-1.5 p-1">
                  {[0,1,2].map(i => (
                    <span key={i} className="w-1.5 h-1.5 bg-[var(--muted-foreground)] rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Follow-up input */}
      <div className={`pt-4 ${chatHistory.length === 0 ? "border-t border-[var(--border)]" : ""}`}>
        <div className="flex items-center gap-2">
          <input
            placeholder="Ask a follow-up question about this incident..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            disabled={asking}
            className="flex-1 text-sm bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
          />
          <Button variant="primary" size="sm" onClick={handleAsk} disabled={asking || !question.trim()}>Ask</Button>
        </div>
      </div>
    </div>
  );
}

export function Copilot() {
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    fetchIncidents().then(data => {
      setIncidents(data.incidents || []);
    });
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="AI Engineering Copilot"
        description="Understand incidents, investigate failures, and get actionable engineering recommendations."
      />

      <div className="grid grid-cols-3 gap-5 max-lg:grid-cols-1" style={{ minHeight: "600px" }}>
        {/* Incident selector */}
        <div className="flex flex-col gap-3">
          <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">Select Incident</div>
          {incidents.map(inc => (
            <Card
              key={inc.incident_id}
              className={`p-4 cursor-pointer transition-all ${selectedIncident?.incident_id === inc.incident_id ? "border-[var(--accent)]/50 bg-[var(--accent)]/5" : "hover:border-[var(--accent)]/30"}`}
              onClick={() => setSelectedIncident(inc)}
            >
              <div className="flex items-center gap-1.5 mb-1.5">
                <Badge variant={
                  inc.severity === "critical" ? "error" : inc.severity === "high" ? "warning" : "info"
                } className="text-[10px]">{inc.severity.toUpperCase()}</Badge>
                <Badge variant={inc.status === "resolved" ? "success" : "error"} className="text-[10px]">{inc.status}</Badge>
                {"ai_analysis" in (inc.metadata || {}) ? <Badge variant="success" className="text-[9px]">AI Cached</Badge> : <Badge variant="muted" className="text-[9px]">Generate AI</Badge>}
              </div>
              <div className="text-xs font-medium text-[var(--foreground)] mb-1">{inc.title}</div>
              <div className="mono text-[10px] text-[var(--muted-foreground)]">{inc.incident_id} · {inc.provider_slug}</div>
              <div className="text-[10px] text-[var(--muted-foreground)] mt-1.5">{inc.started_at_iso}</div>
            </Card>
          ))}
        </div>

        {/* Analysis panel */}
        <Card className="col-span-2 flex flex-col overflow-hidden">
          {!selectedIncident ? (
            <div className="flex flex-col items-center justify-center flex-1 gap-4 text-center p-8">
              <div className="w-16 h-16 rounded-2xl bg-[var(--accent)]/10 border border-[var(--accent)]/20 flex items-center justify-center">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>
              </div>
              <div>
                <div className="text-base font-semibold text-[var(--foreground)] mb-1">Select an incident to begin analysis</div>
                <div className="text-sm text-[var(--muted-foreground)] max-w-sm">
                  The AI copilot will analyze patterns, correlate logs, and surface actionable recommendations.
                </div>
              </div>
              <div className="flex flex-wrap gap-2 justify-center mt-2">
                {["Root cause analysis", "Latency correlation", "Circuit breaker insights", "Retry pattern analysis"].map(f => (
                  <span key={f} className="px-2.5 py-1 bg-[var(--secondary)] border border-[var(--border)] rounded-full text-xs text-[var(--muted-foreground)]">{f}</span>
                ))}
              </div>
            </div>
          ) : (
            <AIAnalysisPanel incident={selectedIncident} />
          )}
        </Card>
      </div>
    </div>
  );
}

