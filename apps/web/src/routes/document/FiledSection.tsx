import { Breadcrumbs, Banner, format } from '@mona/ui';
import { useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import { folderHref } from '../../data/archive';
import type { DocumentDetail } from '../../data/dto';
import { useLang } from '../../shell/useLang';

export function FiledSection({ doc }: { doc: DocumentDetail }) {
  const { t } = useTranslation();
  const lang = useLang();
  const router = useRouter();
  const reviewable = doc.status === 'review' || doc.status === 'unreadable';

  if (reviewable) {
    return (
      <section aria-labelledby="filed-heading" className="flex flex-col gap-3">
        <h3 id="filed-heading" className="m-0 text-text [font:var(--type-heading)]">
          {t('viewer.filed.title')}
        </h3>
        <Banner tone="warning">
          {t('viewer.filed.notYet')}{' '}
          <InternalLink href={`/review/${doc.id}`} className="text-info underline">
            {t('viewer.filed.review')}
          </InternalLink>
        </Banner>
      </section>
    );
  }

  const crumbs = doc.path.map((segment, i) => {
    const href = folderHref(doc.path.slice(0, i + 1));
    return {
      label: segment,
      href,
      onClick: (e: React.MouseEvent) => {
        e.preventDefault();
        router.history.push(href);
      },
    };
  });
  const when = doc.filedAt ? format.date(doc.filedAt, lang) : null;
  return (
    <section aria-labelledby="filed-heading" className="flex flex-col gap-3" data-testid="filed-section">
      <h3 id="filed-heading" className="m-0 text-text [font:var(--type-heading)]">
        {t('viewer.filed.title')}
      </h3>
      <div className="flex flex-col gap-2 rounded-sm bg-surface-sunken px-3 py-3">
        {crumbs.length > 0 ? <Breadcrumbs items={crumbs} maxItems={6} label={t('viewer.filed.path')} /> : null}
        <span className="break-all text-text [font:var(--type-filename)]" data-testid="filed-name">
          {doc.fileName}
        </span>
      </div>
      <p className="m-0 font-ui text-[15px] leading-[22px] text-text">
        {doc.filedBy ? t(`viewer.filed.by_${doc.filedBy}`, { date: when ?? '' }) : t('viewer.filed.unknown')}
        {doc.rule ? (
          <>
            {' · '}
            {t('viewer.filed.rule')}{' '}
            <InternalLink href={`/rules/${doc.rule.id}`} className="text-info underline">
              {doc.rule.name}
            </InternalLink>
          </>
        ) : null}
      </p>
    </section>
  );
}
