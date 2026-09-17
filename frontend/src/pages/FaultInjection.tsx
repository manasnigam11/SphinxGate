import React, { useState } from "react";
import { Badge, Button, Card, Select, SectionHeader, Toggle } from "../components/ui";

const FAILURE_TYPES = [
  { value: "timeout", label: "Timeout" },
  { value: "429", label: "HTTP 429 (Rate Limited)" },
  { value: "500", label: "HTTP 500 (Server Error)" },
  { value: "502", label: "HTTP 502 (Bad Gateway)" },
  { value: "503", label: "HTTP 503 (Unavailable)" },
  { value: "connection_failure", label: "Connection Failure" },
  { value: "artificial_latency", label: "Artificial Latency" },
];

interface FaultResult {
  requestsAffected: number;
  retriesTriggered: number;
  circuitState: string;
  fallbackResponses: number;
  elapsed: number;
}

export function FaultInjection() {
  const [provider, setProvider] = useState("vela-systems");
  const [failureType, setFailureType] = useState("timeout");
  const [duration, setDuration] = useState(30);
  const [failureRate, setFailureRate] = useState(50);
  const [latency, setLatency] = useState(3000);
  const [active, setActive] = useState(false);
  const [result, setResult] = useState<FaultResult | null>(null);

  function handleInject() {
    setActive(true);
    setResult(null);
    const interval = setInterval(() => {
      setResult(prev => ({
        requestsAffected: (prev?.requestsAffected ?? 0) + Math.floor(Math.random() * 8 + 2),
        retriesTriggered: (prev?.retriesTriggered ?? 0) + Math.floor(Math.random() * 4),
        circuitState: prev && (prev.requestsAffected ?? 0) > 30 ? "open" : "closed",
        fallbackResponses: (prev?.fallbackResponses ?? 0) + Math.floor(Math.random() * 3),
        elapsed: (prev?.elapsed ?? 0) + 1,
      }));
    }, 1000);
    setTimeout(() => {
      clearInterval(interval);
      setActive(false);
    }, duration * 1000);
  }

  function handleStop() {
    setActive(false);
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Fault Injection"
        description="Simulate upstream failures and verify resilience behavior under controlled conditions."
      />

      {/* Warning banner */}
      <div className="flex items-start gap-3 bg-amber-500/5 border border-amber-500/20 rounded-[var(--radius-lg)] px-5 py-4">
        <svg className="text-amber-500 flex-shrink-0 mt-0.5" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <div>
          <div className="text-sm font-semibold text-amber-500 mb-1">Non-Production Only</div>
          <div className="text-xs text-[var(--muted-foreground)]">
            Fault injection is available in Development and Staging environments only. Production is protected and cannot be targeted.
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
        {/* Config */}
        <Card className="p-5 flex flex-col gap-4">
          <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">Fault Configuration</div>

          <Select
            label="Target Provider"
            value={provider}
            onChange={e => setProvider(e.target.value)}
            options={[
              { value: "nexus-ai", label: "Nexus AI" },
              { value: "vela-systems", label: "Vela Systems" },
              { value: "aether-labs", label: "Aether Labs" },
            ]}
          />

          <Select
            label="Failure Type"
            value={failureType}
            onChange={e => setFailureType(e.target.value)}
            options={FAILURE_TYPES}
          />

          <div>
            <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">
              Duration: <span className="mono text-[var(--foreground)]">{duration}s</span>
            </label>
            <input type="range" min={5} max={120} step={5} value={duration} onChange={e => setDuration(Number(e.target.value))}
              className="w-full accent-[var(--primary)] cursor-pointer" />
            <div className="flex justify-between text-[10px] text-[var(--muted-foreground)] mt-1"><span>5s</span><span>120s</span></div>
          </div>

          <div>
            <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">
              Failure Rate: <span className="mono text-[var(--foreground)]">{failureRate}%</span>
            </label>
            <input type="range" min={10} max={100} step={10} value={failureRate} onChange={e => setFailureRate(Number(e.target.value))}
              className="w-full accent-[var(--primary)] cursor-pointer" />
            <div className="flex justify-between text-[10px] text-[var(--muted-foreground)] mt-1"><span>10%</span><span>100%</span></div>
          </div>

          {failureType === "artificial_latency" && (
            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">
                Added Latency: <span className="mono text-[var(--foreground)]">{latency}ms</span>
              </label>
              <input type="range" min={500} max={10000} step={500} value={latency} onChange={e => setLatency(Number(e.target.value))}
                className="w-full accent-[var(--primary)] cursor-pointer" />
            </div>
          )}

          <div className="flex gap-2 pt-2">
            {!active ? (
              <Button variant="danger" onClick={handleInject}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                Inject Fault
              </Button>
            ) : (
              <Button variant="secondary" onClick={handleStop}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
                Stop Injection
              </Button>
            )}
          </div>
        </Card>

        {/* Live results */}
        <Card className="p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">Live Results</div>
            {active && (
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse-dot" />
                <span className="text-xs text-red-400 font-medium">Injecting</span>
              </div>
            )}
          </div>

          {!result && !active && (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--muted-foreground)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              <div className="text-sm font-medium text-[var(--foreground)]">No active injection</div>
              <div className="text-xs text-[var(--muted-foreground)]">Configure and inject a fault to see live results</div>
            </div>
          )}

          {(result || active) && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "Requests Affected", value: result?.requestsAffected ?? 0, color: "text-red-400" },
                  { label: "Retries Triggered", value: result?.retriesTriggered ?? 0, color: "text-amber-500" },
                  { label: "Fallback Responses", value: result?.fallbackResponses ?? 0, color: "text-blue-400" },
                  { label: "Elapsed", value: `${result?.elapsed ?? 0}s`, color: "text-[var(--foreground)]" },
                ].map(s => (
                  <div key={s.label} className="bg-[var(--secondary)] rounded-[var(--radius)] p-3 border border-[var(--border)]">
                    <div className="text-[10px] text-[var(--muted-foreground)] mb-1">{s.label}</div>
                    <div className={`mono text-xl font-semibold ${s.color}`}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Circuit state */}
              <div className="flex items-center justify-between p-3 bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)]">
                <span className="text-xs text-[var(--muted-foreground)]">Circuit Breaker State</span>
                <Badge
                  variant={result?.circuitState === "open" ? "error" : "success"}
                  dot
                  className="mono text-[10px]"
                >
                  {result?.circuitState?.toUpperCase() ?? "CLOSED"}
                </Badge>
              </div>

              {/* Recovery status */}
              {!active && result && (
                <div className="flex items-center gap-2 p-3 bg-green-500/5 border border-green-500/20 rounded-[var(--radius)]">
                  <svg className="text-green-500" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  <span className="text-xs text-green-500">Injection complete — system recovering</span>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
