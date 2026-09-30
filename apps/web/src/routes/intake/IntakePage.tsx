import { Banner, Skeleton, Spinner, format } from '@mona/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { errorKey, errorValues } from '../../data/errors';
import { invalidateAfterWrite } from '../../data/journal';
import { batchKey, planUpload, uploadIntake, useBatch, useRecentBatchId } from '../../data/intake';
import { useUndoRunner } from '../../data/journal';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';
import { BatchProgress } from './BatchProgress';
import { BatchQuestionsBanner } from './BatchQuestionsBanner';
import { DropZone } from './DropZone';
import { PipelineRow } from './PipelineRow';
import { intakeSummary } from './summary';

export function IntakePage() {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const undo = useUndoRunner();
  const [visitor, setVisitor] = useState(false);
  const [picked, setPicked] = useState<string | undefined>();
  const latest = useRecentBatchId();
  const batchId = picked ?? latest.data ?? undefined;
  const batch = useBatch(batchId);
  const summary = batch.data?.batch;

  const upload = useMutation({
    mutationFn: (files: File[]) => uploadIntake(files, { visitor }),
    onSuccess: (result) => {
      setPicked(result.batch.id);
      qc.setQueryData(batchKey(result.batch.id), { batch: result.batch, items: result.items.map((item) => ({ ...item, document: null })) });
      void invalidateAfterWrite(qc);
    },
    onError: (err) => toasts.push({ key: 'upload-failed', message: errorKey(err), values: errorValues(err), tone: 'danger' }),
  });

  function onFiles(files: File[]) {
    const { send, overLimit } = planUpload(files);
    if (overLimit.length > 0) toasts.push({ key: 'over-limit', message: 'intake.overLimit', count: overLimit.length, tone: 'warning' });
    if (send.length > 0) upload.mutate(send);
  }

  const previous = useRef<{ id: string; status: string } | null>(null);
  useEffect(() => {
    if (!summary) return;
    const before = previous.current;
    previous.current = { id: summary.id, status: summary.status };
    if (before?.id === summary.id && before.status === 'running' && summary.status === 'done' && summary.counts.filed > 0) {
      toasts.push({
        key: `batch-filed-${summary.id}`,
        message: 'toast.filed',
        count: summary.counts.filed,
        from: 'mona',
        undo: () => void undo({ groupId: summary.groupId }),
      });
    }
  }, [summary, undo]);

  const restore = (journalId: number) => void undo({ journalId });
  const counts = summary ? intakeSummary(summary.counts) : null;

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 p-6 lg:p-10">
      <header className="flex flex-col gap-2">
        <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.intake')}</h1>
        <p className="m-0 text-text-muted">{t('intake.subtitle')}</p>
      </header>
      <DropZone disabled={upload.isPending} visitor={visitor} onVisitorChange={setVisitor} onFiles={onFiles} />
      {upload.isPending ? <Spinner label={t('intake.uploading')} /> : null}
      {summary ? <BatchQuestionsBanner batch={summary} /> : null}
      {batch.isError ? (
        <Banner tone="danger" onDismiss={undefined}>
          {t(errorKey(batch.error), errorValues(batch.error))}
        </Banner>
      ) : null}
      {batchId && batch.isPending ? <Skeleton lines={4} /> : null}
      {summary && batch.data ? (
        <section aria-label={t('intake.batch.region')} className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-1">
          <BatchProgress batch={summary} now={batch.dataUpdatedAt} />
          {summary.status === 'done' && counts ? (
            <p className="m-0 font-ui text-[15px] leading-[22px] font-medium text-text" role="status" data-testid="batch-summary">
              {t('intake.summary', {
                filed: format.number(counts.filed, lang),
                needYou: format.number(counts.needYou, lang),
                unreadable: format.number(counts.unreadable, lang),
                alreadyHad: format.number(counts.alreadyHad, lang),
              })}
            </p>
          ) : null}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <caption className="mona-sr">{t('intake.table.caption')}</caption>
              <thead>
                <tr className="bg-surface-sunken font-ui text-[13px] leading-[18px] text-text-muted">
                  <th scope="col" className="px-4 py-2 font-medium">
                    {t('intake.table.file')}
                  </th>
                  <th scope="col" className="px-2 py-2 font-medium">
                    {t('intake.table.steps')}
                  </th>
                  <th scope="col" className="px-2 py-2 font-medium">
                    {t('intake.table.status')}
                  </th>
                  <th scope="col" className="hidden px-4 py-2 font-medium md:table-cell">
                    {t('intake.table.where')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {batch.data.items.map((item) => (
                  <PipelineRow key={item.id} item={item} onRestore={restore} busy={false} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      {!batchId && !latest.isPending && !upload.isPending ? <p className="m-0 text-text-muted">{t('intake.empty')}</p> : null}
    </div>
  );
}
