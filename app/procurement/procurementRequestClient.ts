export type ProcurementRequestPriority = "interactive" | "background" | "idle";

type RequestOptions = {
  signal?: AbortSignal;
  priority?: ProcurementRequestPriority;
  key?: string;
  retryTransient?: boolean;
  credentials?: RequestCredentials;
  cache?: RequestCache;
  headers?: HeadersInit;
};

type CircuitState = {
  failures: number;
  openedUntil: number;
};

type QueueItem<T> = {
  priority: number;
  run: () => Promise<T>;
  resolve: (value: T | PromiseLike<T>) => void;
  reject: (reason?: unknown) => void;
};

const PRIORITY: Record<ProcurementRequestPriority, number> = {
  interactive: 0,
  background: 1,
  idle: 2,
};

const TRANSIENT_STATUSES = new Set([502, 503, 504]);
const CIRCUIT_FAILURE_THRESHOLD = 3;
const CIRCUIT_OPEN_MS = 30_000;
const RETRY_DELAY_MS = 750;
const DEFAULT_CONCURRENCY = 3;

function abortError() {
  return new DOMException("Request aborted", "AbortError");
}

function wait(milliseconds: number, signal?: AbortSignal) {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise<void>((resolve, reject) => {
    const timer = globalThis.setTimeout(resolve, milliseconds);
    if (!signal) return;
    signal.addEventListener("abort", () => {
      globalThis.clearTimeout(timer);
      reject(abortError());
    }, { once: true });
  });
}

function circuitKey(url: string) {
  try {
    const parsed = new URL(url, globalThis.location?.origin || "http://localhost");
    return parsed.pathname;
  } catch {
    return url;
  }
}

export class ProcurementRequestClient {
  private active = 0;
  private readonly concurrency: number;
  private readonly queue: QueueItem<unknown>[] = [];
  private readonly inflight = new Map<string, Promise<unknown>>();
  private readonly circuits = new Map<string, CircuitState>();
  private readonly fetchImpl: typeof fetch;
  private readonly now: () => number;

  constructor(options: { concurrency?: number; fetchImpl?: typeof fetch; now?: () => number } = {}) {
    this.concurrency = Math.max(1, options.concurrency ?? DEFAULT_CONCURRENCY);
    this.fetchImpl = options.fetchImpl || fetch;
    this.now = options.now || Date.now;
  }

  getJson<T>(url: string, options: RequestOptions = {}): Promise<T> {
    const key = options.key || `GET:${url}`;
    const existing = this.inflight.get(key) as Promise<T> | undefined;
    if (existing) return existing;

    const promise = this.enqueue<T>(options.priority || "interactive", async () => {
      const circuit = this.circuits.get(circuitKey(url));
      if (circuit && circuit.openedUntil > this.now()) {
        throw new Error("procurement-circuit-open");
      }

      const maxAttempts = options.retryTransient === false ? 1 : 2;
      let lastError: unknown;
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        if (options.signal?.aborted) throw abortError();
        try {
          const response = await this.fetchImpl(url, {
            method: "GET",
            credentials: options.credentials || "include",
            cache: options.cache,
            headers: { Accept: "application/json", ...(options.headers || {}) },
            signal: options.signal,
          });
          if (TRANSIENT_STATUSES.has(response.status) && attempt < maxAttempts) {
            await wait(RETRY_DELAY_MS, options.signal);
            continue;
          }
          if (!response.ok) throw new Error(`procurement-http-${response.status}`);
          const payload = await response.json() as T;
          this.recordSuccess(url);
          return payload;
        } catch (error) {
          if (error instanceof DOMException && error.name === "AbortError") throw error;
          lastError = error;
          const retryableNetworkError = error instanceof TypeError;
          if (attempt < maxAttempts && retryableNetworkError) {
            await wait(RETRY_DELAY_MS, options.signal);
            continue;
          }
          this.recordFailure(url);
          throw error;
        }
      }
      throw lastError instanceof Error ? lastError : new Error("procurement-request-failed");
    });

    this.inflight.set(key, promise as Promise<unknown>);
    void promise.finally(() => {
      if (this.inflight.get(key) === promise) this.inflight.delete(key);
    }).catch(() => undefined);
    return promise;
  }

  private recordSuccess(url: string) {
    this.circuits.delete(circuitKey(url));
  }

  private recordFailure(url: string) {
    const key = circuitKey(url);
    const current = this.circuits.get(key) || { failures: 0, openedUntil: 0 };
    const failures = current.failures + 1;
    this.circuits.set(key, {
      failures,
      openedUntil: failures >= CIRCUIT_FAILURE_THRESHOLD ? this.now() + CIRCUIT_OPEN_MS : 0,
    });
  }

  private enqueue<T>(priority: ProcurementRequestPriority, run: () => Promise<T>) {
    return new Promise<T>((resolve, reject) => {
      this.queue.push({ priority: PRIORITY[priority], run, resolve, reject } as QueueItem<unknown>);
      this.queue.sort((left, right) => left.priority - right.priority);
      this.drain();
    });
  }

  private drain() {
    while (this.active < this.concurrency && this.queue.length) {
      const item = this.queue.shift()!;
      this.active += 1;
      void item.run()
        .then(item.resolve, item.reject)
        .finally(() => {
          this.active -= 1;
          this.drain();
        });
    }
  }
}

export const procurementRequestClient = new ProcurementRequestClient();
