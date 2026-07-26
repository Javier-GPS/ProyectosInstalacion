import React, { createContext, useContext, useMemo } from 'react';
import { useConfigStore } from '../store/useConfigStore';
import type { Language, TranslationMap } from './types';
import { common } from './common';
import { admin } from './admin';
import { projects } from './projects';
import { optimize } from './optimize';
import { editor } from './editor';
import { tramos } from './tramos';

export type { Language };

const modules: TranslationMap[] = [common, admin, projects, optimize, editor, tramos];

const translations: Record<Language, Record<string, TranslationMap[Language][string]>> = {
  es: {},
  en: {},
  fr: {},
  pt: {},
  de: {},
  it: {},
};

for (const mod of modules) {
  for (const lang of Object.keys(mod) as Language[]) {
    Object.assign(translations[lang], mod[lang]);
  }
}

interface I18nContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const language = useConfigStore(state => state.language);
  const setLanguage = useConfigStore(state => state.setLanguage);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    t: (key, params) => {
      const entry = translations[language][key] ?? translations.en[key];
      if (typeof entry === 'function') return entry(params ?? {});
      return entry ?? key;
    },
  }), [language, setLanguage]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export const useI18n = () => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return context;
};
