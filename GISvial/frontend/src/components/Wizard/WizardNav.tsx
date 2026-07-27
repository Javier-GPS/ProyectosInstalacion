import React from 'react';
import { useI18n } from '../../i18n';
import type { WizardStep } from '../../store/types';

interface WizardNavProps {
  currentStep: WizardStep;
  onStepChange: (step: WizardStep) => void;
  stepLabels?: Partial<Record<WizardStep, string>>;
}

const STEPS: WizardStep[] = ['proyecto', 'zona', 'vias', 'luminarias', 'informe'];

const STEP_ICONS: Record<WizardStep, string> = {
  proyecto: '📁',
  zona: '📍',
  vias: '🛣️',
  luminarias: '💡',
  informe: '📊',
};

const WizardNav: React.FC<WizardNavProps> = ({ currentStep, onStepChange }) => {
  const { t } = useI18n();

  const stepLabel = (step: WizardStep): string => {
    const labels: Record<WizardStep, string> = {
      proyecto: t('nav.projects'),
      zona: t('zone.name'),
      vias: 'Vías OSM',
      luminarias: t('detail.elements', { n: '' }).replace(' ()', ''),
      informe: 'Informe',
    };
    return labels[step];
  };

  return (
    <nav className="flex items-center gap-0.5" aria-label="Wizard steps">
      {STEPS.map((step, idx) => {
        const isActive = step === currentStep;
        const isPast = STEPS.indexOf(currentStep) > idx;
        return (
          <React.Fragment key={step}>
            {idx > 0 && (
              <div className={`h-px w-4 ${isPast || isActive ? 'bg-salvi-black' : 'bg-salvi-line'}`} />
            )}
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
