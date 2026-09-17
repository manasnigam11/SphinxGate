import type {
  Provider, Request, LogEntry, Incident, ApiKey,
  Metric, ResiliencePolicy
} from "../types";

export const PROVIDERS: Provider[] = [
  {
    id: "p1", name: "Nexus AI", slug: "nexus-ai", status: "healthy",
    latency: 312, successRate: 99.4, requests: 842400, errors: 5054,
    lastHealthCheck: "12s ago", circuitState: "closed", availability: 99.97,
    models: [
      { id: "m1", name: "nexus-ultra-2", provider: "Nexus AI", contextWindow: 200000, inputCost: 0.015, outputCost: 0.075, status: "healthy", latency: 312 },
      { id: "m2", name: "nexus-fast", provider: "Nexus AI", contextWindow: 32000, inputCost: 0.003, outputCost: 0.015, status: "healthy", latency: 180 },
      { id: "m3", name: "nexus-embed", provider: "Nexus AI", contextWindow: 8192, inputCost: 0.0001, outputCost: 0, status: "healthy", latency: 45 },
    ]
  },
  {
    id: "p2", name: "Vela Systems", slug: "vela-systems", status: "degraded",
    latency: 1842, successRate: 94.1, requests: 521000, errors: 30721,
    lastHealthCheck: "28s ago", circuitState: "half-open", availability: 98.2,
    models: [
      { id: "m4", name: "vela-7b", provider: "Vela Systems", contextWindow: 128000, inputCost: 0.002, outputCost: 0.008, status: "degraded", latency: 1842 },
      { id: "m5", name: "vela-13b", provider: "Vela Systems", contextWindow: 64000, inputCost: 0.004, outputCost: 0.016, status: "degraded", latency: 2100 },
    ]
  },
  {
    id: "p3", name: "Aether Labs", slug: "aether-labs", status: "healthy",
    latency: 524, successRate: 98.9, requests: 340200, errors: 3754,
    lastHealthCheck: "8s ago", circuitState: "closed", availability: 99.85,
    models: [
      { id: "m6", name: "aether-vision", provider: "Aether Labs", contextWindow: 128000, inputCost: 0.01, outputCost: 0.03, status: "healthy", latency: 524 },
      { id: "m7", name: "aether-code", provider: "Aether Labs", contextWindow: 64000, inputCost: 0.005, outputCost: 0.015, status: "healthy", latency: 420 },
    ]
  },
  {
    id: "p4", name: "Orbital API", slug: "orbital-api", status: "down",
    latency: 0, successRate: 0, requests: 0, errors: 0,
    lastHealthCheck: "4m ago", circuitState: "open", availability: 91.2,
    models: [
      { id: "m8", name: "orbital-base", provider: "Orbital API", contextWindow: 16000, inputCost: 0.001, outputCost: 0.002, status: "down", latency: 0 },
    ]
  },
];

