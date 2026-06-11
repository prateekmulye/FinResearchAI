/**
 * Typed API client for the FinResearchAI FastAPI backend.
 *
 * DTOs mirror src/api/routes/dto.py and src/api/schemas.py EXACTLY. The SSE
 * stream is handled separately in hooks/useAnalysisStream.ts (it needs a
 * fetch-body reader, not these JSON helpers).
 *
 * In dev, Vite proxies /api + /healthz to the uvicorn backend on :7860, so a
 * relative base just works. In prod the app is served from the same origin.
 */

export const API_BASE = "";

/* ------------------------------------------------------------------ shared */

export type Action = "BUY" | "SELL" | "HOLD";
export type InvestorMode = "Bullish" | "Bearish" | "Neutral";
export type DebateMode = "on" | "off";
export type RunStatus = "running" | "finished" | "error" | "aborted";

/** Mirrors src/llm/schemas.py::FinalDecision. */
export interface FinalDecision {
  action: Action;
  conviction: number; // 0..1
  score: number; // 0..100
  rationale: string;
}

/** Mirrors dto.py::RunCostSummary. */
export interface RunCostSummary {
  cost_usd: number;
  latency_s: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/** One per-node metrics record inside `run_metrics` (free-form on the wire). */
export interface NodeMetric {
  node?: string;
  cost_usd?: number;
  latency_s?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  [key: string]: unknown;
}

/* ----------------------------------------------------------------- library */

export interface RunSummary {
  run_id: string;
  ticker: string;
  debate_mode: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  final_decision: FinalDecision | null;
  cost: RunCostSummary | null;
}

export interface LibraryResponse {
  runs: RunSummary[];
  total: number;
}

export interface ReplayEvent {
  name?: string;
  data?: Record<string, unknown>;
  ts_ms?: number;
  [key: string]: unknown;
}

export interface RunDetail {
  run_id: string;
  source: "warehouse" | "jsonl";
  ticker: string | null;
  debate_mode: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  final_decision: FinalDecision | null;
  report: string | null;
  metrics: NodeMetric[] | null;
  cost: RunCostSummary | null;
  events: ReplayEvent[];
}

/* ------------------------------------------------------------------ market */

export interface Instrument {
  id: number;
  ticker: string;
  exchange: string;
  screener: string;
  name: string | null;
  country: string | null;
  currency: string | null;
  sector: string | null;
  watched: boolean;
}

export interface InstrumentsResponse {
  instruments: Instrument[];
}

export interface PriceBar {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface PricesResponse {
  ticker: string;
  exchange: string;
  interval: string;
  bars: PriceBar[];
}

export interface Fundamentals {
  ticker: string;
  exchange: string;
  ts: string;
  market_cap: number | null;
  pe_ratio: number | null;
  eps: number | null;
  revenue_growth: number | null;
  profit_margin: number | null;
  payload: Record<string, unknown>;
}

export interface NewsItem {
  ts: string;
  title: string;
  url: string;
  source: string | null;
  snippet: string | null;
}

export interface NewsResponse {
  ticker: string;
  exchange: string;
  items: NewsItem[];
}

/** One /api/search hit. Mirrors dto.py::SearchHitOut.
 *
 * `kind` decides what `ref` means: a news url ("news") or a run_id ("run").
 * `score` is the cosine distance (lower = closer) in semantic mode and null in
 * keyword mode — never surface it as a "relevance %", it's a distance.
 */
export interface SearchHit {
  kind: "news" | "run";
  ref: string;
  ticker: string;
  title: string;
  snippet: string | null;
  score: number | null;
  ts: string;
}

/** Mirrors dto.py::SearchResponse. `mode` is the honesty cue: "keyword" means
 * the semantic path was unavailable and we fell back to index matching. */
export interface SearchResponse {
  mode: "semantic" | "keyword";
  hits: SearchHit[];
}

/* -------------------------------------------------------------------- eval */

export interface EvalResult {
  id: number;
  label: string;
  created_at: string;
  summary: Record<string, unknown>;
  pairs: unknown;
}

export interface EvalResultsResponse {
  results: EvalResult[];
}

/* ------------------------------------------------------------------- quota */

export interface QuotaStatus {
  metered: boolean;
  /**
   * True when the quota system EXISTS but its DB read failed (an outage, not
   * absence): the backend answers 200 with null counters rather than a 500.
   * Optional because older payloads omit it (backend default: false).
   */
  degraded?: boolean;
  ip_used: number | null;
  ip_limit: number | null;
  global_used: number | null;
  global_limit: number | null;
  admin: boolean;
}

/* ------------------------------------------------------------------ health */

export interface HealthStatus {
  status: string;
}

/* ------------------------------------------------------- request machinery */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Build a URL with only the defined query params (skips null/undefined/""). */
export function buildUrl(
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
): string {
  const url = `${API_BASE}${path}`;
  if (!params) return url;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${url}?${qs}` : url;
}

async function getJson<T>(
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const url = buildUrl(path, params);
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    throw new ApiError(`GET ${path} -> ${res.status}`, res.status, body);
  }
  return (await res.json()) as T;
}

/* ----------------------------------------------------------------- the API */

export const api = {
  health: (signal?: AbortSignal) =>
    getJson<HealthStatus>("/healthz", undefined, signal),

  quota: (signal?: AbortSignal) =>
    getJson<QuotaStatus>("/api/quota", undefined, signal),

  library: (
    params?: {
      ticker?: string;
      status?: RunStatus;
      limit?: number;
      offset?: number;
    },
    signal?: AbortSignal,
  ) => getJson<LibraryResponse>("/api/library", params, signal),

  run: (runId: string, signal?: AbortSignal) =>
    getJson<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`, undefined, signal),

