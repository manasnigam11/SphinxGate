import React, { useEffect, useState, useCallback } from "react";
import { Badge, Button, Card, Select, SectionHeader } from "../components/ui";
import {
  fetchFaultStatus,
  fetchFaults,
  createFault,
  disableFault,
  clearAllFaults,
  formatTimestamp,
  type FaultConfig,
  type FaultStatus,
} from "../api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function faultStatusVariant(f: FaultConfig): "error" | "muted" {
  if (f.is_effective) return "error";
  return "muted";
}

function faultStatusLabel(f: FaultConfig): string {
  if (f.is_expired) return "Expired";
  if (!f.is_active) return "Disabled";
  return "Active";
}

// ── Component ─────────────────────────────────────────────────────────────────

export function FaultInjection() {
  const [status, setStatus] = useState<FaultStatus | null>(null);
  const [faults, setFaults] = useState<FaultConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Form state
  const [provider, setProvider] = useState("");
  const [faultType, setFaultType] = useState("timeout");
  const [duration, setDuration] = useState(60);
  const [latencyMs, setLatencyMs] = useState(2000);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try {
      const [st, fl] = await Promise.all([fetchFaultStatus(), fetchFaults()]);
      setStatus(st);
      setFaults(fl.faults);
      if (!provider && st.registered_providers.length > 0) {
        setProvider(st.registered_providers[0]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load fault injection status");
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  async function handleInject() {
    if (!status?.enabled) return;
    setActionError(null);
    setActionSuccess(null);
    setCreating(true);
    try {
      const result = await createFault({
        provider_slug: provider,
        fault_type: faultType,
        latency_ms: faultType === "latency" ? latencyMs : 0,
        duration_seconds: duration,
        note,
        created_by: "demo-operator",
      });
      setActionSuccess(`Fault activated: ${result.fault.fault_id}`);
      await load();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Failed to create fault");
    } finally {
      setCreating(false);
    }
  }

  async function handleDisable(faultId: string) {
    setActionError(null);
    try {
      await disableFault(faultId);
      setActionSuccess(`Fault ${faultId} disabled`);
      await load();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Failed to disable fault");
    }
  }

  async function handleClearAll() {
    setActionError(null);
    try {
      const result = await clearAllFaults();
      setActionSuccess(`Cleared ${result.faults_deactivated} fault(s)`);
      await load();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : "Failed to clear faults");
    }
  }

  const activeFaults = faults.filter(f => f.is_effective);

  if (loading) {
    return (
      <div className="flex flex-col gap-6 p-6 animate-fade-in">
        <SectionHeader title="Fault Injection" description="Loading..." />
        <div className="flex items-center justify-center py-16">
          <div className="w-6 h-6 border-2 border-[var(--primary)] border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Fault Injection"
        description="Simulate upstream failures to verify resilience behavior under controlled conditions."
      />

      {/* Status banner */}
      {!status?.enabled ? (
        <div className="flex items-start gap-3 bg-red-500/5 border border-red-500/20 rounded-[var(--radius-lg)] px-5 py-4">
          <svg className="text-red-400 flex-shrink-0 mt-0.5" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            <div className="text-sm font-semibold text-red-400 mb-1">Fault Injection Disabled</div>
            <div className="text-xs text-[var(--muted-foreground)]">
              Set <span className="mono bg-[var(--secondary)] px-1 py-0.5 rounded text-[var(--foreground)]">FAULT_INJECTION_ENABLED=true</span> in your environment to enable fault injection. This feature is for development and demo environments only.
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3 bg-amber-500/5 border border-amber-500/20 rounded-[var(--radius-lg)] px-5 py-4">
          <svg className="text-amber-500 flex-shrink-0 mt-0.5" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <div>
            <div className="text-sm font-semibold text-amber-500 mb-1">⚡ Fault Injection ENABLED — Development Mode</div>
            <div className="text-xs text-[var(--muted-foreground)]">
              Faults injected here will affect all requests to the targeted provider until disabled. This is a real operation, not a simulation.
            </div>
          </div>
        </div>
      )}

      {/* Error / success feedback */}
      {error && (
        <div className="text-xs text-red-400 px-4 py-3 bg-red-500/5 border border-red-500/20 rounded-[var(--radius)]">{error}</div>
      )}
      {actionError && (
        <div className="text-xs text-red-400 px-4 py-3 bg-red-500/5 border border-red-500/20 rounded-[var(--radius)]">⚠ {actionError}</div>
      )}
      {actionSuccess && (
        <div className="text-xs text-green-500 px-4 py-3 bg-green-500/5 border border-green-500/20 rounded-[var(--radius)]">✓ {actionSuccess}</div>
      )}

      <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
        {/* Config panel */}
        <Card className="p-5 flex flex-col gap-4">
          <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">Fault Configuration</div>

          <Select
            label="Target Provider"
            value={provider}
            onChange={e => setProvider(e.target.value)}
            options={(status?.registered_providers ?? []).map(p => ({ value: p, label: p }))}
            disabled={!status?.enabled}
          />

          <Select
            label="Fault Type"
            value={faultType}
            onChange={e => setFaultType(e.target.value)}
            options={(status?.supported_fault_types ?? []).map(t => ({ value: t.value, label: t.label }))}
            disabled={!status?.enabled}
          />

          <div>
            <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">
              Duration: <span className="mono text-[var(--foreground)]">{duration === 0 ? "∞ manual" : `${duration}s`}</span>
            </label>
            <input type="range" min={0} max={300} step={15} value={duration}
              onChange={e => setDuration(Number(e.target.value))}
              className="w-full accent-[var(--primary)] cursor-pointer"
              disabled={!status?.enabled} />
            <div className="flex justify-between text-[10px] text-[var(--muted-foreground)] mt-1"><span>∞</span><span>300s</span></div>
          </div>

          {faultType === "latency" && (
            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">
                Added Latency: <span className="mono text-[var(--foreground)]">{latencyMs}ms</span>
              </label>
              <input type="range" min={100} max={10000} step={100} value={latencyMs}
                onChange={e => setLatencyMs(Number(e.target.value))}
                className="w-full accent-[var(--primary)] cursor-pointer"
                disabled={!status?.enabled} />
              <div className="flex justify-between text-[10px] text-[var(--muted-foreground)] mt-1"><span>100ms</span><span>10s</span></div>
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">Note (optional)</label>
            <input
              type="text"
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Why are you injecting this fault?"
              maxLength={200}
              disabled={!status?.enabled}
              className="w-full text-sm bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)] disabled:opacity-40"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <Button
              variant="danger"
              onClick={handleInject}
              disabled={!status?.enabled || creating || !provider}
            >
              {creating ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
                  Injecting...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                  Inject Fault
                </span>
              )}
            </Button>
            {activeFaults.length > 0 && (
              <Button variant="secondary" onClick={handleClearAll} disabled={!status?.enabled}>
                Clear All
              </Button>
            )}
          </div>
        </Card>

        {/* Active faults panel */}
        <Card className="p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">Active Faults</div>
            {activeFaults.length > 0 && (
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse-dot" />
                <span className="text-xs text-red-400 font-medium">{activeFaults.length} active</span>
              </div>
            )}
          </div>

          {faults.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center py-8">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--muted-foreground)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              <div className="text-sm font-medium text-[var(--foreground)]">No active faults</div>
              <div className="text-xs text-[var(--muted-foreground)]">
                {status?.enabled ? "Inject a fault to see it here." : "Enable fault injection first."}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2 overflow-y-auto max-h-96">
              {faults.map(f => (
                <div key={f.fault_id} className="flex items-start gap-3 p-3 bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)]">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="mono text-xs text-[var(--foreground)] font-medium">{f.provider_slug}</span>
                      <Badge variant={faultStatusVariant(f)} dot>{faultStatusLabel(f)}</Badge>
                      {f.fault_injected !== undefined && (
                        <span className="mono text-[10px] text-[var(--muted-foreground)] bg-[var(--background)] border border-[var(--border)] px-1.5 py-0.5 rounded">
                          {f.fault_type_label}
                        </span>
                      )}
                    </div>
                    <div className="mono text-[10px] text-[var(--muted-foreground)] mb-0.5">{f.fault_type_label}</div>
                    {f.duration_seconds > 0 && (
                      <div className="text-[10px] text-[var(--muted-foreground)]">
                        Duration: {f.duration_seconds}s · Created: {formatTimestamp(f.created_at)}
                      </div>
                    )}
                    {f.note && (
                      <div className="text-[10px] text-[var(--muted-foreground)] italic mt-0.5">{f.note}</div>
                    )}
                    <div className="mono text-[10px] text-[var(--muted-foreground)] mt-0.5">{f.fault_id}</div>
                  </div>
                  {f.is_effective && status?.enabled && (
                    <button
                      onClick={() => handleDisable(f.fault_id)}
                      className="flex-shrink-0 text-[10px] text-red-400 hover:text-red-300 transition-colors border border-red-500/30 rounded px-2 py-1 cursor-pointer"
                    >
                      Disable
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Supported fault types reference */}
      {status?.enabled && (
        <Card className="p-5">
          <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-3">Supported Fault Types</div>
          <div className="grid grid-cols-4 gap-2 max-lg:grid-cols-2">
            {(status?.supported_fault_types ?? []).map(t => (
              <div key={t.value} className="p-3 bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)]">
                <div className="mono text-xs text-[var(--foreground)] mb-1">{t.value}</div>
                <div className="text-[10px] text-[var(--muted-foreground)]">{t.label}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
