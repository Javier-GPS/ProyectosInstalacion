import React from 'react';
import { ArrowLeft } from 'lucide-react';
import { useI18n } from '../../i18n';
import type { WizardStep } from '../../store/types';

interface WizardNavProps {
  currentStep: WizardStep;
  onStepChange: (step: WizardStep) => void;
  onBackToZones: () => void;
  stepLabels?: Partial<Record<WizardStep, string>>;
}

const STEPS: WizardStep[] = ['zona', 'vias', 'informe'];

const STEP_ICONS: Record<WizardStep, string> = {
  proyecto: '📁',
  zona: '📍',
  vias: '🛣️',
  informe: '📊',
};

const WizardNav: React.FC<WizardNavProps> = ({ currentStep, onStepChange, onBackToZones }) => {
  const { t } = useI18n();

  const stepLabel = (step: WizardStep): string => {
    const labels: Record<WizardStep, string> = {
      proyecto: t('nav.projects'),
      zona: t('zone.name'),
      vias: 'Vías OSM',
      informe: 'Informe',
    };
    return labels[step];
  };

  return (
    <nav className="flex items-center gap-0.5" aria-label="Wizard steps">
      <button
        onClick={onBackToZones}
        className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors text-salvi-grey hover:bg-salvi-surface"
        title={t('header.backToZones')}
        aria-label={t('header.backToZones')}
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">{t('zones.list')}</span>
      </button>
      {STEPS.map((step, idx) => {
        const isActive = step === currentStep;
        const isPast = STEPS.indexOf(currentStep) > idx;
        return (
          <React.Fragment key={step}>
            <div className={`h-px w-4 ${isPast || isActive ? 'bg-salvi-black' : 'bg-salvi-line'}`} />
            <button
              onClick={() => onStepChange(step)}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors ${
                isActive
                  ? 'bg-salvi-black text-white shadow-sm'
                  : isPast
                    ? 'text-salvi-grey hover:bg-salvi-surface'
                    : 'text-salvi-muted hover:bg-salvi-surface'
              }`}
              aria-current={isActive ? 'step' : undefined}
            >
              <span className="text-sm">{STEP_ICONS[step]}</span>
              <span className="hidden sm:inline">{stepLabel(step)}</span>
            </button>
          </React.Fragment>
        );
      })}
    </nav>
  );
};

export default WizardNav;
