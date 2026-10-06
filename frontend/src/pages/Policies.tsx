import React, { useState, useEffect, useCallback } from "react";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { fetchPolicy } from "../api";

/**
 * Policies page — Phase 3.
 *
 * Displays the LIVE resilience policy from the backend /api/v1/policy endpoint.
 * Read-only in Phase 3 (changing policy requires env var changes and restart).
 * The Phase 3 scope does not include runtime policy mutation via UI.
 */

function PolicyRow({ label, value, description }: { label: string; value: React.ReactNode; description?: string }) {
  return (
    <div className="flex items-start justify-between py-3 border-b border-[var(--border)] last:border-0 gap-4">
      <div className="min-w-0">
        <div className="text-sm font-medium text-[var(--foreground)]">{label}</div>
        {description && <div className="text-xs text-[var(--muted-foreground)] mt-0.5">{description}</div>}
      </div>
      <div className="flex-shrink-0">{value}</div>
    </div>
  );
}

function ValueBadge({ v }: { v: unknown }) {
  if (typeof v === "boolean") {
    return <Badge variant={v ? "success" : "muted"}>{v ? "Enabled" : "Disabled"}</Badge>;
  }
  if (typeof v === "number") {
    return <span className="mono text-sm font-semibold text-[var(--foreground)]">{v}</span>;
  }
  if (typeof v === "string") {
    return <span className="mono text-sm text-[var(--foreground)]">{v}</span>;
  }
  if (Array.isArray(v)) {
    if (v.length === 0) return <span className="text-xs text-[var(--muted-foreground)]">None configured</span>;
    return (
      <div className="flex flex-col gap-1 items-end">
        {(v as { primary?: string; fallbacks?: string[] }[]).map((item, i) => (
          <div key={i} className="text-xs mono text-[var(--muted-foreground)]">
            {item.primary ?? ""} → [{(item.fallbacks ?? []).join(", ")}]
          </div>
        ))}
      </div>
    );
  }
  return <span className="mono text-xs text-[var(--muted-foreground)]">{JSON.stringify(v)}</span>;
}

const POLICY_FIELDS: {
  key: string;
  label: string;
  description: string;
  unit?: string;
}[] = [
  { key: "timeout", label: "Request Timeout", description: "Maximum wait for a provider response", unit: "ms" },
  { key: "request_timeout_seconds", label: "Request Timeout", description: "Maximum wait for a provider response", unit: "s" },
  { key: "retryEnabled", label: "Retry Enabled", description: "Automatically retry failed requests" },
  { key: "retry_enabled", label: "Retry Enabled", description: "Automatically retry failed requests" },
  { key: "maxRetries", label: "Max Retries", description: "Maximum retry attempts per request" },
  { key: "max_retries", label: "Max Retries", description: "Maximum retry attempts per request" },
  { key: "initialBackoff", label: "Initial Backoff", description: "Starting delay before first retry", unit: "ms" },
  { key: "initial_backoff_seconds", label: "Initial Backoff", description: "Starting delay before first retry", unit: "s" },
  { key: "maxBackoff", label: "Max Backoff", description: "Maximum delay cap for exponential backoff", unit: "ms" },
  { key: "max_backoff_seconds", label: "Max Backoff", description: "Maximum delay cap for exponential backoff", unit: "s" },
  { key: "circuitBreakerThreshold", label: "CB Failure Threshold", description: "Consecutive failures before opening circuit" },
  { key: "circuit_failure_threshold", label: "CB Failure Threshold", description: "Consecutive failures before opening circuit" },
  { key: "circuitBreakerWindow", label: "CB Recovery Window", description: "Seconds before attempting half-open recovery", unit: "s" },
  { key: "circuit_recovery_window_seconds", label: "CB Recovery Window", description: "Seconds before attempting half-open recovery", unit: "s" },
  { key: "rateLimitRps", label: "Rate Limit", description: "Maximum requests per window per provider" },
  { key: "rate_limit_requests", label: "Rate Limit Requests", description: "Max requests per window per provider" },
  { key: "rate_limit_window_seconds", label: "Rate Limit Window", description: "Rate limiting window size", unit: "s" },
  { key: "fallbackEnabled", label: "Fallback Enabled", description: "Route to backup provider on failure" },
  { key: "fallback_enabled", label: "Fallback Enabled", description: "Route to backup provider on failure" },
  { key: "fallbackConfigs", label: "Fallback Chains", description: "Provider fallback routing configuration" },
  { key: "fallback_configs", label: "Fallback Chains", description: "Provider fallback routing configuration" },
];

