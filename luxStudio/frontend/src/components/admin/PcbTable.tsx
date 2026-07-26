import React, { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';

interface Props {
  refreshKey: number;
}

const PcbTable: React.FC<Props> = ({ refreshKey }) => {
  const { authFetch } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    pcb_ref: '',
    pcb_descripcion: '',
    pcb_no_drivers: '',
    pcb_v_nominal: '',
    pcb_no_led: '',
    pcb_no_circuitos: '',
    pcb_imax_led: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    authFetch('/api/admin/pcbs')
      .then(async res => (res.ok ? res.json() : []))
      .then(data => setItems(Array.isArray(data) ? data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [refreshKey]);

  const columns = [
    { key: 'id', label: 'ID' },
    { key: 'pcb_ref', label: 'Ref' },
    { key: 'pcb_descripcion', label: 'Descripción' },
    { key: 'pcb_no_drivers', label: 'Nº Drivers' },
    { key: 'pcb_v_nominal', label: 'V Nominal' },
    { key: 'pcb_no_led', label: 'Nº LEDs' },
    { key: 'pcb_no_circuitos', label: 'Circuitos' },
    { key: 'pcb_imax_led', label: 'Imax LED' },
  ];

  const filterDefs: ColumnFilterDef<any>[] = columns.map(col => ({
    key: col.key,
    getValue: item => String(item[col.key] ?? ''),
  }));

  const { filters, setFilter, filteredData, activeCount } = useColumnFilters(items, filterDefs);

  const resetForm = () => {
    setForm({ pcb_ref: '', pcb_descripcion: '', pcb_no_drivers: '', pcb_v_nominal: '', pcb_no_led: '', pcb_no_circuitos: '', pcb_imax_led: '' });
    setError('');
  };

  const handleSubmit = async () => {
    if (!form.pcb_ref.trim()) {
      setError('pcb_ref es obligatorio');
      return;
    }
    setSaving(true);
    setError('');
    const body: Record<string, any> = { pcb_ref: form.pcb_ref.trim() };
    if (form.pcb_descripcion) body.pcb_descripcion = form.pcb_descripcion.trim();
    if (form.pcb_no_drivers) body.pcb_no_drivers = Number(form.pcb_no_drivers);
    if (form.pcb_v_nominal) body.pcb_v_nominal = Number(form.pcb_v_nominal);
    if (form.pcb_no_led) body.pcb_no_led = Number(form.pcb_no_led);
    if (form.pcb_no_circuitos) body.pcb_no_circuitos = Number(form.pcb_no_circuitos);
    if (form.pcb_imax_led) body.pcb_imax_led = Number(form.pcb_imax_led);
    const res = await authFetch('/api/admin/pcbs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    setSaving(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Error' }));
      setError(err.detail || 'Error');
      return;
    }
    resetForm();
    setShowForm(false);
    load();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSubmit();
    if (e.key === 'Escape') { setShowForm(false); resetForm(); }
  };

  if (loading) {
    return <div className="text-center py-8 text-[#6a6a6a]">Cargando...</div>;
  }

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-[#FCF9F5] border-b border-[#E8E2D8]">
        <div>
          <h3 className="font-semibold text-[#6A6A6A]">PCBs</h3>
          <p className="mt-0.5 text-xs text-[#6a6a6a]">{filteredData.length}{activeCount > 0 ? ` / ${items.length}` : ''} registros</p>
        </div>
        {!showForm && (
          <button
            onClick={() => { setShowForm(true); resetForm(); }}
            className="px-3 py-1 text-xs font-medium rounded-md bg-[#1E1E1E] text-white hover:bg-[#333333]"
          >
            + Nuevo PCB
          </button>
        )}
      </div>

      {showForm && (
        <div className="px-4 py-3 border-b border-[#E8E2D8] bg-[#FCF9F5]">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
            <input
              autoFocus
              value={form.pcb_ref}
              onChange={e => setForm(f => ({ ...f, pcb_ref: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="Ref *"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
            <input
              value={form.pcb_descripcion}
              onChange={e => setForm(f => ({ ...f, pcb_descripcion: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="Descripción"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
            <input
              type="number"
              value={form.pcb_no_drivers}
              onChange={e => setForm(f => ({ ...f, pcb_no_drivers: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="Nº Drivers"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
            <input
              type="number"
              step="any"
              value={form.pcb_v_nominal}
              onChange={e => setForm(f => ({ ...f, pcb_v_nominal: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="V Nominal"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
            <input
              type="number"
              value={form.pcb_no_led}
              onChange={e => setForm(f => ({ ...f, pcb_no_led: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="Nº LEDs"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
            <input
              type="number"
              value={form.pcb_no_circuitos}
              onChange={e => setForm(f => ({ ...f, pcb_no_circuitos: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="Circuitos"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
            <input
              type="number"
              step="any"
              value={form.pcb_imax_led}
              onChange={e => setForm(f => ({ ...f, pcb_imax_led: e.target.value }))}
              onKeyDown={handleKeyDown}
              placeholder="Imax LED"
              className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
            />
          </div>
          {error && <p className="text-red-600 text-xs mb-2">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-[#1E1E1E] text-white hover:bg-[#333333] disabled:opacity-50"
            >
              {saving ? 'Guardando...' : 'Crear'}
            </button>
            <button
              onClick={() => { setShowForm(false); resetForm(); }}
              className="px-3 py-1.5 text-xs rounded-md border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#FFFFFF]"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

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
                      {item[col.key] ?? '—'}
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

export default PcbTable;
