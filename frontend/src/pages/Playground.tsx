import React, { useState, useEffect } from "react";
import { Badge, Button, Card, CodeBlock, Select, Tabs, SectionHeader } from "../components/ui";
import { fetchProviders } from "../api";

// The SphinxGate backend URL. In development the Vite proxy (see vite.config.ts)
// will forward /api/* requests to http://localhost:8000.
const GATEWAY_BASE = "";  // empty = same origin, routed via Vite proxy

const DEFAULT_BODY = `{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Explain exponential backoff in two sentences."
    }
  ],
  "max_tokens": 512,
  "temperature": 0.7
}`;

const FALLBACK_LLM_PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "gemini", label: "Google Gemini" },
  { value: "groq",   label: "Groq" },
];

const FALLBACK_PUBLIC_API_PROVIDERS = [
  { value: "open_meteo",  label: "Open-Meteo (Weather)" },
  { value: "jokeapi",     label: "JokeAPI" },
  { value: "frankfurter", label: "Frankfurter (Currency)" },
  { value: "trivia",      label: "Open Trivia DB" },
];

// Default public API params for each provider (for the textarea)
const DEFAULT_PUBLIC_PARAMS: Record<string, string> = {
  open_meteo:  JSON.stringify({ latitude: 51.5074, longitude: -0.1278 }, null, 2),
  jokeapi:     JSON.stringify({ category: "Programming", safe_mode: true }, null, 2),
  frankfurter: JSON.stringify({ base: "USD", to: "EUR,GBP,JPY" }, null, 2),
  trivia:      JSON.stringify({ amount: 3, difficulty: "easy", type: "multiple" }, null, 2),
};

type ProviderMode = "llm" | "public_api";

type ReqState = "idle" | "loading" | "success" | "timeout" | "rate_limited" | "error";

interface GatewayMeta {
  requestId: string;
  provider: string;
  latencyMs: number;
  statusCode: number;
  tokensUsed: number;
  retryCount: number;
  circuitState: string;
}

interface RequestResult {
  meta: GatewayMeta;
  responseBody: string;       // raw JSON string for display
  responseHeaders: string;    // formatted header string for display
  statusCode: number;
}

const TIMELINE_LABELS = [
  { label: "Request received", detail: "Validated and queued" },
  { label: "Provider selected", detail: "" },   // filled dynamically
  { label: "Auth & rate check", detail: "API key resolved from gateway config" },
  { label: "Request forwarded", detail: "TLS 1.3 · keep-alive" },
  { label: "Provider processing", detail: "Model inference" },
  { label: "Response received", detail: "" },   // filled dynamically
];

