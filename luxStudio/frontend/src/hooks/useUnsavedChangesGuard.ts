import { useCallback, useEffect, useRef, useState } from 'react';
import { useBlocker } from 'react-router-dom';

export type UnsavedGuardState = {
  /** True when the user is being asked whether to discard unsaved changes. */
  blocking: boolean;
  /** True when the user is being asked whether to proceed without recalculating. */
  requireRecalcPrompt: boolean;
  /** Resolve the underlying navigation: true = proceed, false = cancel. */
  resolveNavigation: ((proceed: boolean) => void) | null;
  /** Resolve the recalc prompt: true = save anyway, false = cancel. */
  resolveRecalcPrompt: ((saveAnyway: boolean) => void) | null;
};

export type UnsavedGuardApi = {
  state: UnsavedGuardState;
  /** Programmatically arm the guard before triggering navigation. */
  confirmNavigation: () => Promise<boolean>;
  /** Programmatically ask the user to recalc before saving. */
  confirmSaveWithoutRecalc: () => Promise<boolean>;
  /** Reset the guard so the next navigation is allowed. */
  bypass: () => void;
};

export type UnsavedGuardOptions = {
  /** Whether the page currently has unsaved changes. */
  isDirty: () => boolean;
  /** Whether the page has changes that haven't been recalculated since the last save. */
  isStale: () => boolean;
};

/**
 * Combined guard for unsaved changes.
 *
 * - Blocks in-app navigation (router) when `isDirty()` is true.
 * - Shows the browser native prompt for tab close / refresh.
 * - Exposes `confirmSaveWithoutRecalc()` so the "Save" button can ask the user
 *   to confirm when the latest config hasn't been recalculated.
 *
 * The hook returns a `state` object the page renders as a modal, and two
 * imperative helpers.
 */
export const useUnsavedChangesGuard = ({
  isDirty,
  isStale,
}: UnsavedGuardOptions): UnsavedGuardApi => {
  const [blocking, setBlocking] = useState(false);
  const [requireRecalcPrompt, setRequireRecalcPrompt] = useState(false);
  const resolveNavigationRef = useRef<((proceed: boolean) => void) | null>(null);
  const resolveRecalcRef = useRef<((saveAnyway: boolean) => void) | null>(null);
  const bypassRef = useRef(false);

  const resolveNavigation = useCallback((proceed: boolean) => {
    setBlocking(false);
    resolveNavigationRef.current?.(proceed);
    resolveNavigationRef.current = null;
  }, []);

  const resolveRecalcPrompt = useCallback((saveAnyway: boolean) => {
    setRequireRecalcPrompt(false);
    resolveRecalcRef.current?.(saveAnyway);
    resolveRecalcRef.current = null;
  }, []);

  // Programmatic navigation guard (called from any code path that wants to navigate)
  const confirmNavigation = useCallback((): Promise<boolean> => {
    if (!isDirty() || bypassRef.current) {
      bypassRef.current = false;
      return Promise.resolve(true);
    }
    setBlocking(true);
    return new Promise<boolean>(resolve => {
      resolveNavigationRef.current = proceed => {
        bypassRef.current = proceed;
        resolve(proceed);
      };
    });
  }, [isDirty]);

  const confirmSaveWithoutRecalc = useCallback((): Promise<boolean> => {
    if (!isDirty() || !isStale()) {
      return Promise.resolve(true);
    }
    setRequireRecalcPrompt(true);
    return new Promise<boolean>(resolve => {
      resolveRecalcRef.current = saveAnyway => resolve(saveAnyway);
    });
  }, [isDirty, isStale]);

  const bypass = useCallback(() => {
    bypassRef.current = true;
  }, []);

  // Router navigation blocker (in-app links / programmatic navigate())
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (bypassRef.current) {
      bypassRef.current = false;
      return false;
    }
    if (!isDirty()) return false;
    if (currentLocation.pathname === nextLocation.pathname) return false;
    return true;
  });

  useEffect(() => {
    if (blocker.state === 'blocked') {
      setBlocking(true);
      resolveNavigationRef.current = (proceed: boolean) => {
        bypassRef.current = proceed;
        if (proceed) {
          blocker.proceed();
        } else {
          blocker.reset();
        }
        setBlocking(false);
        resolveNavigationRef.current = null;
      };
    }
  }, [blocker]);

  // Browser-level unload (tab close, refresh, external nav)
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (isDirty()) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  return {
    state: {
      blocking,
      requireRecalcPrompt,
      resolveNavigation,
      resolveRecalcPrompt,
    },
    confirmNavigation,
    confirmSaveWithoutRecalc,
    bypass,
  };
};
