import { ProcurementRequestClient } from "./procurementRequestClient";

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
  concurrency?: number;
};

const WORKFLOW_ALLOWLIST = new Set<ProcurementWorkflow>([
  "recent",
  "recommended",
  "selected",
  "submitted",
  "results",
]);

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

export class ProcurementDataClient {
  private readonly endpoint: string;
  private readonly cacheTtlMs: number;
  private readonly now: () => number;
  private readonly requestClient: ProcurementRequestClient;
  private readonly cache = new Map<string, ProcurementCacheEntry>();
  private readonly inflight = new Map<string, Promise<ProcurementQueryPayload>>();
  private readonly controllers = new Map<string, AbortController>();
  private readonly generation = new Map<string, number>();

  constructor(options: ProcurementDataClientOptions = {}) {
    this.endpoint = options.endpoint || "/api/v1/procurement/ui/notices/";
    this.cacheTtlMs = options.cacheTtlMs ?? 60_000;
    this.now = options.now || Date.now;
    this.requestClient = new ProcurementRequestClient({
      concurrency: options.concurrency ?? 3,
      fetchImpl: options.fetchImpl,
      now: this.now,
    });
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

  private fetchKey<T>(key: string, context: ProcurementQueryContext): Promise<ProcurementQueryPayload<T>> {
    const existing = this.inflight.get(key) as Promise<ProcurementQueryPayload<T>> | undefined;
    if (existing) return existing;

    const controller = new AbortController();
    const requestGeneration = (this.generation.get(key) || 0) + 1;
    this.generation.set(key, requestGeneration);
    this.controllers.set(key, controller);
    const params = procurementQueryParams(context);
    const requestUrl = `${this.endpoint}?${params.toString()}`;

    // DataClient owns same-context single-flight. The lower request governor key must include
    // this generation so a newly started load can never reuse a Promise that belongs to an
    // earlier aborted generation of the same notice context.
    const requestGovernorKey = `notice:${key}:generation:${requestGeneration}`;
    const baseRequest = this.requestClient.getJson<ProcurementQueryPayload<T>>(requestUrl, {
      key: requestGovernorKey,
      priority: "interactive",
      signal: controller.signal,
      retryTransient: true,
    }).then((payload) => {
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