export const REQUESTS: Request[] = [
  { id: "req_8f21c9a4", timestamp: "2026-09-12 14:42:31", provider: "Nexus AI", model: "nexus-ultra-2", status: "success", latency: 428, tokens: 1842, retries: 0, environment: "production", endpoint: "/api/v1/chat/completions" },
  { id: "req_7b30d1e2", timestamp: "2026-09-12 14:42:28", provider: "Vela Systems", model: "vela-7b", status: "timeout", latency: 5000, tokens: 0, retries: 2, environment: "production", endpoint: "/api/v1/chat/completions", error: "upstream_timeout", circuitState: "half-open" },
  { id: "req_4c19f8a1", timestamp: "2026-09-12 14:42:25", provider: "Aether Labs", model: "aether-code", status: "success", latency: 612, tokens: 3240, retries: 0, environment: "staging", endpoint: "/api/v1/completions" },
  { id: "req_9d22b5f0", timestamp: "2026-09-12 14:42:22", provider: "Nexus AI", model: "nexus-fast", status: "success", latency: 194, tokens: 820, retries: 0, environment: "production", endpoint: "/api/v1/chat/completions" },
  { id: "req_1e44c3d8", timestamp: "2026-09-12 14:42:19", provider: "Orbital API", model: "orbital-base", status: "error", latency: 0, tokens: 0, retries: 2, environment: "production", endpoint: "/api/v1/chat/completions", error: "provider_down", circuitState: "open" },
  { id: "req_3f55a2b7", timestamp: "2026-09-12 14:42:16", provider: "Nexus AI", model: "nexus-ultra-2", status: "success", latency: 356, tokens: 2100, retries: 0, environment: "production", endpoint: "/api/v1/chat/completions" },
  { id: "req_6g77d4e9", timestamp: "2026-09-12 14:42:13", provider: "Vela Systems", model: "vela-13b", status: "rate_limited", latency: 12, tokens: 0, retries: 1, environment: "production", endpoint: "/api/v1/chat/completions", error: "rate_limit_exceeded" },
  { id: "req_2h88e5f0", timestamp: "2026-09-12 14:42:10", provider: "Aether Labs", model: "aether-vision", status: "success", latency: 891, tokens: 5420, retries: 0, environment: "development", endpoint: "/api/v1/chat/completions" },
  { id: "req_5i99f6g1", timestamp: "2026-09-12 14:42:07", provider: "Nexus AI", model: "nexus-embed", status: "success", latency: 48, tokens: 512, retries: 0, environment: "production", endpoint: "/api/v1/embeddings" },
  { id: "req_8j00g7h2", timestamp: "2026-09-12 14:42:04", provider: "Nexus AI", model: "nexus-ultra-2", status: "success", latency: 399, tokens: 1680, retries: 0, environment: "production", endpoint: "/api/v1/chat/completions" },
];

export const LOGS: LogEntry[] = [
  { id: "l1", timestamp: "2026-09-12 14:42:31.420", level: "info", service: "router", event: "request_routed", requestId: "req_8f21c9a4", provider: "Nexus AI", latencyMs: 428, retryCount: 0 },
  { id: "l2", timestamp: "2026-09-12 14:42:28.003", level: "error", service: "router", event: "upstream_timeout", requestId: "req_7b30d1e2", provider: "Vela Systems", latencyMs: 5000, retryCount: 2, message: "Provider did not respond within 5000ms after 2 retries" },
  { id: "l3", timestamp: "2026-09-12 14:42:27.891", level: "warn", service: "circuit-breaker", event: "threshold_approaching", requestId: "req_7b30d1e2", provider: "Vela Systems", message: "Failure count 4/5, circuit may open" },
  { id: "l4", timestamp: "2026-09-12 14:42:25.112", level: "info", service: "router", event: "request_routed", requestId: "req_4c19f8a1", provider: "Aether Labs", latencyMs: 612, retryCount: 0 },
  { id: "l5", timestamp: "2026-09-12 14:42:19.445", level: "error", service: "circuit-breaker", event: "circuit_opened", requestId: "req_1e44c3d8", provider: "Orbital API", message: "Circuit opened after 5 consecutive failures" },
  { id: "l6", timestamp: "2026-09-12 14:42:19.001", level: "info", service: "fallback", event: "fallback_activated", requestId: "req_1e44c3d8", provider: "Orbital API", message: "Fallback route activated for Orbital API" },
  { id: "l7", timestamp: "2026-09-12 14:42:16.330", level: "info", service: "router", event: "request_routed", requestId: "req_3f55a2b7", provider: "Nexus AI", latencyMs: 356, retryCount: 0 },
  { id: "l8", timestamp: "2026-09-12 14:42:13.558", level: "warn", service: "rate-limiter", event: "rate_limit_hit", requestId: "req_6g77d4e9", provider: "Vela Systems", message: "Rate limit exceeded: 429 from upstream" },
  { id: "l9", timestamp: "2026-09-12 14:42:10.001", level: "debug", service: "router", event: "provider_selected", requestId: "req_2h88e5f0", provider: "Aether Labs", message: "Selected Aether Labs based on routing policy" },
  { id: "l10", timestamp: "2026-09-12 14:42:07.220", level: "info", service: "router", event: "request_routed", requestId: "req_5i99f6g1", provider: "Nexus AI", latencyMs: 48, retryCount: 0 },
];

