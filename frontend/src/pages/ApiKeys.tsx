import React, { useState } from "react";
import { Badge, Button, Card, SectionHeader } from "../components/ui";
import { API_KEYS } from "../data/mock";
import type { ApiKey } from "../types";

const ENV_VARIANT: Record<string, "success" | "info" | "muted"> = {
  production: "success",
  staging: "info",
  development: "muted",
};

export function ApiKeys() {
  const [keys, setKeys] = useState<ApiKey[]>(API_KEYS);
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyEnv, setNewKeyEnv] = useState("development");
  const [created, setCreated] = useState<string | null>(null);

  function toggleReveal(id: string) {
    setRevealed(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function revokeKey(id: string) {
    setKeys(prev => prev.map(k => k.id === id ? { ...k, status: "revoked" as const } : k));
  }

  function handleCreate() {
    if (!newKeyName) return;
    const newKey: ApiKey = {
      id: `k${Date.now()}`,
      name: newKeyName,
      keyPreview: `sk_${newKeyEnv.slice(0, 3)}_••••••••${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      created: new Date().toISOString().split("T")[0],
      lastUsed: "Never",
      environment: newKeyEnv as "production" | "staging" | "development",
      status: "active",
      requests: 0,
    };
    setCreated(newKey.keyPreview);
    setKeys(prev => [newKey, ...prev]);
    setShowCreate(false);
    setNewKeyName("");
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="API Keys"
        description="Manage gateway authentication credentials. Keys are environment-scoped and never displayed in full."
        actions={
          <Button variant="primary" size="sm" onClick={() => setShowCreate(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Create API Key
          </Button>
        }
      />

      {/* Security warning */}
      <div className="flex items-start gap-3 bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius-lg)] px-5 py-4">
        <svg className="text-[var(--muted-foreground)] flex-shrink-0 mt-0.5" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <div className="text-xs text-[var(--muted-foreground)]">
          <span className="font-semibold text-[var(--foreground)]">Security note:</span> Never expose API keys in client-side code, public repositories, or logs. Rotate compromised keys immediately. Keys are stored encrypted and cannot be retrieved after creation.
        </div>
      </div>

      {/* Create key modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-[400px] p-6 shadow-2xl animate-fade-in">
            <div className="text-base font-semibold text-[var(--foreground)] mb-4">Create API Key</div>
            <div className="flex flex-col gap-4">
              <div>
                <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">Key Name</label>
                <input
                  value={newKeyName}
                  onChange={e => setNewKeyName(e.target.value)}
                  placeholder="e.g. Production Gateway v2"
                  className="w-full bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">Environment</label>
                <select
                  value={newKeyEnv}
                  onChange={e => setNewKeyEnv(e.target.value)}
                  className="w-full bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
                >
                  <option value="development">Development</option>
                  <option value="staging">Staging</option>
                  <option value="production">Production</option>
                </select>
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="primary" onClick={handleCreate}>Create Key</Button>
                <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Created banner */}
      {created && (
        <div className="flex items-center gap-3 bg-green-500/5 border border-green-500/20 rounded-[var(--radius-lg)] px-5 py-4 animate-fade-in">
          <svg className="text-green-500" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          <div className="flex-1 text-xs">
            <span className="font-semibold text-green-500">Key created: </span>
            <span className="mono text-[var(--foreground)]">{created}</span>
            <span className="text-[var(--muted-foreground)] ml-2">— Copy it now. It won't be shown again.</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setCreated(null)}>Dismiss</Button>
        </div>
      )}

      {/* Keys table */}
      <Card className="overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--border)]">
              {["Name", "Key", "Created", "Last Used", "Environment", "Requests", "Status", ""].map(h => (
                <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map(key => (
              <tr key={key.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--secondary)] transition-colors">
                <td className="px-4 py-3.5 text-sm font-medium text-[var(--foreground)]">{key.name}</td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2">
                    <span className="mono text-xs text-[var(--foreground)]">
                      {revealed.has(key.id) ? key.keyPreview.replace(/•+/, "sk_...ACTUAL_KEY_HIDDEN") : key.keyPreview}
                    </span>
                    <button
                      onClick={() => toggleReveal(key.id)}
                      className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer p-0.5"
                      aria-label={revealed.has(key.id) ? "Hide key" : "Reveal key"}
                    >
                      {revealed.has(key.id) ? (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                      ) : (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                      )}
                    </button>
                    <button className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer p-0.5" aria-label="Copy key">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    </button>
                  </div>
                </td>
                <td className="px-4 py-3.5 text-xs text-[var(--muted-foreground)]">{key.created}</td>
                <td className="px-4 py-3.5 text-xs text-[var(--muted-foreground)]">{key.lastUsed}</td>
                <td className="px-4 py-3.5">
                  <Badge variant={ENV_VARIANT[key.environment]}>{key.environment}</Badge>
                </td>
                <td className="px-4 py-3.5 mono text-xs text-[var(--muted-foreground)]">{key.requests.toLocaleString()}</td>
                <td className="px-4 py-3.5">
                  <Badge variant={key.status === "active" ? "success" : "muted"}>{key.status}</Badge>
                </td>
                <td className="px-4 py-3.5">
                  {key.status === "active" && (
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" className="text-[10px]">Rotate</Button>
                      <Button variant="danger" size="sm" className="text-[10px]" onClick={() => revokeKey(key.id)}>Revoke</Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
