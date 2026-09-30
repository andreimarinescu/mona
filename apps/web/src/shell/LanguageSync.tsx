import { useEffect } from 'react';
import i18n from '../i18n';
import { useSettings } from '../data/hooks';

export function LanguageSync() {
  const locale = useSettings().data?.locale;
  useEffect(() => {
    if (locale) void i18n.changeLanguage(locale);
  }, [locale]);
  return null;
}
