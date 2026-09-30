import { EmptyState } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

export function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-[880px] p-6 font-ui lg:p-10">
      <h1 className="m-0 mb-6 text-text [font:var(--type-title)]">{t('errors.notFound.title')}</h1>
      <EmptyState title={t('errors.notFound.body')} action={<Link to="/" className="mona-link">{t('errors.notFound.home')}</Link>} />
    </div>
  );
}
