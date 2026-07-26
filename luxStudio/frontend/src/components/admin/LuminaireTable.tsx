import React, { useEffect, useState, useMemo } from 'react';
import { useAuth } from '../../auth/AuthContext';
import type { LDTInfo } from '../../types';
import { useI18n } from '../../i18n';
import { useColumnFilters, type ColumnFilterDef } from '../../hooks/useColumnFilters';

interface Props {
  onEdit: (lum: LDTInfo) => void;
  refreshKey: number;
}

const LuminaireTable: React.FC<Props> = ({ onEdit, refreshKey }) => {
  const { t } = useI18n();
  const { authFetch } = useAuth();
  const [luminaires, setLuminaires] = useState<LDTInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    authFetch('/api/admin/luminaires')
      .then(async res => {
        if (!res.ok) return [];
        return res.json();
      })
      .then(data => setLuminaires(Array.isArray(data) ? data : []))
      .catch(() => setLuminaires([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [refreshKey]);

  const handleDelete = async (id: string) => {
    if (!confirm(t('admin.deleteConfirm'))) return;
    await authFetch(`/api/admin/luminaires/${id}`, { method: 'DELETE' });
    load();
  };

  const filterDefs: ColumnFilterDef<LDTInfo>[] = useMemo(() => [
    { key: 'id', getValue: lum => String(lum.id) },
    { key: 'gama', getValue: lum => lum.gama || lum.model_family || '' },
    { key: 'difusor', getValue: lum => lum.difusor || '-' },
    { key: 'lente', getValue: lum => lum.lente || lum.optic_family || '' },
    { key: 'led_type', getValue: lum => lum.led_type || '-' },
    { key: 'cct', getValue: lum => String(lum.cct) },
    { key: 'cri', getValue: lum => String(lum.cri ?? 70) },
    { key: 'power', getValue: lum => String(lum.power.toFixed(1)) },
    { key: 'flux', getValue: lum => String(lum.flux) },
    { key: 'fotometria', getValue: lum => lum.fotometria || lum.filename || '-' },
  ], []);

  const { filters, setFilter, filteredData } = useColumnFilters(luminaires, filterDefs);

  if (loading) {
    return <div className="text-center py-8 text-[#6a6a6a]">{t('admin.loadingLuminaires')}</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#E8E2D8] text-left text-[#A09A91] text-xs uppercase tracking-wider">
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">Gama</th>
            <th className="px-3 py-2">Difusor</th>
            <th className="px-3 py-2">Lente</th>
            <th className="px-3 py-2">LED Type</th>
            <th className="px-3 py-2">CCT</th>
            <th className="px-3 py-2">CRI</th>
            <th className="px-3 py-2">{t('luminaire.power')}</th>
            <th className="px-3 py-2">{t('results.flux')}</th>
            <th className="px-3 py-2">Fotometría</th>
            <th className="px-3 py-2 text-right">{t('admin.actions')}</th>
          </tr>
          <tr className="border-b border-[#E8E2D8]">
            <th className="px-1 py-1"><input value={filters.id || ''} onChange={e => setFilter('id', e.target.value)} placeholder="ID" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.gama || ''} onChange={e => setFilter('gama', e.target.value)} placeholder="Gama" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.difusor || ''} onChange={e => setFilter('difusor', e.target.value)} placeholder="Difusor" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.lente || ''} onChange={e => setFilter('lente', e.target.value)} placeholder="Lente" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.led_type || ''} onChange={e => setFilter('led_type', e.target.value)} placeholder="LED" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.cct || ''} onChange={e => setFilter('cct', e.target.value)} placeholder="CCT" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.cri || ''} onChange={e => setFilter('cri', e.target.value)} placeholder="CRI" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.power || ''} onChange={e => setFilter('power', e.target.value)} placeholder="W" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.flux || ''} onChange={e => setFilter('flux', e.target.value)} placeholder="lm" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1"><input value={filters.fotometria || ''} onChange={e => setFilter('fotometria', e.target.value)} placeholder="Fotometría" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
            <th className="px-1 py-1" />
          </tr>
        </thead>
        <tbody>
          {filteredData.map(lum => (
            <tr key={lum.id} className="border-b border-[#E8E2D8] hover:bg-[#F7F4EF]">
              <td className="px-3 py-2 text-[#6a6a6a]">{lum.id}</td>
              <td className="px-3 py-2 font-medium text-[#6A6A6A]">{lum.gama || lum.model_family}</td>
              <td className="px-3 py-2">{lum.difusor || '-'}</td>
              <td className="px-3 py-2">
                <span className="inline-block px-2 py-0.5 rounded-md bg-[#1E1E1E]/6 text-[#333333] text-xs font-medium">
                  {lum.lente || lum.optic_family}
                </span>
              </td>
              <td className="px-3 py-2">{lum.led_type || '-'}</td>
              <td className="px-3 py-2">{lum.cct}K</td>
              <td className="px-3 py-2">{lum.cri ?? 70}</td>
              <td className="px-3 py-2">{lum.power.toFixed(1)}W</td>
              <td className="px-3 py-2">{(lum.flux / 1000).toFixed(1)}k lm</td>
              <td className="px-3 py-2 text-xs text-[#A09A91] max-w-[260px] truncate" title={lum.filename}>
                {lum.fotometria || lum.filename || '-'}
              </td>
              <td className="px-3 py-2 text-right space-x-1">
                <button
                  onClick={() => onEdit(lum)}
                  className="px-2 py-1 text-xs rounded border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#FFFFFF]"
                >
                  {t('actions.edit')}
                </button>
                <button
                  onClick={() => handleDelete(lum.id)}
                  className="px-2 py-1 text-xs rounded border border-red-200 text-red-600 hover:bg-red-50"
                >
                  {t('actions.delete')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filteredData.length === 0 && (
        <p className="text-center py-8 text-[#6a6a6a]">{t('admin.noLuminaires')}</p>
      )}
    </div>
  );
};

export default LuminaireTable;
