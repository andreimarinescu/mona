import { Checkbox, Icon, ReasonChip, format, i18n } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import type { DocumentSummary } from '../../data/dto';
import { useLang } from '../../shell/useLang';

export interface ReviewListItemProps {
  doc: DocumentSummary;
  selected: boolean;
  checked: boolean;
  correctedByYou: boolean;
  now: number;
  onCheck(checked: boolean): void;
}

export function ReviewListItem({ doc, selected, checked, correctedByYou, now, onCheck }: ReviewListItemProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const percent = doc.confidence === null ? null : format.percent(doc.confidence / 100, lang);
  return (
    <li
      className={`flex items-start gap-3 rounded-lg border p-3 ${selected ? 'border-accent bg-accent-soft' : 'border-border bg-surface'}`}
      data-testid="review-item"
      data-document-id={doc.id}
      data-selected={selected ? '' : undefined}
    >
      <Checkbox
        checked={checked}
        disabled={correctedByYou}
        aria-label={t('review.list.select', { title: doc.title })}
        onChange={(e) => onCheck(e.target.checked)}
      />
      <span aria-hidden className="inline-flex h-12 w-10 shrink-0 items-center justify-center overflow-hidden rounded-sm border border-border bg-surface-raised text-text-muted">
        {doc.thumbnailUrl ? <img src={doc.thumbnailUrl} alt="" loading="lazy" className="size-full object-cover" /> : <Icon name="file" size={20} />}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Link
          to="/review/$documentId"
          params={{ documentId: doc.id }}
          aria-current={selected ? 'true' : undefined}
          className="font-ui text-[15px] leading-[22px] font-semibold text-text no-underline hover:underline"
        >
          {doc.title}
        </Link>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {correctedByYou ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-surface-sunken px-2 py-0.5 font-ui text-[13px] leading-[18px] text-text">
              <Icon name="pencil" size={14} />
              {t('review.list.corrected')}
            </span>
          ) : (
            doc.reasons.map((reason) => (
              <ReasonChip key={reason} reason={reason} lang={lang} label={reason === 'low' && percent ? `${i18n.REASON[lang].low} · ${percent}` : undefined} />
            ))
          )}
          <span className="font-ui text-[13px] leading-[18px] text-text-muted">
            {t('review.list.arrived', { when: format.relative(doc.arrivedAt, lang, new Date(now)), source: t(`review.source.${doc.source}`) })}
          </span>
        </div>
      </div>
    </li>
  );
}
