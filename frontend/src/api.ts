/**
 * SphinxGate API client — Phase 4.
 *
 * Centralizes all backend API calls so page components stay clean.
 * All functions return typed data or throw on network error.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// ── Types (Phase 1-3) ──────────────────────────────────────────────────────────

export interface TelemetryRequest {
  request_id: string;
  timestamp: number;
  timestamp_iso: string;
  provider: string;
  provider_display_name: string;
  provider_category: string;
  endpoint: string;
  success: boolean;
  status_code: number;
  latency_ms: number;
  retry_count: number;
  fallback_used: boolean;
  circuit_state: string;
  tokens_used: number;
  cache_hit: boolean;
  error_type: string | null;
  error_message?: string;
  events?: ResilienceEvent[];
}

export interface ResilienceEvent {
  event_type: string;
  provider_slug: string;
  timestamp: number;
  data: Record<string, unknown>;
}

export interface TelemetrySummary {
  window: string;
  since_seconds: number;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number | null;
  error_rate: number | null;
  avg_latency_ms: number;
  p95_latency_ms: number;
  total_tokens_used: number;
  total_retries: number;
  total_fallbacks: number;
  cache_hits: number;
  cache_misses: number;
  cache_hit_rate: number | null;
  provider_stats: Record<string, { total: number; successful: number; avg_latency_ms: number }>;
  failure_types: Record<string, number>;
}

export interface ProviderHealthEntry {
  slug: string;
  display_name: string;
  category: string;
  requires_api_key: boolean;
  configured: boolean;
  circuit_state: string;
  failure_count: number;
  health_status: "healthy" | "degraded" | "down" | "unknown";
  active_health?: {
    state: string;
    last_checked_at?: number;
    last_success_at?: number;
    last_failure_at?: number;
    last_failure_reason?: string;
    probe_latency_ms?: number;
    consecutive_failures: number;
    consecutive_successes: number;
  };
  recent_stats: {
    provider?: string;
    total_requests?: number;
    successful_requests?: number;
    avg_latency_ms?: number;
    total_retries?: number;
    total_fallbacks?: number;
  };
}

export interface CircuitSnapshot {
  provider: string;
  state: string;
  failure_count: number;
  last_failure_time?: number;
  last_state_change?: number;
}

// ── Phase 4 Types ──────────────────────────────────────────────────────────────

export interface FaultConfig {
  fault_id: string;
  provider_slug: string;
  fault_type: string;
  fault_type_label: string;
  latency_ms: number;
  duration_seconds: number;
  created_at: number;
  created_by: string;
  note: string;
  is_active: boolean;
  is_expired: boolean;
  is_effective: boolean;
}

export interface FaultStatus {
  enabled: boolean;
  supported_fault_types: Array<{ value: string; label: string }>;
  max_latency_ms: number;
  max_duration_seconds: number;
  registered_providers: string[];
}

export interface IncidentTimelineEntry {
  timestamp: number;
  timestamp_iso: string;
  event: string;
  event_type: string;
}

export interface Incident {
  incident_id: string;
  title: string;
  provider_slug: string;
  provider_display_name: string;
  failure_category: string;
  failure_type: string;
  severity: "critical" | "high" | "medium" | "low";
  status: "open" | "acknowledged" | "investigating" | "resolved";
  started_at: number;
  started_at_iso: string;
  updated_at: number;
  updated_at_iso: string;
  resolved_at: number | null;
  resolved_at_iso: string | null;
  duration_seconds: number | null;
  error_count: number;
  affected_count: number;
  retry_count: number;
  fallback_count: number;
  circuit_state: string;
  circuit_opened: boolean;
  fault_injected: boolean;
  fault_id: string | null;
  summary: string;
  timeline: IncidentTimelineEntry[];
  metadata: Record<string, unknown>;
}

export interface IncidentSummary {
  total: number;
  open: number;
  acknowledged: number;
  investigating: number;
  resolved: number;
  critical_active: number;
  needs_attention: number;
}

// ── Internal fetch helpers ─────────────────────────────────────────────────────

async function apiFetch<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`);
  if (!resp.ok) {
    throw new Error(`API error ${resp.status} on ${path}`);
  }
  return resp.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
    throw new Error((detail as { detail?: string })?.detail ?? `API error ${resp.status} on ${path}`);
  }
  return resp.json() as Promise<T>;
}

async function apiDelete<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
    throw new Error((detail as { detail?: string })?.detail ?? `API error ${resp.status} on ${path}`);
  }
  return resp.json() as Promise<T>;
}

// ── Telemetry APIs ─────────────────────────────────────────────────────────────

export async function fetchRecentRequests(
  limit = 50,
  offset = 0
): Promise<{ requests: TelemetryRequest[]; count: number }> {
  return apiFetch(`/api/v1/telemetry/requests?limit=${limit}&offset=${offset}`);
}

export async function fetchRequestDetail(requestId: string): Promise<TelemetryRequest> {
  return apiFetch(`/api/v1/telemetry/requests/${requestId}`);
}

export async function fetchTelemetrySummary(
  window: "1h" | "6h" | "24h" | "7d" | "30d" = "1h"
): Promise<TelemetrySummary> {
  return apiFetch(`/api/v1/telemetry/summary?window=${window}`);
}

export async function fetchProviderHealth(): Promise<{ providers: ProviderHealthEntry[] }> {
  return apiFetch("/api/v1/telemetry/health");
}

export async function fetchCacheStats(): Promise<{ cache_stats: Record<string, unknown> }> {
  return apiFetch("/api/v1/telemetry/cache");
}

export async function fetchProviderTelemetry(
  slug: string,
  window = "24h"
): Promise<Record<string, unknown>> {
  return apiFetch(`/api/v1/telemetry/providers/${slug}?window=${window}`);
}

// ── Gateway/Resilience APIs ────────────────────────────────────────────────────

export async function fetchCircuitStates(): Promise<{ providers: CircuitSnapshot[] }> {
  return apiFetch("/api/v1/providers/state");
}

export async function fetchProviders(): Promise<{ providers: unknown[] }> {
  return apiFetch("/api/v1/providers");
}

export async function fetchPolicy(): Promise<Record<string, unknown>> {
  return apiFetch("/api/v1/policy");
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  return apiFetch("/health");
}

// ── Phase 4: Fault Injection APIs ─────────────────────────────────────────────

export async function fetchFaultStatus(): Promise<FaultStatus> {
  return apiFetch("/api/v1/faults/status");
}

export async function fetchFaults(
  activeOnly = false
): Promise<{ faults: FaultConfig[]; count: number; enabled: boolean }> {
  return apiFetch(`/api/v1/faults${activeOnly ? "/active" : ""}`);
}

export async function createFault(params: {
  provider_slug: string;
  fault_type: string;
  latency_ms?: number;
  duration_seconds?: number;
  note?: string;
  created_by?: string;
}): Promise<{ created: boolean; fault: FaultConfig; warning: string }> {
  return apiPost("/api/v1/faults", params);
}

export async function disableFault(
  faultId: string
): Promise<{ disabled: boolean; fault: FaultConfig }> {
  return apiDelete(`/api/v1/faults/${faultId}`);
}

export async function clearAllFaults(): Promise<{
  cleared: boolean;
  faults_deactivated: number;
}> {
  return apiDelete("/api/v1/faults");
}

// ── Phase 4: Incident APIs ─────────────────────────────────────────────────────

export async function fetchIncidents(
  status?: string,
  limit = 50
): Promise<{ incidents: Incident[]; count: number; total: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set("status", status);
  return apiFetch(`/api/v1/incidents?${params}`);
}

export async function fetchIncidentSummary(): Promise<IncidentSummary> {
  return apiFetch("/api/v1/incidents/summary");
}

export async function fetchIncident(
  incidentId: string
): Promise<{ incident: Incident }> {
  return apiFetch(`/api/v1/incidents/${incidentId}`);
}

export async function acknowledgeIncident(
  incidentId: string
): Promise<{ acknowledged: boolean; incident: Incident }> {
  return apiPost(`/api/v1/incidents/${incidentId}/acknowledge`, {});
}

export async function investigateIncident(
  incidentId: string
): Promise<{ investigating: boolean; incident: Incident }> {
  return apiPost(`/api/v1/incidents/${incidentId}/investigate`, {});
}

export async function resolveIncident(
  incidentId: string,
  note = ""
): Promise<{ resolved: boolean; incident: Incident }> {
  return apiPost(`/api/v1/incidents/${incidentId}/resolve`, { note });
}

export async function fetchCopilotAnalysis(incidentId: string): Promise<any> {
  return apiFetch(`/api/v1/incidents/${incidentId}/copilot`);
}

export async function askCopilot(incidentId: string, question: string): Promise<{ answer: string }> {
  return apiPost(`/api/v1/incidents/${incidentId}/copilot/ask`, { question });
}

// ── Helpers ────────────────────────────────────────────────────────────────────

export function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export function formatRelativeTime(ts: number): string {
  const diffMs = Date.now() - ts * 1000;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  return `${Math.floor(diffMin / 60)}h ago`;
}

export function circuitStateVariant(state: string): "success" | "warning" | "error" {
  if (state === "closed") return "success";
  if (state === "half-open") return "warning";
  return "error";
}

export function healthStatusVariant(
  status: string
): "success" | "warning" | "error" | "muted" {
  if (status === "healthy") return "success";
  if (status === "degraded") return "warning";
  if (status === "down") return "error";
  return "muted";
}