export const INCIDENTS: Incident[] = [
  {
    id: "INC-1042", title: "Upstream API Latency Spike", provider: "Vela Systems",
    severity: "high", status: "resolved", started: "2026-09-12 14:31:00",
    resolved: "2026-09-12 14:34:42", duration: "3m 42s",
    affectedRequests: 4821, failureRate: 18.4, peakLatency: 4820,
    timeline: [
      { timestamp: "14:31:00", event: "Elevated latency detected — P95 exceeded 2s threshold", type: "detection" },
      { timestamp: "14:31:14", event: "Retry policy escalated — max retries increased to 3", type: "action" },
      { timestamp: "14:32:08", event: "Circuit breaker opened after 5 consecutive failures", type: "action" },
      { timestamp: "14:32:10", event: "Fallback route activated — routing to Nexus AI", type: "action" },
      { timestamp: "14:33:51", event: "Provider latency normalizing — P95 back under 1s", type: "recovery" },
      { timestamp: "14:34:42", event: "Circuit breaker closed — provider marked healthy", type: "recovery" },
    ],
    aiAnalysis: {
      summary: "Upstream provider Vela Systems experienced a significant latency spike lasting 3 minutes 42 seconds, likely caused by a transient infrastructure event on their end. The gateway's resilience stack responded automatically.",
      observedPatterns: [
        "P95 latency increased from 820ms to 4.82s over 4 minutes",
        "Timeout rate reached 18.4% of requests",
        "7 consecutive failures triggered circuit breaker threshold",
        "Recovery detected within 90 seconds of circuit opening"
      ],
      likelyCause: "Probable transient infrastructure degradation on Vela Systems upstream. Pattern matches a cold-start or overload event — not a sustained outage.",
      actionsTaken: [
        "Retry policy escalated automatically",
        "Circuit breaker opened after threshold hit",
        "Fallback routing activated to Nexus AI",
        "Alerts dispatched to on-call engineer"
      ],
      recommendations: [
        "Consider increasing timeout from 2.0s to 2.5s to reduce unnecessary retries on slow responses",
        "Review Vela Systems SLA — this is the 3rd latency event this month",
        "Add a secondary fallback to Aether Labs for redundancy depth"
      ],
      confidence: 87,
      affectedComponents: ["router", "circuit-breaker", "fallback", "vela-systems"]
    }
  },
  {
    id: "INC-1041", title: "Orbital API Complete Outage", provider: "Orbital API",
    severity: "critical", status: "investigating", started: "2026-09-12 14:38:00",
    affectedRequests: 1240, failureRate: 100, peakLatency: 0,
    timeline: [
      { timestamp: "14:38:00", event: "Health check failure detected — no response from provider", type: "detection" },
      { timestamp: "14:38:05", event: "Circuit breaker opened immediately — connection refused", type: "action" },
      { timestamp: "14:38:06", event: "Fallback routing activated", type: "action" },
      { timestamp: "14:42:00", event: "Provider still unreachable — investigating", type: "info" },
    ]
  },
  {
    id: "INC-1040", title: "Rate Limit Exhaustion", provider: "Vela Systems",
    severity: "medium", status: "resolved", started: "2026-09-12 11:14:00",
    resolved: "2026-09-12 11:29:00", duration: "15m",
    affectedRequests: 840, failureRate: 6.2, peakLatency: 12,
    timeline: [
      { timestamp: "11:14:00", event: "Rate limit 429s detected from Vela Systems", type: "detection" },
      { timestamp: "11:14:30", event: "Request queuing enabled — rate limiter activated", type: "action" },
      { timestamp: "11:29:00", event: "Rate limit window reset — normal operation resumed", type: "recovery" },
    ]
  },
];

