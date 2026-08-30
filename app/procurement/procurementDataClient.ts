export type ProcurementNoticeType = "tender" | "inquiry";
export type ProcurementWorkflow = "recent" | "recommended" | "selected" | "submitted" | "results";

export type ProcurementQueryContext = {
  noticeType: ProcurementNoticeType;
  workflow: ProcurementWorkflow | string;
  page: number;
  pageSize: number;
  filters?: Record<string, string | string[] | number | boolean | null | undefined>;
  sort?: string;
};

export type ProcurementQueryPayload<T = unknown> = {
  count?: number;
  page: number;
  page_size: number;
  has_more?: boolean;
  results: T[];
  domain_revision?: number;
};

export type ProcurementCacheEntry<T = unknown> = {
  payload: ProcurementQueryPayload<T>;
  fetchedAt: number;
};

export type ProcurementLoadResult<T = unknown> = {
  payload: ProcurementQueryPayload<T>;
  source: "network" | "cache";
  stale: boolean;
};

export type ProcurementDataClientOptions = {
  endpoint?: string;
  cacheTtlMs?: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
  // Retained for constructor compatibility. Notice ownership is active-view scoped and
  // abortAllExcept keeps the notice path at one current context rather than a shared queue.
  concurrency?: number;
};

const WORKFLOW_ALLOWLIST = new Set<ProcurementWorkflow>([
  "recent",
  "recommended",
  "selected",
  "submitted",
  "results",
]);
const TRANSIENT_STATUSES = new Set([502, 503, 504]);
const RETRY_DELAY_MS = 750;

export function normalizeProcurementWorkflow(value: string): ProcurementWorkflow {
  return WORKFLOW_ALLOWLIST.has(value as ProcurementWorkflow)
    ? value as ProcurementWorkflow
    : "recent";
}

function normalizedFilterEntries(filters: ProcurementQueryContext["filters"] = {}) {
  return Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => {
      const normalized = Array.isArray(value)
        ? [...value].map((item) => String(item)).sort()
        : String(value);
      return [key, normalized] as const;
    })
    .sort(([left], [right]) => left.localeCompare(right));
}

export function procurementQueryKey(context: ProcurementQueryContext) {
  return JSON.stringify({
    noticeType: context.noticeType,
    workflow: normalizeProcurementWorkflow(context.workflow),
    page: Math.max(1, context.page),
    pageSize: Math.max(1, context.pageSize),
    sort: context.sort || "",
    filters: normalizedFilterEntries(context.filters),
  });
}

function appendQueryValue(params: URLSearchParams, key: string, value: unknown) {
  if (value === undefined || value === null || value === "") return;
  if (Array.isArray(value)) {
    for (const item of value) params.append(key, String(item));
    return;
  }
  params.set(key, String(value));
}

export function procurementQueryParams(context: ProcurementQueryContext) {
  const params = new URLSearchParams();
  params.set("notice_type", context.noticeType);
  params.set("workflow", normalizeProcurementWorkflow(context.workflow));
  params.set("page", String(Math.max(1, context.page)));
  params.set("page_size", String(Math.max(1, context.pageSize)));
  if (context.sort) params.set("ordering", context.sort);
  for (const [key, value] of Object.entries(context.filters || {})) appendQueryValue(params, key, value);
  return params;
}

function abortError() {
  return new DOMException("Request aborted", "AbortError");
}

function waitForRetry(milliseconds: number, signal: AbortSignal) {
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise<void>((resolve, reject) => {
    const timer = globalThis.setTimeout(resolve, milliseconds);
    signal.addEventListener("abort", () => {
      globalThis.clearTimeout(timer);
      reject(abortError());
    }, { once: true });
  });
}

export class ProcurementDataClient {
  private readonly endpoint: string;
  private readonly cacheTtlMs: number;
  private readonly now: () => number;
  private readonly fetchImpl: typeof fetch;
  private readonly cache = new Map<string, ProcurementCacheEntry>();
  private readonly inflight = new Map<string, Promise<ProcurementQueryPayload>>();
  private readonly controllers = new Map<string, AbortController>();
  private readonly generation = new Map<string, number>();

