export type Environment = "development" | "staging" | "production";

export type ProviderStatus = "healthy" | "degraded" | "down";

export type CircuitState = "closed" | "half-open" | "open";

export type IncidentSeverity = "critical" | "high" | "medium" | "low";

export type IncidentStatus = "investigating" | "mitigating" | "resolved";

export type LogLevel = "info" | "warn" | "error" | "debug";

export type RequestStatus = "success" | "error" | "timeout" | "rate_limited";

export interface Provider {
  id: string;
  name: string;
  slug: string;
  status: ProviderStatus;
  latency: number;
  successRate: number;
  requests: number;
  errors: number;
  lastHealthCheck: string;
  models: Model[];
  circuitState: CircuitState;
  availability: number;
}

export interface Model {
  id: string;
  name: string;
  provider: string;
  contextWindow: number;
  inputCost: number;
  outputCost: number;
  status: ProviderStatus;
  latency: number;
}

export interface Request {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  status: RequestStatus;
  latency: number;
  tokens: number;
  retries: number;
  environment: Environment;
  endpoint: string;
  userId?: string;
  error?: string;
  circuitState?: CircuitState;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  service: string;
  event: string;
  requestId: string;
  provider: string;
  latencyMs?: number;
  retryCount?: number;
  message?: string;
  data?: Record<string, unknown>;
}

export interface Incident {
  id: string;
  title: string;
  provider: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  started: string;
  resolved?: string;
  duration?: string;
  affectedRequests: number;
  failureRate: number;
  peakLatency: number;
  timeline: IncidentEvent[];
  aiAnalysis?: AIAnalysis;
}

export interface IncidentEvent {
  timestamp: string;
  event: string;
  type: "detection" | "action" | "recovery" | "info";
}

export interface AIAnalysis {
  summary: string;
  observedPatterns: string[];
  likelyCause: string;
  actionsTaken: string[];
  recommendations: string[];
  confidence: number;
  affectedComponents: string[];
}

export interface ResiliencePolicy {
  id: string;
  name: string;
  enabled: boolean;
  timeout: number;
  maxRetries: number;
  initialBackoff: number;
  maxBackoff: number;
  circuitBreakerThreshold: number;
  circuitBreakerWindow: number;
  fallbackEnabled: boolean;
  rateLimitRps: number;
}

export interface ApiKey {
  id: string;
  name: string;
  keyPreview: string;
  created: string;
  lastUsed: string;
  environment: Environment;
  status: "active" | "revoked";
  requests: number;
}

export interface Metric {
  timestamp: string;
  value: number;
}

export interface HealthStatus {
  overall: ProviderStatus;
  providers: Provider[];
  uptime: number;
  lastUpdated: string;
}

export interface CircuitBreakerEvent {
  timestamp: string;
  state: CircuitState;
  failureCount: number;
  event: string;
}
