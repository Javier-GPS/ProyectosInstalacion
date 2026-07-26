export type Language = 'es' | 'en' | 'fr' | 'pt' | 'de' | 'it';

export type TranslationValue = string | ((params: Record<string, string | number>) => string);
export type TranslationMap = Record<Language, Record<string, TranslationValue>>;
