import type { Lang } from '@mona/ui';
import { useTranslation } from 'react-i18next';

export function useLang(): Lang {
  const { i18n } = useTranslation();
  const lng = i18n.resolvedLanguage;
  return lng === 'fr' || lng === 'ro' ? lng : 'en';
}
