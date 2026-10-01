import { ConfidenceMeter, Icon, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { DocStatusPill } from '../../components/DocStatusPill';
import { InternalLink } from '../../components/InternalLink';
import { calendarDate } from '../../data/calendar';
import type { DocumentSummary } from '../../data/dto';
import { useCategories, useThresholds } from '../../data/registry';
import { useLang } from '../../shell/useLang';
import { CardShell } from './CardShell';

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col">
      <dt className="font-ui text-[13px] leading-[18px] text-text-muted">{label}</dt>
      <dd className="m-0 truncate font-ui text-[15px] leading-[22px] font-semibold text-text">{children}</dd>
    </div>
  );
}

export function DocCard({ doc }: { doc: DocumentSummary }) {
  const { t } = useTranslation();
  const lang = useLang();
  const categories = useCategories().data ?? [];
  const { confidenceHigh, confidenceLow } = useThresholds();
  const category = categories.find((c) => c.id === doc.categoryId);
  const categoryLabel = category ? category.labels[lang] : doc.categoryId;
  const path = [...doc.path, doc.fileName].join(' / ');
  return (
    <CardShell kind="doc" id={doc.id} label={doc.title}>
      <div className="flex gap-4">
        <span aria-hidden className="hidden h-[88px] w-[66px] shrink-0 items-center justify-center overflow-hidden rounded-sm border border-border bg-paper text-text-muted sm:inline-flex">
          {doc.thumbnailUrl ? <img src={doc.thumbnailUrl} alt="" loading="lazy" className="size-full object-cover" /> : <Icon name="file" size={24} />}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 className="m-0 min-w-0 font-ui text-[16px] leading-6 font-semibold text-text">{doc.title}</h3>
            <DocStatusPill doc={doc} size="sm" />
          </div>
          <dl className="m-0 grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-4">
            {doc.entityName ? <Fact label={t('chat.doc.entity')}>{doc.entityName}</Fact> : null}
            {categoryLabel ? <Fact label={t('chat.doc.category')}>{categoryLabel}</Fact> : null}
            {doc.date ? <Fact label={t('chat.doc.date')}>{format.date(calendarDate(doc.date), lang, 'medium')}</Fact> : null}
            {doc.amount ? (
              <Fact label={t('chat.doc.amount')}>
                <span className="tabular-nums">{format.money(doc.amount.value, doc.amount.currency, lang)}</span>
              </Fact>
            ) : null}
          </dl>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="min-w-0 flex-1 truncate font-code text-[13px] leading-[18px] text-text-muted" title={path}>
              <span className="mona-sr">{t('chat.doc.path')}: </span>
              {path}
            </span>
            {doc.confidence !== null ? (
              <ConfidenceMeter value={doc.confidence / 100} lang={lang} thresholds={{ high: confidenceHigh / 100, medium: confidenceLow / 100 }} />
            ) : null}
            <InternalLink href={`/documents/${doc.id}`} className="mona-btn mona-btn--secondary mona-btn--sm no-underline" aria-label={`${t('chat.doc.open')}: ${doc.title}`}>
              {t('chat.doc.open')}
            </InternalLink>
          </div>
        </div>
      </div>
    </CardShell>
  );
}
