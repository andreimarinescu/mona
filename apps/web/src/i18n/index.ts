import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './en.json';
import fr from './fr.json';
import ro from './ro.json';

export const languages = ['en', 'fr', 'ro'] as const;
export type Language = (typeof languages)[number];

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, fr: { translation: fr }, ro: { translation: ro } },
  lng: 'en',
  fallbackLng: 'en',
  supportedLngs: languages,
  interpolation: { escapeValue: false },
});

export default i18n;