export function Policies() {
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPolicy();
      setPolicy(data);
    } catch {
      setError("Failed to load policy from backend. Is the server running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Deduplicate — pick camelCase or snake_case but not both
  const seenLabels = new Set<string>();
  const visibleFields = policy
    ? POLICY_FIELDS.filter(f => {
        if (!(f.key in policy)) return false;
        if (seenLabels.has(f.label)) return false;
        seenLabels.add(f.label);
        return true;
      })
    : [];

  // Any fields not in our known list
  const unknownFields = policy
    ? Object.entries(policy).filter(([k]) => !POLICY_FIELDS.some(f => f.key === k))
    : [];

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Resilience Policies"
        description="Live policy from the backend. Change via environment variables and restart."
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="info">Read-only</Badge>
            <Button variant="outline" size="sm" onClick={load}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              Refresh
            </Button>
          </div>
        }
      />

      <div className="bg-amber-500/5 border border-amber-500/20 rounded-[var(--radius)] p-4 text-xs text-amber-400">
        <strong>Note:</strong> Resilience policy is configured via environment variables (e.g. <code className="mono">RESILIENCE_TIMEOUT_SECONDS</code>, <code className="mono">RESILIENCE_MAX_RETRIES</code>).
      </div>

      {error && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] p-4 text-sm text-red-400">{error}</div>
      )}

      {loading ? (
        <Card className="p-6">
          <div className="text-sm text-[var(--muted-foreground)]">Loading policy from backend…</div>
        </Card>
      ) : policy ? (
        <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
          {/* Known fields */}
          <Card className="p-5">
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-4">Timeouts & Retries</div>
            {visibleFields
              .filter(f => ["Request Timeout", "Retry Enabled", "Max Retries", "Initial Backoff", "Max Backoff"].includes(f.label))
              .map(f => (
                <PolicyRow
                  key={f.key}
                  label={f.label}
                  description={f.description}
                  value={
                    <div className="flex items-center gap-1.5">
                      <ValueBadge v={policy[f.key]} />
                      {f.unit && <span className="text-xs text-[var(--muted-foreground)]">{f.unit}</span>}
                    </div>
                  }
                />
              ))}
          </Card>

          <Card className="p-5">
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-4">Circuit Breaker</div>
            {visibleFields
              .filter(f => f.label.startsWith("CB"))
              .map(f => (
                <PolicyRow
                  key={f.key}
                  label={f.label}
                  description={f.description}
                  value={
                    <div className="flex items-center gap-1.5">
                      <ValueBadge v={policy[f.key]} />
                      {f.unit && <span className="text-xs text-[var(--muted-foreground)]">{f.unit}</span>}
                    </div>
                  }
                />
              ))}
          </Card>

          <Card className="p-5">
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-4">Rate Limiting</div>
            {visibleFields
              .filter(f => f.label.startsWith("Rate"))
              .map(f => (
                <PolicyRow
                  key={f.key}
                  label={f.label}
                  description={f.description}
                  value={
                    <div className="flex items-center gap-1.5">
                      <ValueBadge v={policy[f.key]} />
                      {f.unit && <span className="text-xs text-[var(--muted-foreground)]">{f.unit}</span>}
                    </div>
                  }
                />
              ))}
          </Card>

          <Card className="p-5">
            <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-4">Fallback</div>
            {visibleFields
              .filter(f => f.label.startsWith("Fallback"))
              .map(f => (
                <PolicyRow
                  key={f.key}
                  label={f.label}
                  description={f.description}
                  value={<ValueBadge v={policy[f.key]} />}
                />
              ))}
          </Card>

          {/* Catch-all for unexpected fields */}
          {unknownFields.length > 0 && (
            <Card className="p-5 col-span-2">
              <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-4">Additional Fields</div>
              {unknownFields.map(([k, v]) => (
                <PolicyRow key={k} label={k} value={<ValueBadge v={v} />} />
              ))}
            </Card>
          )}
        </div>
      ) : null}
    </div>
  );
}