  instruments: (params?: { q?: string; limit?: number }, signal?: AbortSignal) =>
    getJson<InstrumentsResponse>("/api/market/instruments", params, signal),

  prices: (
    ticker: string,
    params?: { exchange?: string; days?: number },
    signal?: AbortSignal,
  ) =>
    getJson<PricesResponse>(
      `/api/market/${encodeURIComponent(ticker)}/prices`,
      params,
      signal,
    ),

  fundamentals: (
    ticker: string,
    params?: { exchange?: string },
    signal?: AbortSignal,
  ) =>
    getJson<Fundamentals>(
      `/api/market/${encodeURIComponent(ticker)}/fundamentals`,
      params,
      signal,
    ),

  news: (
    ticker: string,
    params?: { exchange?: string; limit?: number },
    signal?: AbortSignal,
  ) =>
    getJson<NewsResponse>(
      `/api/market/${encodeURIComponent(ticker)}/news`,
      params,
      signal,
    ),

  searchResearch: (params: { q: string; limit?: number }, signal?: AbortSignal) =>
    getJson<SearchResponse>("/api/search", params, signal),

  evalResults: (params?: { limit?: number }, signal?: AbortSignal) =>
    getJson<EvalResultsResponse>("/api/eval/results", params, signal),
};

/* ----------------------------------------------------- quota presentation */

export type QuotaState =
  | { kind: "admin"; label: string }
  | { kind: "available"; label: string; remaining: number }
  | { kind: "replay-only"; label: string }
  | { kind: "unmetered"; label: string }
  | { kind: "degraded"; label: string }
  | { kind: "unknown"; label: string };

/**
 * Derive the human-facing quota pill state from the QuotaStatus DTO.
 *
 * Backend semantics (quota.py): metered=false means there is NO quota system
 * (counters null) — an "unmetered demo", distinct from an outage. degraded=true
 * means the system exists but its counters are unreadable right now (a DB
 * outage) — a neutral "quota unavailable", NEVER an exhausted/replay-only
 * claim. When metered, a run consumes BOTH the per-IP and the global budget,
 * so the binding limit is the smaller remaining of the two.
 */
export function deriveQuotaState(q: QuotaStatus | undefined): QuotaState {
  if (!q) return { kind: "unknown", label: "checking quota…" };
  if (q.admin) return { kind: "admin", label: "admin · unlimited" };
  if (!q.metered) return { kind: "unmetered", label: "unmetered demo" };
  if (q.degraded) return { kind: "degraded", label: "quota unavailable" };

  const ipLeft =
    q.ip_limit != null && q.ip_used != null
      ? Math.max(0, q.ip_limit - q.ip_used)
      : Infinity;
  const globalLeft =
    q.global_limit != null && q.global_used != null
      ? Math.max(0, q.global_limit - q.global_used)
      : Infinity;
  const remaining = Math.min(ipLeft, globalLeft);

  if (!Number.isFinite(remaining)) {
    return { kind: "unknown", label: "quota unknown" };
  }
  if (remaining <= 0) {
    return { kind: "replay-only", label: "replay-only" };
  }
  return {
    kind: "available",
    remaining,
    label: `${remaining} live ${remaining === 1 ? "run" : "runs"} left today`,
  };
}
