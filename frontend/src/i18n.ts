import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import it from './locales/it.json';
import en from './locales/en.json';
import ko from './locales/ko.json';

function readSavedLanguage(): string {
  if (typeof globalThis === 'undefined') return 'ko';
  if (!('localStorage' in globalThis)) return 'ko';

  try {
    return globalThis.localStorage?.getItem('lang') ?? 'ko';
  } catch {
    return 'ko';
  }
}

const savedLang = readSavedLanguage();

i18n
  .use(initReactI18next)
  .init({
    resources: {
      it: { translation: it },
      en: { translation: en },
      ko: { translation: ko },
    },
    lng: savedLang,
    fallbackLng: 'ko',
    interpolation: { escapeValue: false },
  });

export default i18n;
