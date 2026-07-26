import React, { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';

interface Props {
  refreshKey: number;
}

const FIELDS = [
  { key: 'gama', label: 'Gama *', type: 'text' },
  { key: 'difusor', label: 'Difusor *', type: 'text' },
  { key: 'lente', label: 'Lente *', type: 'text' },
  { key: 'led_ref', label: 'LED Ref *', type: 'text' },
  { key: 'led_type', label: 'LED Type', type: 'text' },
  { key: 'pcb_ref', label: 'PCB Ref', type: 'text' },
  { key: 'n_pcbs', label: 'Nº PCBs', type: 'number' },
  { key: 'n_leds_per_pcb', label: 'LEDs/PCB', type: 'number' },
] as const;

const emptyForm = Object.fromEntries(FIELDS.map(f => [f.key, '']));

const COLUMNS = [
  { key: 'id', label: 'ID' },
  { key: 'gama', label: 'Gama' },
  { key: 'difusor', label: 'Difusor' },
  { key: 'lente', label: 'Lente' },
  { key: 'led_type', label: 'LED Type' },
  { key: 'led_ref', label: 'LED Ref' },
  { key: 'led_tipo', label: 'LED Tipo' },
  { key: 'pcb_ref', label: 'PCB' },
  { key: 'n_pcbs', label: 'Nº PCBs' },
  { key: 'n_leds_per_pcb', label: 'LEDs/PCB' },
  {
    key: 'pmax_ajustada',
    label: 'Pmax Ajustada',
    render: (v: any, _item?: any) => v != null ? <span className="font-semibold text-[#333333]">{v}</span> : '—',
  },
];

const LuminaireLedTable: React.FC<Props> = ({ refreshKey }) => {
  const { authFetch } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({ ...emptyForm });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    authFetch('/api/admin/luminaire-leds')
      .then(async res => (res.ok ? res.json() : []))
      .then(data => setItems(Array.isArray(data) ? data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [refreshKey]);

  const filterDefs: ColumnFilterDef<any>[] = COLUMNS.map(col => ({
    key: col.key,
    getValue: item => String(item[col.key] ?? ''),
  }));

  const { filters, setFilter, filteredData, activeCount } = useColumnFilters(items, filterDefs);

  const resetForm = () => {
    setForm({ ...emptyForm });
    setError('');
  };

  const handleSubmit = async () => {
    if (!form.gama.trim() || !form.difusor.trim() || !form.lente.trim() || !form.led_ref.trim()) {
      setError('Gama, Difusor, Lente y LED Ref son obligatorios');
      return;
    }
    setSaving(true);
    setError('');
    const body: Record<string, any> = {
      gama: form.gama.trim(),
      difusor: form.difusor.trim(),
      lente: form.lente.trim(),
      led_ref: form.led_ref.trim(),
    };
    if (form.led_type.trim()) body.led_type = form.led_type.trim();
    if (form.pcb_ref.trim()) body.pcb_ref = form.pcb_ref.trim();
    if (form.n_pcbs.trim()) body.n_pcbs = Number(form.n_pcbs);
    if (form.n_leds_per_pcb.trim()) body.n_leds_per_pcb = Number(form.n_leds_per_pcb);
    const res = await authFetch('/api/admin/luminaire-leds', {
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
          <h3 className="font-semibold text-[#6A6A6A]">4-tupla → LED</h3>
          <p className="mt-0.5 text-xs text-[#6a6a6a]">{filteredData.length}{activeCount > 0 ? ` / ${items.length}` : ''} registros</p>
        </div>
        {!showForm && (
          <button
            onClick={() => { setShowForm(true); resetForm(); }}
            className="px-3 py-1 text-xs font-medium rounded-md bg-[#1E1E1E] text-white hover:bg-[#333333]"
          >
            + Nueva 4-tupla
          </button>
        )}
      </div>

      {showForm && (
        <div className="px-4 py-3 border-b border-[#E8E2D8] bg-[#FCF9F5]">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
            {FIELDS.map(f => (
              <input
                key={f.key}
                autoFocus={f.key === 'gama'}
                type={f.type}
                value={form[f.key]}
                onChange={e => setForm(ff => ({ ...ff, [f.key]: e.target.value }))}
                onKeyDown={handleKeyDown}
                placeholder={f.label}
                className="px-2 py-1.5 text-sm border border-[#D4CEC6] rounded focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
              />
            ))}
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
                {COLUMNS.map(col => (
                  <th key={col.key} className="px-3 py-2 whitespace-nowrap">{col.label}</th>
                ))}
              </tr>
              <tr className="border-b border-[#E8E2D8]">
                {COLUMNS.map(col => (
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
                  {COLUMNS.map(col => (
                    <td key={col.key} className="px-3 py-2 text-[#6A6A6A] whitespace-nowrap">
                      {'render' in col && col.render ? (col.render as any)(item[col.key], item) : (item[col.key] ?? '—')}
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

export default LuminaireLedTable;

