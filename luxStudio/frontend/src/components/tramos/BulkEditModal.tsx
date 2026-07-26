import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useI18n } from '../../i18n';
import type { AuthFetch } from '../../auth/AuthContext';

interface DimensionOption { id: number; name: string; }
interface ValidCombo { gama: string; difusor: string; lente: string; led_type: string | null; }
interface DimensionsData {
  gamas: DimensionOption[];
  difusores: DimensionOption[];
  lentes: DimensionOption[];
  led_types: DimensionOption[];
  valid_combinations: ValidCombo[];
}

interface BulkEditModalProps {
  open: boolean;
  selectedIds: Set<number>;
  projectId: number;
  authFetch: AuthFetch;
  onClose: () => void;
  onUpdated: () => void;
}

const NO_CHANGE = '';

const BulkEditModal: React.FC<BulkEditModalProps> = ({ open, selectedIds, projectId, authFetch, onClose, onUpdated }) => {
  const { t } = useI18n();
  const [dims, setDims] = useState<DimensionsData | null>(null);
  const [loadingDims, setLoadingDims] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);

  const [gama, setGama] = useState(NO_CHANGE);
  const [difusor, setDifusor] = useState(NO_CHANGE);
  const [lente, setLente] = useState(NO_CHANGE);
  const [ledType, setLedType] = useState(NO_CHANGE);

  useEffect(() => {
    if (!open) return;
    setLoadingDims(true);
    setError(null);
    setGama(NO_CHANGE);
    setDifusor(NO_CHANGE);
    setLente(NO_CHANGE);
    setLedType(NO_CHANGE);
    fetch('/api/ldt/dimensions')
      .then(r => r.json())
      .then(setDims)
      .catch(() => setError('Error loading catalog'))
      .finally(() => setLoadingDims(false));
  }, [open]);

  const validCombos = useMemo(() => dims?.valid_combinations || [], [dims]);

  const matchesSelection = useCallback(
    (vc: ValidCombo, except: 'gama' | 'difusor' | 'lente' | 'led_type') => (
      (except === 'gama' || gama === NO_CHANGE || vc.gama === gama) &&
      (except === 'difusor' || difusor === NO_CHANGE || vc.difusor === difusor) &&
      (except === 'lente' || lente === NO_CHANGE || vc.lente === lente) &&
      (except === 'led_type' || ledType === NO_CHANGE || vc.led_type === ledType)
    ),
    [gama, difusor, lente, ledType],
  );

  const gamas = useMemo(() => {
    if (!dims?.gamas) return [];
    if (difusor === NO_CHANGE && lente === NO_CHANGE && ledType === NO_CHANGE) return dims.gamas.map(g => g.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'gama')).map(vc => vc.gama));
    return dims.gamas.filter(g => valid.has(g.name)).map(g => g.name);
  }, [dims, validCombos, difusor, lente, ledType, matchesSelection]);

  const difusores = useMemo(() => {
    if (!dims?.difusores) return [];
    if (gama === NO_CHANGE && lente === NO_CHANGE && ledType === NO_CHANGE) return dims.difusores.map(d => d.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'difusor')).map(vc => vc.difusor));
    return dims.difusores.filter(d => valid.has(d.name)).map(d => d.name);
  }, [dims, validCombos, gama, lente, ledType, matchesSelection]);

  const lentes = useMemo(() => {
    if (!dims?.lentes) return [];
    if (gama === NO_CHANGE && difusor === NO_CHANGE && ledType === NO_CHANGE) return dims.lentes.map(l => l.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'lente')).map(vc => vc.lente));
    return dims.lentes.filter(l => valid.has(l.name)).map(l => l.name);
  }, [dims, validCombos, gama, difusor, ledType, matchesSelection]);

  const ledTypes = useMemo(() => {
    if (!dims?.led_types) return [];
    if (gama === NO_CHANGE && difusor === NO_CHANGE && lente === NO_CHANGE) return dims.led_types.map(lt => lt.name);
    const valid = new Set(validCombos.filter(vc => matchesSelection(vc, 'led_type')).map(vc => vc.led_type));
    return dims.led_types.filter(lt => valid.has(lt.name)).map(lt => lt.name);
  }, [dims, validCombos, gama, difusor, lente, matchesSelection]);

  const hasChanges = gama !== NO_CHANGE || difusor !== NO_CHANGE || lente !== NO_CHANGE || ledType !== NO_CHANGE;

  const handleApply = async () => {
    if (!hasChanges || applying) return;
    setApplying(true);
    setError(null);
    const config_fields: Record<string, unknown> = {};
    if (gama !== NO_CHANGE) config_fields.gama = gama;
    if (difusor !== NO_CHANGE) config_fields.difusor = difusor;
    if (lente !== NO_CHANGE) config_fields.lente = lente;
    if (ledType !== NO_CHANGE) config_fields.led_type = ledType;

    try {
      const res = await authFetch(`/api/projects/${projectId}/tramos/bulk-update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: Array.from(selectedIds), config_fields }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || t('tramos.bulkEdit.error'));
      }
      onUpdated();
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setApplying(false);
    }
  };

  if (!open) return null;

  const selectClass = 'w-full rounded-lg border border-[#D4CEC6] px-3 py-2 text-sm focus:border-[#1E1E1E] focus:ring-1 focus:ring-[#1E1E1E]/15';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20" onClick={onClose}>
      <div className="mx-4 w-full max-w-lg rounded-xl bg-[#FFFFFF] shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="border-b border-[#E8E2D8] px-5 py-4">
          <h2 className="text-lg font-semibold text-[#1E1E1E]">
            {t('tramos.bulkEdit.title', { count: selectedIds.size })}
          </h2>
        </div>

        <div className="space-y-4 px-5 py-4">
          {loadingDims ? (
            <p className="text-sm text-[#A09A91]">{t('actions.loading')}</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-[#6A6A6A]">{t('luminaire.lensOptic')}</label>
                  <select className={selectClass} value={gama} onChange={e => setGama(e.target.value)}>
                    <option value="">— {t('tramos.bulkEdit.noChange')} —</option>
                    {gamas.map(item => <option key={item} value={item}>{item}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-[#6A6A6A]">Difusor</label>
                  <select className={selectClass} value={difusor} onChange={e => setDifusor(e.target.value)}>
                    <option value="">— {t('tramos.bulkEdit.noChange')} —</option>
                    {difusores.map(item => <option key={item} value={item}>{item}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-[#6A6A6A]">Lente</label>
                  <select className={selectClass} value={lente} onChange={e => setLente(e.target.value)}>
                    <option value="">— {t('tramos.bulkEdit.noChange')} —</option>
                    {lentes.map(item => <option key={item} value={item}>{item}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-[#6A6A6A]">LED type</label>
                  <select className={selectClass} value={ledType} onChange={e => setLedType(e.target.value)}>
                    <option value="">— {t('tramos.bulkEdit.noChange')} —</option>
                    {ledTypes.map(item => <option key={item} value={item}>{item}</option>)}
                  </select>
                </div>
              </div>
            </>
          )}
          {error && (
            <p className="text-sm text-[#B42318]">{error}</p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={applying}
            className="rounded-lg border border-[#D4CEC6] px-4 py-2 text-sm font-medium text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:opacity-50"
          >
            {t('unsavedChanges.cancel')}
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!hasChanges || applying || loadingDims}
            className="rounded-lg bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#333333] disabled:opacity-50"
          >
            {applying ? t('actions.loading') : t('tramos.bulkEdit.apply', { count: selectedIds.size })}
          </button>
        </div>
      </div>
    </div>
  );
};

export default BulkEditModal;
