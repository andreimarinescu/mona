import { useRouterState } from '@tanstack/react-router';
import { useEffect } from 'react';
import i18n from '../i18n';
import { useSettings } from '../data/hooks';

function ProfileLanguage() {
  const locale = useSettings().data?.locale;
  useEffect(() => {
    if (locale) void i18n.changeLanguage(locale);
  }, [locale]);
  return null;
}

/** The profile's language drives i18next everywhere but /unlock (where nothing is readable yet and the page takes it from the auth state) and the dev pages. */
export function LanguageSync() {
  const unlocking = useRouterState({ select: (s) => s.location.pathname === '/unlock' || s.location.pathname.startsWith('/dev/') });
  return unlocking ? null : <ProfileLanguage />;
}