  constructor(options: ProcurementDataClientOptions = {}) {
    this.endpoint = options.endpoint || "/api/v1/procurement/ui/notices/";
    this.cacheTtlMs = options.cacheTtlMs ?? 60_000;
    this.now = options.now || Date.now;
    // Never store the native Window.fetch function as an unbound instance method.
    // Chromium requires the Window receiver for native fetch; the wrapper preserves
    // dependency injection while always invoking the platform fetch with its own realm.
    this.fetchImpl = options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  getCached<T = unknown>(context: ProcurementQueryContext): ProcurementLoadResult<T> | null {
    const key = procurementQueryKey(context);
    const entry = this.cache.get(key) as ProcurementCacheEntry<T> | undefined;
    if (!entry) return null;
    return {
      payload: entry.payload,
      source: "cache",
      stale: this.now() - entry.fetchedAt > this.cacheTtlMs,
    };
  }

  async load<T = unknown>(context: ProcurementQueryContext): Promise<ProcurementLoadResult<T>> {
    const key = procurementQueryKey(context);
    const payload = await this.fetchKey<T>(key, context);
    return { payload, source: "network", stale: false };
  }

  async staleWhileRevalidate<T = unknown>(
    context: ProcurementQueryContext,
    onRefresh?: (result: ProcurementLoadResult<T>) => void,
  ): Promise<ProcurementLoadResult<T>> {
    const cached = this.getCached<T>(context);
    if (!cached) return this.load<T>(context);
    void this.load<T>(context)
      .then((fresh) => onRefresh?.(fresh))
      .catch(() => undefined);
    return cached;
  }

  prefetch(context: ProcurementQueryContext) {
    const cached = this.getCached(context);
    if (cached && !cached.stale) return Promise.resolve(cached);
    return this.load(context);
  }

  invalidate(predicate?: (contextKey: string) => boolean) {
    if (!predicate) {
      this.cache.clear();
      return;
    }
    for (const key of this.cache.keys()) {
      if (predicate(key)) this.cache.delete(key);
    }
  }

  abort(context: ProcurementQueryContext) {
    this.abortKey(procurementQueryKey(context));
  }

  abortAllExcept(context: ProcurementQueryContext) {
    const keep = procurementQueryKey(context);
    for (const key of [...this.controllers.keys()]) {
      if (key !== keep) this.abortKey(key);
    }
  }

  private abortKey(key: string) {
    this.controllers.get(key)?.abort();
    this.controllers.delete(key);
    this.inflight.delete(key);
    this.generation.set(key, (this.generation.get(key) || 0) + 1);
  }

  private async fetchNoticePayload<T>(requestUrl: string, signal: AbortSignal): Promise<ProcurementQueryPayload<T>> {
    let lastError: unknown;
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      if (signal.aborted) throw abortError();
      try {
        const response = await this.fetchImpl(requestUrl, {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
          signal,
        });
        if (TRANSIENT_STATUSES.has(response.status) && attempt < 2) {
          await waitForRetry(RETRY_DELAY_MS, signal);
          continue;
        }
        if (!response.ok) throw new Error(`procurement-http-${response.status}`);
        return await response.json() as ProcurementQueryPayload<T>;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") throw error;
        lastError = error;
        const retryableNetworkError = error instanceof TypeError;
        if (attempt < 2 && retryableNetworkError) {
          await waitForRetry(RETRY_DELAY_MS, signal);
          continue;
        }
        throw error;
      }
    }
    throw lastError instanceof Error ? lastError : new Error("procurement-request-failed");
  }

  private fetchKey<T>(key: string, context: ProcurementQueryContext): Promise<ProcurementQueryPayload<T>> {
    const existing = this.inflight.get(key) as Promise<ProcurementQueryPayload<T>> | undefined;
    if (existing) return existing;

    const controller = new AbortController();
    const requestGeneration = (this.generation.get(key) || 0) + 1;
    this.generation.set(key, requestGeneration);
    this.controllers.set(key, controller);
    const params = procurementQueryParams(context);
    const requestUrl = `${this.endpoint}?${params.toString()}`;

    // ProcurementDataClient is the single owner of notice reads. An uncached active-view
    // load enters browser fetch directly; it cannot be rejected by a second queued/circuit
    // governor before a Network request exists. Context single-flight, active-view abort,
    // stale-generation rejection and one bounded transient retry remain enforced here.
    const baseRequest = this.fetchNoticePayload<T>(requestUrl, controller.signal).then((payload) => {
      if (this.generation.get(key) !== requestGeneration) {
        throw new DOMException("Stale procurement response discarded", "AbortError");
      }
      this.cache.set(key, { payload, fetchedAt: this.now() });
      return payload;
    });

    const trackedRequest = baseRequest.finally(() => {
      if (this.inflight.get(key) === trackedRequest) this.inflight.delete(key);
      if (this.controllers.get(key) === controller) this.controllers.delete(key);
    });

    this.inflight.set(key, trackedRequest as Promise<ProcurementQueryPayload>);
    return trackedRequest;
  }
}

export const procurementDataClient = new ProcurementDataClient();