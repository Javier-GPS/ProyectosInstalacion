import { useCallback, useEffect, useRef, useState } from 'react';

interface PendingRequest {
  promise: Promise<unknown>;
  timestamp: number;
}

interface UseApiOptions {
  dedupTTL?: number; // ms to reuse in-flight promise, default 300
}

type ApiFn<T> = (signal?: AbortSignal) => Promise<T>;

export interface UseApiResult<T> {
  call: (fn: ApiFn<T>) => Promise<T>;
  cancel: () => void;
  isPending: boolean;
  error: string | null;
}

const inFlight = new Map<string, PendingRequest>();

/** Hook that wraps API calls with AbortController, dedup, and stale detection. */
export function useApi<T>(options: UseApiOptions = {}): UseApiResult<T> {
  const { dedupTTL = 300 } = options;
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => () => { mountedRef.current = false; }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsPending(false);
  }, []);

  const dedupKey = useCallback((fn: ApiFn<T>): string => {
    // Extract method + URL from the arrow function body for dedup
    const src = fn.toString();
    // Try to extract URL from patterns like: api<any>('/api/zones', ...) or api(`/api/zones/${id}`, ...)
    const urlMatch = src.match(/['`](\/[^'`]+)['`]/);
    const methodMatch = src.match(/method:\s*'(GET|POST|PUT|DELETE)'/i);
    const method = methodMatch?.[1] ?? 'GET';
    // Use a stable URL key — remove dynamic segments like ${id} in favor of a placeholder
    const url = urlMatch?.[1]?.replace(/\$\{[^}]+\}/g, ':param') ?? src.slice(0, 80);
    return `${method}::${url}`;
  }, []);

  const call = useCallback(async (fn: ApiFn<T>): Promise<T> => {
    setError(null);
    setIsPending(true);
    seqRef.current += 1;
    const currentSeq = seqRef.current;
    const key = dedupKey(fn);

    // Check in-flight dedup (GET only)
    const existing = inFlight.get(key);
    if (existing && Date.now() - existing.timestamp < dedupTTL) {
      try {
        const result = await existing.promise;
        if (mountedRef.current && currentSeq === seqRef.current) {
          setIsPending(false);
        }
        return result as T;
      } catch {
        // dedup failed, fall through to re-execute
        inFlight.delete(key);
      }
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const promise = fn(controller.signal)
      .finally(() => { inFlight.delete(key); }) as Promise<unknown>;

    inFlight.set(key, { promise, timestamp: Date.now() });

    try {
      const result = await promise;
      if (mountedRef.current && currentSeq === seqRef.current) {
        setIsPending(false);
      }
      return result as T;
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') {
        // Silently ignore cancelled requests
        throw err;
      }
      const msg = (err as Error)?.message || 'Request failed';
      if (mountedRef.current && currentSeq === seqRef.current) {
        setError(msg);
        setIsPending(false);
      }
      throw err;
    }
  }, [dedupKey, dedupTTL]);

  return { call, cancel, isPending, error };
}
