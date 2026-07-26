import { useState, useMemo, useCallback } from 'react';

export interface ColumnFilterDef<T> {
  key: string;
  getValue: (item: T) => string;
  exact?: boolean;
}

export function useColumnFilters<T>(data: T[], defs: ColumnFilterDef<T>[]) {
  const [filters, setFilters] = useState<Record<string, string>>({});

  const setFilter = useCallback((key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  }, []);

  const clearAll = useCallback(() => setFilters({}), []);

  const filteredData = useMemo(() => {
    const active = Object.entries(filters).filter(([, v]) => v.trim());
    if (active.length === 0) return data;
    return data.filter(item =>
      active.every(([key, val]) => {
        const def = defs.find(d => d.key === key);
        if (!def) return true;
        const cell = def.getValue(item).toLowerCase();
        const needle = val.toLowerCase();
        return def.exact ? cell === needle : cell.includes(needle);
      })
    );
  }, [data, filters, defs]);

  const activeCount = Object.values(filters).filter(v => v.trim()).length;

  return { filters, setFilter, clearAll, filteredData, activeCount };
}
