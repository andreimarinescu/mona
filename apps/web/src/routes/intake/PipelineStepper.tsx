import { Icon, Tooltip } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { DocumentSummary } from '../../data/dto';
import { STEPS, stepOf } from './summary';

type Outcome = 'filed' | 'review' | 'unreadable' | 'failed' | 'processing';

function outcomeOf(doc: DocumentSummary): Outcome {
  if (doc.pipelineStage === 'failed') return 'failed';
  if (doc.status === 'processing') return 'processing';
  return doc.status;
}

const RESULT_TONE: Record<Exclude<Outcome, 'processing'>, string> = {
  filed: 'border-success bg-success text-on-accent',
  review: 'border-warning bg-warning text-on-accent',
  unreadable: 'border-danger bg-danger text-on-accent',
  failed: 'border-danger bg-danger text-on-accent',
};

const GRID = 'm-0 grid list-none grid-cols-[repeat(5,var(--step-pitch))] p-0 [--step-pitch:60px] md:[--step-pitch:66px] xl:[--step-pitch:72px]';

export function PipelineStepHeader() {
  const { t } = useTranslation();
  return (
    <>
      <span className="mona-sr">{t('intake.table.steps')}</span>
      <ol aria-hidden className={GRID} data-testid="step-header">
        {STEPS.map((step) => (
          <li key={step} className="whitespace-nowrap text-center text-[11px] leading-4 font-medium md:text-[12px]">
            {t(`intake.steps.${step}`)}
          </li>
        ))}
      </ol>
    </>
  );
}

export function PipelineStepper({ doc }: { doc: DocumentSummary }) {
  const { t } = useTranslation();
  const outcome = outcomeOf(doc);
  const current = outcome === 'processing' ? stepOf(doc.pipelineStage) : 5;
  const settled = outcome !== 'processing';
  const label = t('intake.step', { n: current, total: STEPS.length, step: t(`intake.steps.${STEPS[current - 1]}`) });
  return (
    <ol className={GRID} aria-label={label} data-step={current}>
      {STEPS.map((step, i) => {
        const pos = i + 1;
        const done = pos < current || (pos === current && settled);
        const active = pos === current && !settled;
        const isResult = pos === 5 && settled;
        return (
          <li key={step} className="relative flex items-center justify-center" data-step-state={done ? 'done' : active ? 'active' : 'todo'}>
            {i > 0 ? <span aria-hidden className={`absolute top-1/2 left-[calc(-50%+10px)] h-0.5 w-[calc(100%-20px)] -translate-y-1/2 ${pos <= current ? 'bg-text-muted' : 'bg-border'}`} /> : null}
            <Tooltip content={t(`intake.steps.${step}`)}>
              <span
                aria-hidden
                data-step-dot={step}
                className={`relative inline-flex size-5 items-center justify-center rounded-full border-2 ${
                  isResult ? RESULT_TONE[outcome as Exclude<Outcome, 'processing'>] : done ? 'border-text-muted bg-text-muted text-on-accent' : active ? 'border-dashed border-info text-info' : 'border-border text-transparent'
                }`}
              >
                {done ? <Icon name={isResult && outcome !== 'filed' ? (outcome === 'review' ? 'help' : 'x') : 'check'} size={12} strokeWidth={3} /> : null}
                {active ? <Icon name="loader" size={12} spin /> : null}
              </span>
            </Tooltip>
          </li>
        );
      })}
    </ol>
  );
}
