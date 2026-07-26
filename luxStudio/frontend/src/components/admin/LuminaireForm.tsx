import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import type { LDTInfo, DimensionItem } from '../../types';
import { useI18n } from '../../i18n';

interface FormData {
  manufacturer: string;
  model_family: string;
  optic_family: string;
  luminaire_name: string;
  power: number;
  cct: number;
  cri: number;
  flux: number;
  efficiency: number;
  LORL: number;
  isym: number;
  gama: string;
  difusor: string;
  lente: string;
  led_type: string;
  mf_origen: number;
}

const defaultForm = (): FormData => ({
  manufacturer: '',
  model_family: '',
  optic_family: '',
  luminaire_name: '',
  power: 0,
  cct: 4000,
  cri: 70,
  flux: 0,
  efficiency: 0,
  LORL: 100,
  isym: 0,
  gama: '',
  difusor: '',
  lente: '',
  led_type: '',
  mf_origen: 0.85,
});

const unique = (values: string[]) => Array.from(new Set(values)).filter(Boolean).sort();

interface Props {
  editLum: LDTInfo | null;
  onSaved: () => void;
  onCancel: () => void;
}

const LuminaireForm: React.FC<Props> = ({ editLum, onSaved, onCancel }) => {
  const { t } = useI18n();
  const { authFetch } = useAuth();
  const [form, setForm] = useState<FormData>(defaultForm());
  const [ldtFile, setLdtFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Dimension data for cascading dropdowns
  const [gamas, setGamas] = useState<DimensionItem[]>([]);
  const [difusores, setDifusores] = useState<DimensionItem[]>([]);
  const [lentes, setLentes] = useState<DimensionItem[]>([]);
  const [ledTypes, setLedTypes] = useState<DimensionItem[]>([]);

  // Load dimension data
  useEffect(() => {
    Promise.all([
      authFetch('/api/admin/gamas').then(r => r.json()),
      authFetch('/api/admin/difusores').then(r => r.json()),
      authFetch('/api/admin/lentes').then(r => r.json()),
      authFetch('/api/admin/led-types').then(r => r.json()),
    ]).then(([g, d, l, lt]) => {
      setGamas(g);
      setDifusores(d);
      setLentes(l);
      setLedTypes(lt);
    }).catch(console.error);
  }, []);

  // Cascading filter for valid combinations (client-side from loaded data)
  const filteredDifusores = useMemo(() => {
    if (!form.gama) return difusores;
    return difusores; // For now show all; real filtering needs valid_combinations
  }, [difusores, form.gama]);

  const filteredLentes = useMemo(() => {
    if (!form.gama) return lentes;
    return lentes;
  }, [lentes, form.gama]);

  const filteredLedTypes = useMemo(() => {
    return ledTypes;
  }, [ledTypes]);

  useEffect(() => {
    if (editLum) {
      setForm({
        manufacturer: editLum.manufacturer,
        model_family: editLum.model_family,
        optic_family: editLum.optic_family,
        luminaire_name: editLum.luminaire_name,
        power: editLum.power,
        cct: editLum.cct,
        cri: editLum.cri ?? 70,
        flux: editLum.flux,
        efficiency: editLum.efficiency,
        LORL: editLum.LORL,
        isym: editLum.isym,
        gama: editLum.gama || '',
        difusor: editLum.difusor || '',
        lente: editLum.lente || '',
        led_type: editLum.led_type || '',
        mf_origen: editLum.mf_origen ?? 0.85,
      });
    } else {
      setForm(defaultForm());
    }
    setLdtFile(null);
    setMessage(null);
  }, [editLum]);

  const handleField = (field: keyof FormData, value: string | number) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLdtFile(file);
    setMessage(null);
    setParsing(true);

    const fd = new FormData();
    fd.append('file', file);

    try {
      const res = await authFetch('/api/admin/parse-ldt', { method: 'POST', body: fd });
      const data = await res.json();
      if (res.ok) {
        setForm(prev => ({
          ...prev,
          manufacturer: data.manufacturer || prev.manufacturer,
          model_family: data.model_family || prev.model_family,
          optic_family: data.optic_family || prev.optic_family,
          luminaire_name: data.luminaire_name || prev.luminaire_name,
          power: data.power ?? prev.power,
          cct: data.cct ?? prev.cct,
          cri: data.cri ?? prev.cri,
          flux: data.flux ?? prev.flux,
          efficiency: data.efficiency ?? prev.efficiency,
          LORL: data.LORL ?? prev.LORL,
          isym: data.isym ?? prev.isym,
        }));
        setMessage(t('form.parsed'));
      } else {
        setMessage(t('form.parseError', { error: data.detail || t('luminaire.invalidLdt') }));
      }
    } catch (err: any) {
      setMessage(t('form.parseError', { error: err.message }));
    } finally {
      setParsing(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);

    try {
      if (editLum) {
        // Update existing
        const res = await authFetch(`/api/admin/luminaires/${editLum.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || t('form.updateFailed'));
        }
        setMessage(t('form.updated'));
      } else {
        // Create new - requires LDT file
        if (!ldtFile) {
          setMessage(t('form.selectLdtToUpload'));
          setSaving(false);
          return;
        }
        const fd = new FormData();
        fd.append('file', ldtFile);
        fd.append('manufacturer', form.manufacturer);
        fd.append('model_family', form.model_family);
        fd.append('optic_family', form.optic_family);
        fd.append('luminaire_name', form.luminaire_name);
        fd.append('power', String(form.power));
        fd.append('cct', String(form.cct));
        fd.append('cri', String(form.cri));
        fd.append('flux', String(form.flux));
        fd.append('efficiency', String(form.efficiency));
        fd.append('LORL', String(form.LORL));
        fd.append('isym', String(form.isym));
        if (form.gama) fd.append('gama', form.gama);
        if (form.difusor) fd.append('difusor', form.difusor);
        if (form.lente) fd.append('lente', form.lente);
        if (form.led_type) fd.append('led_type', form.led_type);

        const res = await authFetch('/api/admin/luminaires/upload', { method: 'POST', body: fd });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || t('form.uploadFailed'));
        }
        setMessage(t('form.created'));
      }
      onSaved();
    } catch (err: any) {
      setMessage(t('form.error', { error: err.message }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm p-5 space-y-4">
      <h3 className="font-semibold text-[#6A6A6A]">
        {editLum ? t('form.editLuminaire') : t('form.newLuminaire')}
      </h3>

      {!editLum && (
        <div>
          <label className="block text-sm font-medium text-[#6A6A6A] mb-1">
            {t('form.ldtFile')} <span className="text-red-500">*</span>
          </label>
          <input
            type="file"
            accept=".ldt"
            onChange={handleFileChange}
            className="block w-full text-sm text-[#6A6A6A] file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-[#1E1E1E]/6 file:text-[#333333] hover:file:bg-blue-100"
          />
          {parsing && <p className="text-xs text-[#6a6a6a] mt-1">{t('form.parsing')}</p>}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Catalog dimension fields */}
        <label className="text-sm font-medium text-[#6A6A6A]">
          Gama
          <select
            value={form.gama}
            onChange={e => handleField('gama', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          >
            <option value="">--</option>
            {gamas.map(g => <option key={g.id} value={g.name}>{g.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          Difusor
          <select
            value={form.difusor}
            onChange={e => handleField('difusor', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          >
            <option value="">--</option>
            {filteredDifusores.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          Lente
          <select
            value={form.lente}
            onChange={e => handleField('lente', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          >
            <option value="">--</option>
            {filteredLentes.map(l => <option key={l.id} value={l.name}>{l.name}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          LED Type
          <select
            value={form.led_type}
            onChange={e => handleField('led_type', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          >
            <option value="">--</option>
            {filteredLedTypes.map(lt => <option key={lt.id} value={lt.name}>{lt.name}</option>)}
          </select>
        </label>

        {/* Legacy fields */}
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('luminaire.manufacturer')}
          <input
            value={form.manufacturer}
            onChange={e => handleField('manufacturer', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('form.modelFamily')}
          <input
            value={form.model_family}
            onChange={e => handleField('model_family', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('form.opticFamily')}
          <input
            value={form.optic_family}
            onChange={e => handleField('optic_family', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('form.luminaireName')}
          <input
            value={form.luminaire_name}
            onChange={e => handleField('luminaire_name', e.target.value)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('luminaire.power')} (W)
          <input
            type="number"
            step="0.1"
            value={form.power}
            onChange={e => handleField('power', parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          CCT (K)
          <input
            type="number"
            step="100"
            value={form.cct}
            onChange={e => handleField('cct', parseInt(e.target.value) || 4000)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          CRI
          <select
            value={form.cri}
            onChange={e => handleField('cri', parseInt(e.target.value))}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          >
            <option value={70}>70</option>
            <option value={80}>80</option>
            <option value={90}>90</option>
          </select>
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('form.flux')}
          <input
            type="number"
            step="0.01"
            value={form.flux}
            onChange={e => handleField('flux', parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          {t('form.efficiency')}
          <input
            type="number"
            step="0.1"
            value={form.efficiency}
            onChange={e => handleField('efficiency', parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          LORL (%)
          <input
            type="number"
            step="0.01"
            value={form.LORL}
            onChange={e => handleField('LORL', parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          Isym <span className="text-xs text-[#6a6a6a] cursor-help" title={t('form.isymHelp')}>ⓘ</span>
          <select
            value={form.isym}
            onChange={e => handleField('isym', parseInt(e.target.value))}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          >
            <option value={0}>0 - {t('form.noSymmetry')}</option>
            <option value={1}>1 - {t('form.rotationalSymmetry')}</option>
            <option value={2}>2 - {t('form.c0c180Symmetry')}</option>
            <option value={3}>3 - {t('form.c90c270Symmetry')}</option>
            <option value={4}>4 - {t('form.quadrantSymmetry')}</option>
          </select>
        </label>
        <label className="text-sm font-medium text-[#6A6A6A]">
          MF origen <span className="text-xs text-[#6a6a6a] cursor-help" title="Factor de mantenimiento ya aplicado en el archivo LDT. 0.85 si la LDT viene con depreciación, 1.0 si es cruda.">ⓘ</span>
          <input
            type="number"
            step="0.01"
            min="0.5"
            max="1.0"
            value={form.mf_origen}
            onChange={e => handleField('mf_origen', Math.min(1, Math.max(0.5, parseFloat(e.target.value) || 0.85)))}
            className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-1.5 text-sm"
          />
        </label>
      </div>

      {message && (
        <div className={`text-sm px-3 py-2 rounded-md ${
          message.startsWith('Error') ? 'bg-red-50 text-red-700' : 'bg-[#1E1E1E]/6 text-[#333333]'
        }`}>
          {message}
        </div>
      )}

      <div className="flex items-center gap-2 pt-2">
        <button
          onClick={handleSave}
          disabled={saving || (!editLum && !ldtFile)}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-[#1E1E1E] text-white hover:bg-[#333333] disabled:opacity-50"
        >
          {saving ? t('form.saving') : editLum ? t('actions.update') : t('actions.create')}
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium rounded-lg border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#F7F4EF]"
        >
          {t('actions.cancel')}
        </button>
      </div>
    </div>
  );
};

export default LuminaireForm;
