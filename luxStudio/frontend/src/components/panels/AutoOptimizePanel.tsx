import React, { useEffect, useMemo, useState } from 'react';
import { useConfigStore } from '../../store/useConfigStore';
import type { AdvancedOptimizationLimits, AdvancedOptimizationObjective, AdvancedOptimizationVariables, LDTInfo } from '../../types';
import { useI18n } from '../../i18n';

interface AutoOptimizePanelProps {
  loading: boolean;
  onRunAdvanced: (
    variables: AdvancedOptimizationVariables,
    objective: AdvancedOptimizationObjective,
    opticFamilies: string[],
    limits?: AdvancedOptimizationLimits,
  ) => void;
}

const AutoOptimizePanel: React.FC<AutoOptimizePanelProps> = ({ loading, onRunAdvanced }) => {
  const { t } = useI18n();
  const { manufacturer, model_family, optic_family, gama, difusor, led_type } = useConfigStore();
  const [variables, setVariables] = useState<AdvancedOptimizationVariables>({
    power: true,
    spacing: false,
    height: false,
    arm_length: false,
    tilt: false,
    optic_family: false,
  });
  const [objective, setObjective] = useState<AdvancedOptimizationObjective>('technical_limits');
  const [limits, setLimits] = useState<Record<keyof AdvancedOptimizationLimits, string>>({
    power: '500',
    spacing: '5',
    height: '40',
    arm_length: '4',
    tilt: '25',
  });
  const [catalog, setCatalog] = useState<LDTInfo[]>([]);
  const [selectedOptics, setSelectedOptics] = useState<string[]>([]);
  const [validCombos, setValidCombos] = useState<Array<{ gama: string; difusor: string; lente: string; led_type: string }>>([]);

  useEffect(() => {
    Promise.all([
      fetch('/api/ldt/catalog').then(r => r.json()),
      fetch('/api/ldt/dimensions').then(r => r.json()),
    ])
      .then(([cat, dims]) => {
        setCatalog(Array.isArray(cat) ? cat : []);
        setValidCombos(dims.valid_combinations || []);
      })
      .catch(() => {
        setCatalog([]);
        setValidCombos([]);
      });
  }, []);

  const availableOptics = useMemo(() => {
    const catalogOptics = catalog
      .filter(item => (!manufacturer || item.manufacturer === manufacturer) && (!model_family || item.model_family === model_family))
      .map(item => item.optic_family);
    if (!gama && !difusor && !led_type) {
      return Array.from(new Set(catalogOptics)).sort();
    }
    const validLentes = new Set(
      validCombos
        .filter(vc =>
          (!gama || vc.gama === gama) &&
          (!difusor || vc.difusor === difusor) &&
          (!led_type || vc.led_type === led_type)
        )
        .map(vc => vc.lente)
        .filter(Boolean)
    );
    return Array.from(new Set(catalogOptics.filter(optic => validLentes.has(optic)))).sort();
  }, [catalog, manufacturer, model_family, gama, difusor, led_type, validCombos]);

  useEffect(() => {
    if (!variables.optic_family) {
      setSelectedOptics(optic_family ? [optic_family] : []);
      return;
    }
    setSelectedOptics(current => {
      const valid = current.filter(item => availableOptics.includes(item));
      return valid.length > 0 ? valid : availableOptics;
    });
  }, [availableOptics, optic_family, variables.optic_family]);

  const toggleVariable = (key: keyof AdvancedOptimizationVariables) => {
    setVariables(current => {
      const nextValue = !current[key];
      if (key === 'optic_family' && nextValue) {
        setSelectedOptics(availableOptics);
      }
      return { ...current, [key]: nextValue };
    });
  };

  const toggleOptic = (optic: string) => {
    setSelectedOptics(current => (
      current.includes(optic)
        ? current.filter(item => item !== optic)
        : [...current, optic].sort()
    ));
  };

  const handleRun = () => {
    const numericLimits = Object.entries(limits).reduce<AdvancedOptimizationLimits>((acc, [key, value]) => {
      const parsed = Number(value);
      if (value !== '' && Number.isFinite(parsed)) {
        acc[key as keyof AdvancedOptimizationLimits] = parsed;
      }
      return acc;
    }, {});
    onRunAdvanced(variables, objective, selectedOptics, numericLimits);
  };

  const limitDefaults: Record<keyof AdvancedOptimizationLimits, number> = {
    power: 500,
    spacing: 5,
    height: 40,
    arm_length: 4,
    tilt: 25,
  };

  const variableRows: Array<{
    key: keyof AdvancedOptimizationVariables;
    label: string;
    unit?: string;
    min?: number;
    max?: number;
    step?: number;
    limitKey?: keyof AdvancedOptimizationLimits;
    lowerBound?: boolean;
  }> = [
    { key: 'power', label: t('luminaire.power'), unit: 'W', min: 1, max: 500, step: 1, limitKey: 'power' },
    { key: 'spacing', label: t('optimize.spacingMin'), unit: 'm', min: 5, max: 60, step: 1, limitKey: 'spacing', lowerBound: true },
    { key: 'height', label: t('pole.height'), unit: 'm', min: 4, max: 40, step: 0.5, limitKey: 'height' },
    { key: 'arm_length', label: t('pole.armLength'), unit: 'm', min: 0, max: 4, step: 0.25, limitKey: 'arm_length' },
    { key: 'tilt', label: t('pole.armTilt'), unit: 'deg', min: -25, max: 25, step: 1, limitKey: 'tilt' },
    { key: 'optic_family', label: t('luminaire.lensOptic') },
  ];

  return (
    <section className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] shadow-sm">
      <div className="border-b border-[#E8E2D8] bg-[#FCF9F5] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-[#1E1E1E]">{t('optimize.title')}</h3>
            <p className="text-xs text-[#A09A91] mt-0.5">
              {t('optimize.advancedSubtitle')}
            </p>
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-wide text-[#1E1E1E] bg-[#1E1E1E]/6 border border-blue-100 rounded-full px-2 py-1">
            {t('optimize.advanced')}
          </span>
        </div>
      </div>

      <div className="space-y-3 p-4">
        <div className="space-y-3">
            <label className="block">
              <span className="block text-[10px] uppercase tracking-wide text-[#6a6a6a] mb-1.5">{t('optimize.priority')}</span>
              <select
                value={objective}
                onChange={(event) => setObjective(event.target.value as AdvancedOptimizationObjective)}
                className="w-full rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-3 py-2 text-xs font-medium text-[#6A6A6A] outline-none focus:border-emerald-300 focus:ring-2 focus:ring-emerald-100"
              >
                <option value="technical_limits">{t('optimize.closestLimits')}</option>
                <option value="min_power">{t('optimize.lowestPower')}</option>
                <option value="max_spacing">{t('optimize.maxSpacing')}</option>
              </select>
            </label>

            <div className="space-y-1.5">
              <div className="text-[10px] uppercase tracking-wide text-[#6a6a6a]">{t('optimize.allowChanges')}</div>
              {variableRows.map(({ key, label, unit, min, max, step, limitKey, lowerBound }) => (
                <label
                  key={key}
                  className={`grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                    variables[key]
                      ? 'bg-[#1F7A4D]/10 border-[#1F7A4D]/25 text-emerald-800'
                      : 'bg-[#FFFFFF] border-[#E8E2D8] text-[#A09A91] hover:bg-[#F7F4EF]'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={variables[key]}
                    onChange={() => toggleVariable(key)}
                    className="h-3.5 w-3.5 rounded border-[#D4CEC6] text-[#1F7A4D] focus:ring-emerald-500"
                  />
                  <span>{label}</span>
                  {limitKey && variables[key] && (
                    <span className="flex items-center gap-1 justify-self-end">
                      <span className="text-[10px] font-semibold uppercase text-[#6a6a6a]">
                        {lowerBound ? t('optimize.min') : t('optimize.max')}
                      </span>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={limits[limitKey]}
                        placeholder={`${limitDefaults[limitKey]}`}
                        onChange={event => setLimits(current => ({ ...current, [limitKey]: event.target.value }))}
                        className="w-16 rounded-md border border-[#E8E2D8] bg-[#FFFFFF] px-2 py-1 text-right text-xs font-semibold text-[#6A6A6A] outline-none focus:border-emerald-300 focus:ring-2 focus:ring-emerald-100"
                      />
                      {unit && <span className="w-7 text-[10px] font-semibold text-[#6a6a6a]">{unit}</span>}
                    </span>
                  )}
                </label>
              ))}
              <p className="text-[11px] leading-snug text-[#6a6a6a]">
                {t('optimize.maxHint')}
              </p>
              <p className="text-[11px] leading-snug text-[#6a6a6a]">
                {t('optimize.minHint')}
              </p>
            </div>

            {variables.optic_family && (
              <div className="rounded-lg border border-[#E8E2D8] bg-[#FCF9F5] px-3 py-2">
                <div className="mb-2 text-[10px] uppercase tracking-wide text-[#6a6a6a]">{t('optimize.lensSelection')}</div>
                <div className="flex flex-wrap gap-1.5">
                  {availableOptics.map(optic => (
                    <label
                      key={optic}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        selectedOptics.includes(optic)
                          ? 'border-blue-200 bg-[#1E1E1E]/6 text-blue-700'
                          : 'border-[#E8E2D8] bg-[#FFFFFF] text-[#A09A91]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedOptics.includes(optic)}
                        onChange={() => toggleOptic(optic)}
                        className="h-3 w-3 rounded border-[#D4CEC6] text-[#1E1E1E] focus:ring-blue-500"
                      />
                      {optic}
                    </label>
                  ))}
                  {availableOptics.length === 0 && (
                    <span className="text-xs text-[#6a6a6a]">{t('optimize.noLenses')}</span>
                  )}
                </div>
              </div>
            )}
        </div>

      </div>
      <div className="border-t border-[#E8E2D8] bg-[#FFFFFF] p-3">
        <button
          type="button"
          onClick={handleRun}
          disabled={loading}
          className={`w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-all ${
            loading
              ? 'cursor-not-allowed bg-emerald-400'
              : 'bg-emerald-600 shadow-sm shadow-emerald-100 hover:bg-emerald-700 active:bg-emerald-800'
          }`}
        >
          {loading ? t('optimize.optimizing') : t('optimize.runAdvanced')}
        </button>
      </div>
    </section>
  );
};

export default AutoOptimizePanel;
