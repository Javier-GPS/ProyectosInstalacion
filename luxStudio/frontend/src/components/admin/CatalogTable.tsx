import React, { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';

interface Column {
  key: string;
  label: string;
  render?: (value: any, row: any) => React.ReactNode;
}

interface Props {
  endpoint: string;
  label: string;
  columns: Column[];
  refreshKey: number;
}

const CatalogTable: React.FC<Props> = ({ endpoint, label, columns, refreshKey }) => {
  const { authFetch } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    authFetch(`/api/admin/${endpoint}`)
      .then(async res => {
        if (!res.ok) return [];
        return res.json();
      })
      .then(data => setItems(Array.isArray(data) ? data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [endpoint, refreshKey]);

  const filterDefs: ColumnFilterDef<any>[] = columns.map(col => ({
    key: col.key,
    getValue: item => String(item[col.key] ?? ''),
  }));

  const { filters, setFilter, filteredData, activeCount } = useColumnFilters(items, filterDefs);

  if (loading) {
    return <div className="text-center py-8 text-[#6a6a6a]">Cargando...</div>;
  }

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-[#FCF9F5] border-b border-[#E8E2D8]">
        <div>
          <h3 className="font-semibold text-[#6A6A6A]">{label}</h3>
          <p className="mt-0.5 text-xs text-[#6a6a6a]">{filteredData.length}{activeCount > 0 ? ` / ${items.length}` : ''} registros</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        {items.length === 0 ? (
          <div className="text-center py-8 text-[#6a6a6a]">Sin elementos</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#E8E2D8] text-left text-[#A09A91] text-xs uppercase tracking-wider">
                {columns.map(col => (
                  <th key={col.key} className="px-3 py-2 whitespace-nowrap">{col.label}</th>
                ))}
              </tr>
              <tr className="border-b border-[#E8E2D8]">
                {columns.map(col => (
                  <th key={`f-${col.key}`} className="px-1 py-1">
                    <input
                      value={filters[col.key] || ''}
                      onChange={e => setFilter(col.key, e.target.value)}
                      placeholder={col.label}
                      className="w-full min-w-0 px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-[#1E1E1E]/10"
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredData.map((item, index) => (
                <tr key={item.id ?? index} className="border-b border-[#E8E2D8] hover:bg-[#F7F4EF]">
                  {columns.map(col => (
                    <td key={col.key} className="px-3 py-2 text-[#6A6A6A] whitespace-nowrap">
                      {col.render ? col.render(item[col.key], item) : (item[col.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default CatalogTable;
