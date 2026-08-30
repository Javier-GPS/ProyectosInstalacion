import type { StateCreator } from 'zustand';
import type { WizardStep, DetailSelectionMode, StatusGranular } from '../types';
import type { GisLanguage } from '../../i18n/types';

export interface UiSlice {
  language: GisLanguage;
  sidebarOpen: boolean;
  view: 'projects' | 'project' | 'editor';
  stepWizard: WizardStep;
  detailSelectionMode: DetailSelectionMode;
  statusGranular: Record<string, StatusGranular>;

  setLanguage: (lang: GisLanguage) => void;
  setSidebarOpen: (open: boolean) => void;
  setView: (view: 'projects' | 'project' | 'editor') => void;
  setStepWizard: (step: WizardStep) => void;
  setDetailSelectionMode: (mode: DetailSelectionMode) => void;
  setStatusGranular: (key: string, status: StatusGranular) => void;
}

const LANG_KEY = 'gis-language';

export const createUiSlice: StateCreator<UiSlice, [], [], UiSlice> = (set) => ({
  language: (typeof localStorage !== 'undefined' ? localStorage.getItem(LANG_KEY) as GisLanguage : null) || 'es',
  sidebarOpen: true,
  view: 'projects',
  stepWizard: 'proyecto',
  detailSelectionMode: 'none',
  statusGranular: {},

  setLanguage: (lang) => {
    localStorage.setItem(LANG_KEY, lang);
    set({ language: lang });
  },
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setView: (view) => set({ view }),
  setStepWizard: (step) => set({ stepWizard: step }),
  setDetailSelectionMode: (mode) => set({ detailSelectionMode: mode }),
  setStatusGranular: (key, status) => set((s) => ({
    statusGranular: { ...s.statusGranular, [key]: status },
  })),
});
