import { Button, Checkbox, Tag, format, i18n } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { DocumentSummary, Reason } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { REASONS } from './queue';
import { ReviewListItem } from './ReviewListItem';

export interface ReviewListProps {
  items: DocumentSummary[];
  counts: Record<Reason, number>;
  total: number;
  reason: Reason | 'all';
  onReason(reason: Reason | 'all'): void;
  selectedId: string | undefined;
  checked: Set<string>;
  corrected: Set<string>;
  now: number;
  onCheck(id: string, checked: boolean): void;
  onCheckAll(checked: boolean): void;
  onApprove(): void;
  approving: boolean;
}

export function ReviewList({ items, counts, total, reason, onReason, selectedId, checked, corrected, now, onCheck, onCheckAll, onApprove, approving }: ReviewListProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const selectable = items.filter((d) => !corrected.has(d.id));
  const allChecked = selectable.length > 0 && selectable.every((d) => checked.has(d.id));
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label={t('review.filter.label')}>
        <Tag selected={reason === 'all'} onToggle={() => onReason('all')} lang={lang}>
          {t('review.filter.all', { n: format.number(total, lang) })}
        </Tag>
        {REASONS.filter((r) => counts[r] > 0 || reason === r).map((r) => (
          <Tag key={r} selected={reason === r} onToggle={(on) => onReason(on ? r : 'all')} lang={lang}>
            {`${i18n.REASON[lang][r]} · ${format.number(counts[r], lang)}`}
          </Tag>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md bg-surface-sunken px-3 py-2">
        <Checkbox
          label={t('review.list.selectAll')}
          checked={allChecked}
          indeterminate={!allChecked && checked.size > 0}
          onChange={(e) => onCheckAll(e.target.checked)}
        />
        <span className="font-ui text-[13px] leading-[18px] whitespace-nowrap text-text-muted" aria-live="polite">
          {t('review.list.selected', { count: checked.size, n: format.number(checked.size, lang) })}
        </span>
        <Button variant="secondary" size="sm" icon="check" className="ml-auto" disabled={checked.size === 0} loading={approving} onClick={onApprove}>
          {t('review.list.approve', { count: checked.size, n: format.number(checked.size, lang) })}
        </Button>
      </div>
      <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={t('review.list.label')}>
        {items.map((doc) => (
          <ReviewListItem
            key={doc.id}
            doc={doc}
            selected={doc.id === selectedId}
            checked={checked.has(doc.id)}
            correctedByYou={corrected.has(doc.id)}
            now={now}
            onCheck={(on) => onCheck(doc.id, on)}
          />
        ))}
      </ul>
    </div>
  );
}
