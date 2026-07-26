import React from 'react';
import { useConfigStore } from '../../store/useConfigStore';
import EditableSlider from '../ui/EditableSlider';
import { useI18n } from '../../i18n';

type ArrangementPanelProps = {
  embedded?: boolean;
};

const ArrangementPanel: React.FC<ArrangementPanelProps> = ({ embedded = false }) => {
  const { t } = useI18n();
  const {
    arm_length, setArmLength,
    tilt, setTilt,
  } = useConfigStore();

  const content = (
    <div className={embedded ? 'space-y-2' : 'p-4 space-y-4'}>
        <div className="grid grid-cols-2 gap-2">
          <EditableSlider
            label={t('pole.armLength')}
            value={arm_length}
            min={0}
            max={4}
            step={0.25}
            unit="m"
            decimals={2}
            onChange={setArmLength}
            dense={embedded}
          />
          <div>
            <label className="mb-1 block text-[13px] font-semibold text-[#6A6A6A]">
              {t('pole.armTilt')} <span className="text-[#6a6a6a]">({tilt}°)</span>
            </label>
            <div className="grid grid-cols-3 gap-1">
              {[0, 5, 10, 15, 20, 25].map(deg => (
                <button
                  key={deg}
                  onClick={() => setTilt(deg)}
                  className={`rounded-md py-1 text-xs font-semibold transition-all
                    ${tilt === deg
                      ? 'bg-[#1E1E1E] text-white shadow-sm'
                      : 'bg-[#FFFFFF] text-[#6A6A6A] hover:bg-[#E8E2D8]'
                    }`}
                >
                  {deg}°
                </button>
              ))}
            </div>
          </div>
        </div>
    </div>
  );

  if (embedded) return content;

  return (
    <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
      <div className="px-4 py-3 bg-[#FCF9F5] border-b border-[#E8E2D8]">
        <h3 className="font-semibold text-[#6A6A6A] flex items-center gap-2">
          <svg className="w-4 h-4 text-[#1E1E1E]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
          </svg>
          {t('pole.title')}
        </h3>
      </div>
      {content}
    </div>
  );
};

export default ArrangementPanel;
