export type GisLanguage = 'es' | 'en' | 'pt' | 'fr' | 'ca';
export type TranslationValue = string | ((params: Record<string, string | number>) => string);
export type TranslationMap = Record<GisLanguage, Record<string, TranslationValue>>;
