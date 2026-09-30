import { Progress, StatusPill, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { BatchSummary } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { timeLeftMs } from './summary';

export function BatchProgress({ batch, now }: { batch: BatchSummary; now: number }) {
  const { t } = useTranslation();
  const lang = useLang();
  const { counts } = batch;
  const total = counts.accepted;
  const done = total - counts.processing;
  const left = batch.status === 'running' ? timeLeftMs(batch.startedAt, now, done, total) : null;
  const title = batch.title ?? t('intake.batch.title', { count: counts.items, n: format.number(counts.items, lang) });
  const valueText = t('intake.batch.done', { done: format.number(done, lang), total: format.number(total, lang) });
  const minutes = left === null ? null : Math.max(1, Math.round(left / 60_000));
  const pill = (status: 'filed' | 'review' | 'unreadable' | 'processing', n: number, label: string) =>
    n > 0 ? <StatusPill key={status} status={status} size="sm" lang={lang} label={`${label} · ${format.number(n, lang)}`} /> : null;
  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-3" data-testid="batch-progress">
      <div className="flex min-w-[220px] flex-col gap-1">
        <h2 className="m-0 font-ui text-[18px] leading-[26px] font-semibold text-text">{title}</h2>
        <span className="font-ui text-[13px] leading-[18px] text-text-muted">
          {t('intake.batch.started', { time: format.time(batch.startedAt, lang) })}
          {minutes !== null ? ` · ${t('intake.batch.timeLeft', { count: minutes, n: format.number(minutes, lang) })}` : ''}
        </span>
      </div>
      <div className="min-w-[200px] max-w-[320px] flex-1">
        <Progress value={done} max={Math.max(total, 1)} label={valueText} valueText={total === 0 ? undefined : format.percent(done / total, lang)} lang={lang} size="sm" />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {pill('filed', counts.filed, t('intake.counts.filed'))}
        {pill('review', counts.review + counts.failed, t('intake.counts.review'))}
        {pill('unreadable', counts.unreadable + counts.rejected, t('intake.counts.unreadable'))}
        {pill('processing', counts.processing, t('intake.counts.processing'))}
      </div>
    </div>
  );
}