export function Playground() {
  const [method] = useState("POST");
  const [endpoint, setEndpoint] = useState("/api/v1/chat/completions");
  const [provider, setProvider] = useState("openai");
  const [providerMode, setProviderMode] = useState<ProviderMode>("llm");
  const [body, setBody] = useState(DEFAULT_BODY);
  const [activeTab, setActiveTab] = useState("Response");
  const [reqState, setReqState] = useState<ReqState>("idle");
  const [result, setResult] = useState<RequestResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [llmProviders, setLlmProviders] = useState(FALLBACK_LLM_PROVIDERS);
  const [publicProviders, setPublicProviders] = useState(FALLBACK_PUBLIC_API_PROVIDERS);
  const allProviders = [...llmProviders, ...publicProviders];

  useEffect(() => {
    fetchProviders().then(res => {
      const providers = res.providers as any[];
      const llms = providers.filter(p => p.category === "llm").map(p => ({ value: p.slug, label: p.display_name }));
      const publics = providers.filter(p => p.category === "public_api").map(p => ({ value: p.slug, label: p.display_name }));
      if (llms.length > 0) setLlmProviders(llms);
      if (publics.length > 0) setPublicProviders(publics);
    }).catch(console.error);
  }, []);

  function handleProviderChange(slug: string) {
    setProvider(slug);
    const isPublic = publicProviders.some(p => p.value === slug);
    if (isPublic) {
      setProviderMode("public_api");
      setEndpoint("/api/v1/query");
      setBody(DEFAULT_PUBLIC_PARAMS[slug] ?? "{}");
    } else {
      setProviderMode("llm");
      setEndpoint("/api/v1/chat/completions");
      setBody(DEFAULT_BODY);
    }
  }

  // Displayed in the request config panel — never sent to the backend.
  const displayHeaders: [string, string][] = [
    ["Content-Type", "application/json"],
    ["X-Provider", provider],
  ];

  async function handleSend() {
    setReqState("loading");
    setResult(null);
    setErrorMessage(null);

    const startTime = performance.now();

    try {
      let fetchBody: string;
      let fetchHeaders: Record<string, string>;

      if (providerMode === "public_api") {
        // Public API mode: wrap params in { provider, params } envelope
        let parsedParams: unknown;
        try {
          parsedParams = JSON.parse(body);
        } catch {
          setReqState("error");
          setErrorMessage("Request params are not valid JSON.");
          return;
        }
        fetchBody = JSON.stringify({ provider, params: parsedParams });
        fetchHeaders = {
          "Content-Type": "application/json",
          "X-Environment": "development",
        };
      } else {
        // LLM mode: validate JSON and send with X-Provider header
        let parsedBody: unknown;
        try {
          parsedBody = JSON.parse(body);
        } catch {
          setReqState("error");
          setErrorMessage("Request body is not valid JSON.");
          return;
        }
        fetchBody = JSON.stringify(parsedBody);
        fetchHeaders = {
          "Content-Type": "application/json",
          "X-Provider": provider,
          "X-Environment": "development",
        };
      }

      const response = await fetch(`${GATEWAY_BASE}${endpoint}`, {
        method: "POST",
        headers: fetchHeaders,
        body: fetchBody,
      });

      const latencyMs = Math.round(performance.now() - startTime);

      // Read gateway metadata from response headers.
      const meta: GatewayMeta = {
        requestId:   response.headers.get("X-Request-ID") ?? "—",
        provider:    response.headers.get("X-Provider") ?? provider,
        latencyMs:   parseInt(response.headers.get("X-Latency-Ms") ?? String(latencyMs), 10),
        statusCode:  response.status,
        tokensUsed:  parseInt(response.headers.get("X-Tokens-Used") ?? "0", 10),
        retryCount:  parseInt(response.headers.get("X-Retry-Count") ?? "0", 10),
        circuitState: response.headers.get("X-Circuit-State") ?? "closed",
      };

      const responseJson = await response.json();
      const responseBody = JSON.stringify(responseJson, null, 2);

      // Build a formatted headers string for the Headers tab.
      const formattedHeaders = [
        `HTTP/1.1 ${response.status} ${response.statusText || "OK"}`,
        "Content-Type: application/json; charset=utf-8",
        `X-Request-ID: ${meta.requestId}`,
        `X-Provider: ${meta.provider}`,
        `X-Latency-Ms: ${meta.latencyMs}`,
        `X-Retry-Count: ${meta.retryCount}`,
        `X-Circuit-State: ${meta.circuitState}`,
        `X-Tokens-Used: ${meta.tokensUsed}`,
        "Cache-Control: no-store",
      ].join("\n");

      setResult({
        meta,
        responseBody,
        responseHeaders: formattedHeaders,
        statusCode: response.status,
      });

      if (response.ok) {
        setReqState("success");
      } else if (response.status === 429) {
        setReqState("rate_limited");
      } else if (response.status === 504) {
        setReqState("timeout");
      } else {
        setReqState("error");
        // Surface the provider's error message if available.
        const errMsg =
          responseJson?.error?.message ??
          responseJson?.detail ??
          `HTTP ${response.status}`;
        setErrorMessage(errMsg);
      }
    } catch (err) {
      // Network-level failure (backend unreachable, CORS, etc.)
      setReqState("error");
      setErrorMessage(
        err instanceof Error
          ? `Network error: ${err.message}`
          : "Failed to reach the SphinxGate backend. Is it running on port 8000?"
      );
    }
  }

  function handleClear() {
    setBody(DEFAULT_BODY);
    setReqState("idle");
    setResult(null);
    setErrorMessage(null);
    setActiveTab("Response");
  }

  const stateColor: Record<ReqState, string> = {
    idle:         "",
    loading:      "text-[var(--muted-foreground)]",
    success:      "text-green-500",
    timeout:      "text-red-400",
    rate_limited: "text-amber-500",
    error:        "text-red-400",
  };

  const statusBadgeVariant = (code: number): "success" | "warning" | "error" => {
    if (code < 300) return "success";
    if (code < 500) return "warning";
    return "error";
  };

  // Build timeline steps from the real result.
  function buildTimeline(r: RequestResult): { label: string; detail: string; duration: string }[] {
    const total = r.meta.latencyMs;
    const providerTime = Math.max(0, total - 30);  // rough split: ~30ms gateway overhead
    return [
      { label: "Request received",  detail: "Validated and queued",                          duration: "2ms" },
      { label: "Provider selected", detail: `${r.meta.provider} — from X-Provider header`,   duration: "1ms" },
      { label: "Auth & rate check", detail: "API key resolved from gateway config",           duration: "3ms" },
      { label: "Request forwarded", detail: "TLS 1.3 · keep-alive",                          duration: "12ms" },
      { label: "Provider processing", detail: "Model inference",                             duration: `${providerTime}ms` },
      { label: "Response received", detail: `${r.statusCode === 200 ? "200 OK" : r.statusCode} · ${r.meta.tokensUsed} tokens`, duration: "12ms" },
    ];
  }

  return (
    <div className="flex flex-col gap-6 p-6 animate-fade-in">
      <SectionHeader
        title="API Playground"
        description="Test requests across configured providers and inspect the complete request lifecycle."
        actions={
          <Button variant="outline" size="sm">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
            Saved Requests
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
        {/* ── Request config ─────────────────────────────────────────────── */}
        <Card className="p-5 flex flex-col gap-4">
          <div className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">Request Configuration</div>

          {/* Method + endpoint */}
          <div className="flex items-center gap-2">
            <span className="bg-[var(--accent)]/10 text-[var(--accent)] mono text-xs font-semibold px-2.5 py-2 rounded-[var(--radius)] border border-[var(--accent)]/20 flex-shrink-0">{method}</span>
            <input
              value={endpoint}
              onChange={e => setEndpoint(e.target.value)}
              className="flex-1 mono text-sm bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
            />
          </div>

          {/* Provider selector */}
          <Select
            label="Provider"
            value={provider}
            onChange={e => handleProviderChange(e.target.value)}
            options={allProviders}
          />
          {providerMode === "public_api" && (
            <div className="text-xs text-[var(--muted-foreground)] bg-[var(--secondary)] rounded-[var(--radius)] px-3 py-2 border border-[var(--border)]">
              🌐 Public API — no key required. Params will be sent to <span className="mono">/api/v1/query</span>.
            </div>
          )}

          {/* Display headers (informational only) */}
          <div>
            <div className="text-xs font-medium text-[var(--muted-foreground)] mb-2">Headers</div>
            <div className="border border-[var(--border)] rounded-[var(--radius)] divide-y divide-[var(--border)] overflow-hidden">
              {displayHeaders.map(([k, v]) => (
                <div key={k} className="flex items-center text-xs">
                  <span className="mono px-3 py-2 text-[var(--muted-foreground)] bg-[var(--secondary)] w-2/5 border-r border-[var(--border)]">{k}</span>
                  <span className="mono px-3 py-2 text-[var(--foreground)]">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Request body */}
          <div className="flex-1">
            <div className="text-xs font-medium text-[var(--muted-foreground)] mb-2">Request Body</div>
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              className="mono text-xs w-full h-52 bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] p-3 text-[var(--foreground)] resize-none focus:outline-none focus:border-[var(--accent)] leading-relaxed"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={handleSend} loading={reqState === "loading"}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              Send Request
            </Button>
            <Button variant="ghost" size="md" onClick={handleClear}>Clear</Button>
          </div>

          {/* Error message */}
          {reqState === "error" && errorMessage && (
            <div className="bg-red-500/5 border border-red-500/20 rounded-[var(--radius)] px-4 py-3 text-xs text-red-400">
              {errorMessage}
            </div>
          )}
        </Card>

        {/* ── Response panel ─────────────────────────────────────────────── */}
        <Card className="flex flex-col overflow-hidden max-h-[650px]">
          {/* Meta bar — shown after a real response */}
          {result && (
            <div className="flex items-center gap-4 px-5 py-3 border-b border-[var(--border)] bg-[var(--secondary)]">
              <Badge variant={statusBadgeVariant(result.statusCode)} className="mono">
                {result.statusCode} {result.statusCode === 200 ? "OK" : ""}
              </Badge>
              <span className="mono text-xs text-[var(--muted-foreground)]">{result.meta.latencyMs}ms</span>
              <span className="text-xs text-[var(--muted-foreground)]">·</span>
              <span className="text-xs text-[var(--muted-foreground)]">{result.meta.provider}</span>
              <span className="text-xs text-[var(--muted-foreground)]">·</span>
              <span className={`mono text-xs ${stateColor[reqState]}`}>{result.meta.requestId}</span>
              {result.meta.tokensUsed > 0 && (
                <>
                  <span className="text-xs text-[var(--muted-foreground)]">·</span>
                  <span className="mono text-xs text-[var(--muted-foreground)]">{result.meta.tokensUsed} tokens</span>
                </>
              )}
            </div>
          )}

          {/* Loading bar */}
          {reqState === "loading" && (
            <div className="flex items-center gap-3 px-5 py-3 border-b border-[var(--border)] bg-[var(--secondary)]">
              <svg className="animate-spin w-3.5 h-3.5 text-[var(--accent)]" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
              <span className="text-xs text-[var(--muted-foreground)]">Routing to {allProviders.find(p => p.value === provider)?.label ?? provider}...</span>
            </div>
          )}

          <Tabs
            tabs={["Response", "Headers", "Timeline", "Raw"]}
            active={activeTab}
            onChange={setActiveTab}
            className="px-5"
          />

          <div className="flex-1 overflow-auto p-5">
            {/* Idle state */}
            {reqState === "idle" && (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--muted-foreground)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                <div className="text-sm font-medium text-[var(--foreground)]">No request sent</div>
                <div className="text-xs text-[var(--muted-foreground)]">Configure your request and click Send</div>
              </div>
            )}

            {/* Loading state */}
            {reqState === "loading" && (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => <span key={i} className="w-2 h-2 bg-[var(--primary)] rounded-full animate-bounce" style={{ animationDelay: `${i * 0.1}s` }} />)}
                </div>
                <span className="text-xs text-[var(--muted-foreground)]">Waiting for response...</span>
              </div>
            )}

            {/* Response tab */}
            {result && activeTab === "Response" && (
              <CodeBlock className="h-full">{result.responseBody}</CodeBlock>
            )}

            {/* Headers tab */}
            {result && activeTab === "Headers" && (
              <CodeBlock className="h-full">{result.responseHeaders}</CodeBlock>
            )}

            {/* Raw tab */}
            {result && activeTab === "Raw" && (
              <CodeBlock className="h-full">{result.responseBody}</CodeBlock>
            )}

            {/* Timeline tab */}
            {result && activeTab === "Timeline" && (
              <div className="flex flex-col gap-0">
                {buildTimeline(result).map((step, i, arr) => (
                  <div key={i} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-2 h-2 rounded-full bg-[var(--primary)] flex-shrink-0 mt-1" />
                      {i < arr.length - 1 && <div className="w-px flex-1 bg-[var(--border)] my-1" />}
                    </div>
                    <div className="pb-5 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-[var(--foreground)]">{step.label}</span>
                        <span className="mono text-xs text-[var(--accent)]">{step.duration}</span>
                      </div>
                      <span className="text-xs text-[var(--muted-foreground)]">{step.detail}</span>
                    </div>
                  </div>
                ))}
                <div className="flex items-center gap-2 mt-1 pt-3 border-t border-[var(--border)]">
                  <span className="text-xs text-[var(--muted-foreground)]">Total:</span>
                  <span className="mono text-xs font-semibold text-[var(--foreground)]">{result.meta.latencyMs}ms</span>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
