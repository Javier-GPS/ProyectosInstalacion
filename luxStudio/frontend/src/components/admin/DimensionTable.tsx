import React, { useEffect, useState, useMemo } from 'react';
import { useAuth } from '../../auth/AuthContext';
import type { DimensionItem } from '../../types';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';

type DimensionRow = DimensionItem & {
  gama?: string;
  difusor?: string;
  lente?: string;
  led_type?: string;
  ledType?: string;
  value?: string;
  label?: string;
  code?: string;
};

interface Props {
  endpoint: string;
  label: string;
  refreshKey: number;
  onRefresh: () => void;
}

const DimensionTable: React.FC<Props> = ({ endpoint, label, refreshKey, onRefresh }) => {
  const { authFetch } = useAuth();
  const [items, setItems] = useState<DimensionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState<DimensionItem | null>(null);
  const [newName, setNewName] = useState('');

  const load = () => {
    setLoading(true);
    authFetch(`/api/admin/${endpoint}`)
      .then(async res => {
        if (!res.ok) return [];
        return res.json();
      })
      .then(data => setItems(Array.isArray(data) ? data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [endpoint, refreshKey]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    await authFetch(`/api/admin/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim() }),
    });
    setNewName('');
    setShowForm(false);
    load();
    onRefresh();
  };

  const handleUpdate = async () => {
    if (!editItem || !newName.trim()) return;
    await authFetch(`/api/admin/${endpoint}/${editItem.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim() }),
    });
    setNewName('');
    setEditItem(null);
    load();
    onRefresh();
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Eliminar "${name}"?`)) return;
    const res = await authFetch(`/api/admin/${endpoint}/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Error' }));
      alert(err.detail || 'Error');
    } else {
      load();
      onRefresh();
    }
  };

  const getName = (item: DimensionRow | string) => {
    if (typeof item === 'string') return item;
    const direct = item.name || item.gama || item.difusor || item.lente || item.led_type || item.ledType || item.value || item.label || item.code;
    if (direct) return direct;
    return Object.entries(item)
      .find(([key, value]) => key !== 'id' && typeof value === 'string' && value.trim())?.[1] as string || '';
  };

  const getId = (item: DimensionRow | string, index: number) => (
    typeof item === 'string' ? index + 1 : item.id
  );

  const startEdit = (item: DimensionRow) => {
    setEditItem(item);
    setNewName(getName(item));
    setShowForm(false);
  };

  const cancelForm = () => {
    setShowForm(false);
    setEditItem(null);
    setNewName('');
  };

  const filterDefs: ColumnFilterDef<DimensionRow>[] = useMemo(() => [
    { key: 'id', getValue: item => String(getId(item, items.indexOf(item))) },
    { key: 'name', getValue: item => getName(item) },
  ], [items]);

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
        {!showForm && !editItem && (
          <button
            onClick={() => { setShowForm(true); setNewName(''); }}
            className="px-3 py-1 text-xs font-medium rounded-md bg-[#1E1E1E] text-white hover:bg-[#333333]"
          >
            + Nuevo
          </button>
        )}
      </div>

      {(showForm || editItem) && (
        <div className="px-4 py-3 border-b border-[#E8E2D8] bg-[#FCF9F5] flex items-center gap-2">
          <input
            autoFocus
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') editItem ? handleUpdate() : handleCreate(); if (e.key === 'Escape') cancelForm(); }}
            className="flex-1 px-3 py-1.5 text-sm border border-[#D4CEC6] rounded-md focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            placeholder={`Nombre del ${label.toLowerCase()}`}
          />
          <button
            onClick={editItem ? handleUpdate : handleCreate}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-[#1E1E1E] text-white hover:bg-[#333333]"
          >
            {editItem ? 'Guardar' : 'Crear'}
          </button>
          <button onClick={cancelForm} className="px-3 py-1.5 text-xs rounded-md border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#FFFFFF]">
            Cancelar
          </button>
        </div>
      )}

      <div className="overflow-x-auto">
        {items.length === 0 ? (
          <div className="text-center py-8 text-[#6a6a6a]">Sin elementos</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#E8E2D8] text-left text-[#A09A91] text-xs uppercase tracking-wider">
                <th className="px-3 py-2 w-20">ID</th>
                <th className="px-3 py-2">Nombre</th>
                <th className="px-3 py-2 w-40 text-right">Acciones</th>
              </tr>
              <tr className="border-b border-[#E8E2D8]">
                <th className="px-1 py-1 w-20">
                  <input
                    value={filters.id || ''}
                    onChange={e => setFilter('id', e.target.value)}
                    placeholder="ID"
                    className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-[#1E1E1E]/10"
                  />
                </th>
                <th className="px-1 py-1">
                  <input
                    value={filters.name || ''}
                    onChange={e => setFilter('name', e.target.value)}
                    placeholder="Nombre"
                    className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-[#1E1E1E]/10"
                  />
                </th>
                <th className="px-1 py-1 w-40" />
              </tr>
            </thead>
            <tbody>
              {filteredData.map((item, index) => {
                const name = getName(item);
                const id = getId(item, index);
                return (
                <tr key={`${id}-${name}`} className="border-b border-[#E8E2D8] hover:bg-[#F7F4EF]">
                  <td className="px-3 py-2 text-[#6a6a6a]">{id}</td>
                  <td className="px-3 py-2 font-medium text-[#6A6A6A] whitespace-normal break-words" title={name}>
                    {name || <span className="text-red-500">Sin nombre</span>}
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <button
                      onClick={() => startEdit(item)}
                      className="px-2 py-1 text-xs rounded border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#FFFFFF]"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => handleDelete(id, name)}
                      className="px-2 py-1 text-xs rounded border border-red-200 text-red-600 hover:bg-red-50"
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              )})}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default DimensionTable;
