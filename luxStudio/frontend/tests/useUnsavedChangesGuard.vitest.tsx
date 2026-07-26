import { describe, it, expect } from 'vitest';
import { render, act } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { useUnsavedChangesGuard } from '../src/hooks/useUnsavedChangesGuard';

const createWrapper = () => {
  let dirty = false;
  let stale = false;
  const hookRef: { current: ReturnType<typeof useUnsavedChangesGuard> | null } = { current: null };

  const TestComp = () => {
    hookRef.current = useUnsavedChangesGuard({ isDirty: () => dirty, isStale: () => stale });
    return null;
  };

  const router = createMemoryRouter([{ path: '/', element: <TestComp /> }], { initialEntries: ['/'] });

  return { router, setDirty: (v: boolean) => { dirty = v; }, setStale: (v: boolean) => { stale = v; }, hookRef };
};

describe('useUnsavedChangesGuard', () => {
  it('confirmNavigation resolves immediately when not dirty', async () => {
    const { router, hookRef } = createWrapper();
    render(<RouterProvider router={router} />);
    expect(await hookRef.current!.confirmNavigation()).toBe(true);
  });

  it('confirmNavigation blocks and resolves via resolveNavigation when dirty', async () => {
    const { router, setDirty, hookRef } = createWrapper();
    setDirty(true);
    render(<RouterProvider router={router} />);
    const promise = hookRef.current!.confirmNavigation();
    act(() => hookRef.current!.state.resolveNavigation(true));
    expect(await promise).toBe(true);
  });

  it('confirmNavigation can cancel when dirty via resolveNavigation(false)', async () => {
    const { router, setDirty, hookRef } = createWrapper();
    setDirty(true);
    render(<RouterProvider router={router} />);
    const promise = hookRef.current!.confirmNavigation();
    act(() => hookRef.current!.state.resolveNavigation(false));
    expect(await promise).toBe(false);
  });

  it('confirmSaveWithoutRecalc resolves immediately when not dirty', async () => {
    const { router, hookRef } = createWrapper();
    render(<RouterProvider router={router} />);
    expect(await hookRef.current!.confirmSaveWithoutRecalc()).toBe(true);
  });

  it('confirmSaveWithoutRecalc resolves immediately when not stale (even if dirty)', async () => {
    const { router, setDirty, hookRef } = createWrapper();
    setDirty(true);
    render(<RouterProvider router={router} />);
    expect(await hookRef.current!.confirmSaveWithoutRecalc()).toBe(true);
  });

  it('confirmSaveWithoutRecalc blocks and resolves when dirty and stale', async () => {
    const { router, setDirty, setStale, hookRef } = createWrapper();
    setDirty(true);
    setStale(true);
    render(<RouterProvider router={router} />);
    const promise = hookRef.current!.confirmSaveWithoutRecalc();
    act(() => hookRef.current!.state.resolveRecalcPrompt(true));
    expect(await promise).toBe(true);
  });
});