export const API_KEYS: ApiKey[] = [
  { id: "k1", name: "Production Gateway", keyPreview: "sk_live_••••••••8F2A", created: "2026-01-15", lastUsed: "2026-09-12", environment: "production", status: "active", requests: 1840000 },
  { id: "k2", name: "Staging Integration", keyPreview: "sk_stg_••••••••3D1B", created: "2026-03-22", lastUsed: "2026-09-11", environment: "staging", status: "active", requests: 240000 },
  { id: "k3", name: "Dev Environment", keyPreview: "sk_dev_••••••••9C4F", created: "2026-05-08", lastUsed: "2026-09-12", environment: "development", status: "active", requests: 84000 },
  { id: "k4", name: "Legacy Integration v1", keyPreview: "sk_live_••••••••2A7E", created: "2025-11-01", lastUsed: "2026-06-30", environment: "production", status: "revoked", requests: 320000 },
];

export const RESILIENCE_POLICY: ResiliencePolicy = {
  id: "default", name: "Default Policy",
  enabled: true, timeout: 2500, maxRetries: 2,
  initialBackoff: 500, maxBackoff: 5000,
  circuitBreakerThreshold: 5, circuitBreakerWindow: 30,
  fallbackEnabled: true, rateLimitRps: 100,
};

function generateSparkline(base: number, variance: number, points = 20): Metric[] {
  return Array.from({ length: points }, (_, i) => ({
    timestamp: `${i}`,
    value: Math.max(0, base + (Math.random() - 0.5) * variance),
  }));
}

export const METRICS = {
  totalRequests: { value: "1.84M", change: "+12.4%", positive: true, sparkline: generateSparkline(30000, 8000) },
  successRate: { value: "98.7%", change: "+0.8%", positive: true, sparkline: generateSparkline(98, 2) },
  avgLatency: { value: "412ms", change: "-8.2%", positive: true, sparkline: generateSparkline(412, 100) },
  errorRate: { value: "1.3%", change: "-0.4%", positive: true, sparkline: generateSparkline(1.3, 0.5) },
};

export const REQUEST_VOLUME: Metric[] = Array.from({ length: 48 }, (_, i) => ({
  timestamp: `${Math.floor(i / 2)}:${i % 2 === 0 ? "00" : "30"}`,
  value: Math.max(0, 1800 + Math.sin(i * 0.3) * 400 + (Math.random() - 0.5) * 300),
}));

export const ERROR_RATE_SERIES: Metric[] = Array.from({ length: 48 }, (_, i) => ({
  timestamp: `${Math.floor(i / 2)}:${i % 2 === 0 ? "00" : "30"}`,
  value: Math.max(0, 1.3 + Math.sin(i * 0.5) * 0.8 + (Math.random() - 0.5) * 0.4),
}));

export const LATENCY_PERCENTILES = {
  p50: generateSparkline(280, 50, 48),
  p95: generateSparkline(820, 200, 48),
  p99: generateSparkline(2100, 600, 48),
};

export const HEALTH_TIMELINE = [
  { time: "09:31", status: "healthy", event: "All systems operational" },
  { time: "09:42", status: "warn", event: "Vela Systems latency increasing" },
  { time: "09:44", status: "degraded", event: "Vela Systems degraded" },
  { time: "09:48", status: "error", event: "Circuit breaker opened" },
  { time: "09:51", status: "warn", event: "Recovery in progress" },
  { time: "09:52", status: "healthy", event: "System healthy" },
  { time: "14:38", status: "error", event: "Orbital API unreachable" },
  { time: "14:42", status: "degraded", event: "Orbital API down (investigating)" },
];
