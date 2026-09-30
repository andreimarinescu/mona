import logoUrl from '@design/mona-handoff/assets/mona-logo.svg';
import { EmptyState } from '@mona/ui';
import { useTranslation } from 'react-i18next';

export function Unlock() {
  const { t } = useTranslation();
  return (
    <main id="main-content" className="mx-auto flex min-h-screen max-w-[480px] flex-col items-center justify-center gap-6 p-8 font-ui">
      <img src={logoUrl} alt="Mona" width={160} height={50} />
      <h1 className="m-0 text-center text-text [font:var(--type-title)]">{t('nav.unlock')}</h1>
      <p className="m-0 text-center text-text-muted">{t('app.tagline')}</p>
      <EmptyState title={t('placeholder.title')}>{t('placeholder.body')}</EmptyState>
    </main>
  );
}
