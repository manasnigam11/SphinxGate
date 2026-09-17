import React, { useState } from "react";
import { Button, Card, Divider, SectionHeader, Toggle } from "../components/ui";

export function Settings({ theme, onThemeChange }: { theme: "light" | "dark"; onThemeChange: (t: "light" | "dark" | "system") => void }) {
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [notifications, setNotifications] = useState({
    incidents: true,
    circuitBreaker: true,
    healthAlerts: true,
    weeklyReport: false,
    email: true,
    slack: false,
  });
  const [saved, setSaved] = useState(false);

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="Settings"
        description="Configure your workspace, appearance, and notification preferences."
        actions={
          <Button variant="primary" size="sm" onClick={handleSave}>
            {saved ? "Saved!" : "Save Changes"}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
        {/* Appearance */}
        <Card className="p-5">
          <div className="text-sm font-semibold text-[var(--foreground)] mb-4">Appearance</div>

          <div className="flex flex-col gap-4">
            <div>
              <div className="text-xs font-medium text-[var(--muted-foreground)] mb-2">Theme</div>
              <div className="grid grid-cols-3 gap-2">
                {(["light", "dark", "system"] as const).map(t => {
                  const active = theme === t || (t === "system" && false);
                  return (
                    <button
                      key={t}
                      onClick={() => onThemeChange(t)}
                      className={`px-3 py-2 text-xs font-medium rounded-[var(--radius)] border transition-colors cursor-pointer ${
                        (t === "light" && theme === "light") || (t === "dark" && theme === "dark")
                          ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                          : "bg-[var(--secondary)] text-[var(--foreground)] border-[var(--border)] hover:border-[var(--accent)]/40"
                      }`}
                    >
                      {t.charAt(0).toUpperCase() + t.slice(1)}
                    </button>
                  );
                })}
              </div>
            </div>

            <Divider />

            <div>
              <div className="text-xs font-medium text-[var(--muted-foreground)] mb-2">Density</div>
              <div className="grid grid-cols-2 gap-2">
                {(["comfortable", "compact"] as const).map(d => (
                  <button
                    key={d}
                    onClick={() => setDensity(d)}
                    className={`px-3 py-2 text-xs font-medium rounded-[var(--radius)] border transition-colors cursor-pointer ${density === d ? "bg-[var(--accent)] text-white border-[var(--accent)]" : "bg-[var(--secondary)] text-[var(--foreground)] border-[var(--border)]"}`}
                  >
                    {d.charAt(0).toUpperCase() + d.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Card>

        {/* Notifications */}
        <Card className="p-5">
          <div className="text-sm font-semibold text-[var(--foreground)] mb-4">Notifications</div>
          <div className="flex flex-col gap-3">
            {[
              { key: "incidents" as const, label: "Incident alerts", description: "New and escalated incidents" },
              { key: "circuitBreaker" as const, label: "Circuit breaker events", description: "Open/close state changes" },
              { key: "healthAlerts" as const, label: "Provider health alerts", description: "Status changes and degradation" },
              { key: "weeklyReport" as const, label: "Weekly digest", description: "Summary of usage and incidents" },
            ].map(n => (
              <div key={n.key} className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-[var(--foreground)]">{n.label}</div>
                  <div className="text-xs text-[var(--muted-foreground)]">{n.description}</div>
                </div>
                <Toggle
                  checked={notifications[n.key]}
                  onChange={v => setNotifications(prev => ({ ...prev, [n.key]: v }))}
                />
              </div>
            ))}
            <Divider />
            <div className="text-xs font-medium text-[var(--muted-foreground)] mb-1">Delivery channels</div>
            {[
              { key: "email" as const, label: "Email" },
              { key: "slack" as const, label: "Slack" },
            ].map(n => (
              <div key={n.key} className="flex items-center justify-between">
                <div className="text-sm text-[var(--foreground)]">{n.label}</div>
                <Toggle
                  checked={notifications[n.key]}
                  onChange={v => setNotifications(prev => ({ ...prev, [n.key]: v }))}
                />
              </div>
            ))}
          </div>
        </Card>

        {/* Security */}
        <Card className="p-5">
          <div className="text-sm font-semibold text-[var(--foreground)] mb-4">Security</div>
          <div className="flex flex-col gap-4">
            {[
              { label: "Two-factor authentication", detail: "Enabled via TOTP", action: "Configure" },
              { label: "Session timeout", detail: "8 hours of inactivity", action: "Change" },
              { label: "IP allowlist", detail: "Disabled — all IPs allowed", action: "Configure" },
              { label: "Audit log", detail: "90-day retention", action: "View logs" },
            ].map(s => (
              <div key={s.label} className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-[var(--foreground)]">{s.label}</div>
                  <div className="text-xs text-[var(--muted-foreground)]">{s.detail}</div>
                </div>
                <Button variant="outline" size="sm">{s.action}</Button>
              </div>
            ))}
          </div>
        </Card>

        {/* General */}
        <Card className="p-5">
          <div className="text-sm font-semibold text-[var(--foreground)] mb-4">General</div>
          <div className="flex flex-col gap-4">
            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">Organization Name</label>
              <input
                defaultValue="Acme Engineering"
                className="w-full bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">Default Environment</label>
              <select className="w-full bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]">
                <option>Production</option>
                <option>Staging</option>
                <option>Development</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--muted-foreground)] block mb-1.5">Timezone</label>
              <select className="w-full bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]">
                <option>UTC</option>
                <option>America/New_York</option>
                <option>America/Los_Angeles</option>
                <option>Europe/London</option>
              </select>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
