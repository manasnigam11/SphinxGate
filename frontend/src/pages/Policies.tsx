import React, { useState } from "react";
import { Badge, Button, Card, SectionHeader, Toggle } from "../components/ui";
import { RESILIENCE_POLICY } from "../data/mock";
import type { ResiliencePolicy } from "../types";

function PolicySection({ title, description, enabled, onToggle, children }: {
  title: string; description: string; enabled: boolean; onToggle: (v: boolean) => void; children?: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 pr-4">
          <div className="text-sm font-semibold text-[var(--foreground)]">{title}</div>
          <div className="text-xs text-[var(--muted-foreground)] mt-1">{description}</div>
        </div>
        <Toggle checked={enabled} onChange={onToggle} />
      </div>
      {enabled && children && (
        <div className="flex flex-col gap-3 pt-4 border-t border-[var(--border)]">
          {children}
        </div>
      )}
    </Card>
  );
}

function PolicyField({ label, value, unit, hint, onChange }: {
  label: string; value: number; unit: string; hint?: string; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xs font-medium text-[var(--foreground)]">{label}</div>
        {hint && <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">{hint}</div>}
      </div>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="w-24 mono text-sm bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-1.5 text-[var(--foreground)] text-right focus:outline-none focus:border-[var(--accent)]"
        />
        <span className="text-xs text-[var(--muted-foreground)] w-8">{unit}</span>
      </div>
    </div>
  );
}

export function Policies() {
  const [policy, setPolicy] = useState<ResiliencePolicy>(RESILIENCE_POLICY);
  const [saved, setSaved] = useState(false);

  function update<K extends keyof ResiliencePolicy>(key: K, value: ResiliencePolicy[K]) {
    setPolicy(p => ({ ...p, [key]: value }));
    setSaved(false);
  }

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Resilience Policies"
        description="Configure how the gateway responds when upstream providers fail."
        actions={
          <Button variant="primary" size="sm" onClick={handleSave}>
            {saved ? (
              <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>Saved</>
            ) : "Save Changes"}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
        <PolicySection
          title="Request Timeout"
          description="Maximum time to wait for a provider response before declaring a timeout."
          enabled
          onToggle={() => {}}
        >
          <PolicyField label="Timeout duration" value={policy.timeout} unit="ms" hint="Recommended: 2000–5000ms" onChange={v => update("timeout", v)} />
        </PolicySection>

        <PolicySection
          title="Retry Policy"
          description="Automatically retry failed requests with configurable backoff."
          enabled={policy.maxRetries > 0}
          onToggle={v => update("maxRetries", v ? 2 : 0)}
        >
          <PolicyField label="Max retries" value={policy.maxRetries} unit="" hint="0 = no retries" onChange={v => update("maxRetries", v)} />
        </PolicySection>

        <PolicySection
          title="Exponential Backoff"
          description="Increase wait time between retries to reduce pressure on struggling providers."
          enabled
          onToggle={() => {}}
        >
          <PolicyField label="Initial backoff" value={policy.initialBackoff} unit="ms" onChange={v => update("initialBackoff", v)} />
          <PolicyField label="Maximum backoff" value={policy.maxBackoff} unit="ms" onChange={v => update("maxBackoff", v)} />
        </PolicySection>

        <PolicySection
          title="Rate Limiting"
          description="Limit outbound request rate to protect providers and stay within quotas."
          enabled
          onToggle={() => {}}
        >
          <PolicyField label="Max requests/sec" value={policy.rateLimitRps} unit="rps" hint="Per provider" onChange={v => update("rateLimitRps", v)} />
        </PolicySection>

        <PolicySection
          title="Circuit Breaker"
          description="Automatically stop sending requests to a failing provider and attempt recovery."
          enabled
          onToggle={() => {}}
        >
          <PolicyField label="Failure threshold" value={policy.circuitBreakerThreshold} unit="failures" hint="Consecutive failures before opening" onChange={v => update("circuitBreakerThreshold", v)} />
          <PolicyField label="Recovery window" value={policy.circuitBreakerWindow} unit="s" hint="Time before attempting half-open" onChange={v => update("circuitBreakerWindow", v)} />
        </PolicySection>

        <PolicySection
          title="Fallback Routing"
          description="Route requests to an alternative provider when the primary is unavailable."
          enabled={policy.fallbackEnabled}
          onToggle={v => update("fallbackEnabled", v)}
        >
          <div className="text-xs text-[var(--muted-foreground)]">
            Fallback order is determined by provider priority and current health. Configure provider priorities in the Providers page.
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="success">Active</Badge>
            <span className="text-xs text-[var(--muted-foreground)]">Nexus AI → Aether Labs</span>
          </div>
        </PolicySection>
      </div>
    </div>
  );
}
