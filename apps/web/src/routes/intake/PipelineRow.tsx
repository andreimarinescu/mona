import { Badge, Button, ReasonChip, StatusPill } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { DocStatusPill } from '../../components/DocStatusPill';
import { useTranslation } from 'react-i18next';
import type { BatchDetail } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { PipelineStepper } from './PipelineStepper';
import { STEPS, stepOf } from './summary';

type Item = BatchDetail['items'][number];

export function PipelineRow({ item, onRestore, busy }: { item: Item; onRestore(journalId: number): void; busy: boolean }) {
  const { t } = useTranslation();
  const lang = useLang();
  const doc = item.document;

  let status: React.ReactNode;
  let where: React.ReactNode = null;
  if (item.outcome === 'rejected') {
    status = <Badge tone="danger">{t('intake.outcome.rejected')}</Badge>;
    where = t(`intake.reject.${item.rejectReason ?? 'unsupported_type'}`);
  } else if (item.outcome === 'duplicate') {
    status = <Badge tone="neutral">{t('intake.outcome.duplicate')}</Badge>;
    where =
      item.deleted && item.restoreJournalId !== null ? (
        <span className="inline-flex flex-wrap items-center gap-2">
          {t('intake.duplicateDeleted')}
          <Button variant="secondary" size="sm" icon="undo" disabled={busy} onClick={() => onRestore(item.restoreJournalId!)}>
            {t('intake.restore')}
          </Button>
        </span>
      ) : (
        t('intake.duplicateOf', { title: doc?.title ?? item.originalName })
      );
  } else if (doc) {
    if (doc.pipelineStage === 'failed') status = <StatusPill status="review" size="sm" lang={lang} label={t('intake.outcome.failed')} />;
    else if (doc.status === 'processing') {
      status = <StatusPill status="processing" size="sm" lang={lang} label={t(`intake.steps.${STEPS[stepOf(doc.pipelineStage) - 1]}`)} />;
      where = t('intake.working');
    } else status = <DocStatusPill doc={doc} size="sm" />;
    if (doc.status === 'filed') where = doc.path.join(' / ');
    else if (doc.status === 'review' || doc.status === 'unreadable') {
      where = (
        <span className="inline-flex flex-wrap items-center gap-2">
          {doc.reasons.map((reason) => (
            <ReasonChip key={reason} reason={reason} lang={lang} />
          ))}
          {doc.entityName ? <span>{doc.entityName}</span> : null}
        </span>
      );
    }
  }

  const viewable = item.outcome === 'accepted' && item.documentId && doc && doc.status !== 'processing';

  return (
    <tr className="border-t border-border align-middle" data-outcome={item.outcome} data-document-id={item.documentId ?? undefined}>
      <th scope="row" className="max-w-[140px] px-4 py-3 text-left md:max-w-[280px] align-middle font-normal text-text [font:var(--type-filename)]">
        {viewable ? (
          <Link to="/documents/$documentId" params={{ documentId: item.documentId! }} className="block truncate text-text no-underline hover:underline" title={item.originalName}>
            {item.originalName}
          </Link>
        ) : (
          <span className="block truncate" title={item.originalName}>
            {item.originalName}
          </span>
        )}
        <span className="mt-1 block font-ui text-[13px] leading-[18px] text-text-muted md:hidden">{where}</span>
      </th>
      <td className="px-2 py-3">{doc && item.outcome === 'accepted' ? <PipelineStepper doc={doc} /> : null}</td>
      <td className="px-2 py-3">{status}</td>
      <td className="hidden px-4 py-3 font-ui text-[14px] leading-5 text-text-muted md:table-cell">{where}</td>
    </tr>
  );
}
