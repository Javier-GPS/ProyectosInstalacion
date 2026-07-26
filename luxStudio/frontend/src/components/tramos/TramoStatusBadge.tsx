import React from 'react';
import { useI18n } from '../../i18n';
import type { TramoStatus } from '../../types';

interface TramoStatusBadgeProps {
  status: TramoStatus;
}

const styles: Record<TramoStatus, { wrap: string; icon: React.ReactNode }> = {
  compliant: {
    wrap: 'bg-[#1F7A4D]/10 text-[#1F7A4D] border-[#1F7A4D]/25',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    ),
  },
  non_compliant: {
    wrap: 'bg-[#FDECEA] text-[#B42318] border-[#B42318]/25',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    ),
  },
  dirty: {
    wrap: 'bg-[#F5EDE0] text-[#B7791F] border-[#B7791F]/25',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <line x1="12" y1="7" x2="12" y2="13" />
        <line x1="12" y1="16" x2="12" y2="16" />
      </svg>
    ),
  },
  calculation_pending: {
    wrap: 'bg-[#1E1E1E]/6 text-[#1E1E1E] border-[#1E1E1E]/15',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    ),
  },
  pending: {
    wrap: 'bg-[#F0EDE8] text-[#6A6A6A] border-[#E8E2D8]',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
      </svg>
    ),
  },
  config_error: {
    wrap: 'bg-[#F5EDE0] text-[#B7791F] border-[#B7791F]/25',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12" y2="16" />
      </svg>
    ),
  },
  missing_config: {
    wrap: 'bg-[#6a6a6a]/10 text-[#6a6a6a] border-[#6a6a6a]/30',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12" y2="16" />
      </svg>
    ),
  },
  no_pcb_capacity: {
    wrap: 'bg-[#FDECEA] text-[#B42318] border-[#B42318]/25',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z" />
      </svg>
    ),
  },
};

const TramoStatusBadge: React.FC<TramoStatusBadgeProps> = ({ status }) => {
  const { t } = useI18n();
  const style = styles[status];
  const labelKey = status === 'non_compliant'
    ? 'nonCompliant'
    : status === 'calculation_pending'
      ? 'calculationPending'
      : status === 'no_pcb_capacity'
        ? 'noPcbCapacity'
      : status;
  const label = t(`tramos.status.${labelKey}`);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style.wrap}`}
    >
      {style.icon}
      {label}
    </span>
  );
};

export default TramoStatusBadge;
