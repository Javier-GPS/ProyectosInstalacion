import { useEffect, useRef } from 'react';
import type { StoreApi } from 'zustand';

export interface ConstraintRule<S> {
  /** Slice key to watch for changes (e.g. 'zones'). */
  watch: (state: S) => unknown;
  /** Cleanup function that runs when watched value changes. */
  cleanup: (prev: unknown, current: unknown, state: S, set: Partial<S>) => void;
}

/**
 * Middleware hook that applies cross-slice consistency rules.
 * Example: when a zone is removed, cascade-delete its vias, luminaires, config.
 */
export function useCrossSliceConstraints<S extends Record<string, unknown>>(
  store: StoreApi<S>,
  rules: ConstraintRule<S>[],
) {
  const prevValues = useRef<Map<number, unknown>>(new Map());

  useEffect(() => {
    const unsub = store.subscribe((state, prevState) => {
      rules.forEach((rule, idx) => {
        const current = rule.watch(state);
        const prev = prevValues.current.get(idx) ?? rule.watch(prevState);
        if (current !== prev && current !== undefined) {
          // Build partial update from cleanup
          const updates: Partial<S> = {};
          rule.cleanup(prev, current, state, updates as any);
          if (Object.keys(updates).length > 0) {
            store.setState(updates);
          }
          prevValues.current.set(idx, current);
        }
      });
    });
    return unsub;
  }, [store, rules]);
}
