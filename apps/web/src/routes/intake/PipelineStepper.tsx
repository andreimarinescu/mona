import { Icon } from '@mona/ui';
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

export function PipelineStepper({ doc }: { doc: DocumentSummary }) {
  const { t } = useTranslation();
  const outcome = outcomeOf(doc);
  const current = outcome === 'processing' ? stepOf(doc.pipelineStage) : 5;
  const settled = outcome !== 'processing';
  const label = t('intake.step', { n: current, total: STEPS.length, step: t(`intake.steps.${STEPS[current - 1]}`) });
  return (
    <ol className="m-0 flex list-none items-center gap-0 p-0" aria-label={label} data-step={current}>
      {STEPS.map((step, i) => {
        const pos = i + 1;
        const done = pos < current || (pos === current && settled);
        const active = pos === current && !settled;
        const isResult = pos === 5 && settled;
        return (
          <li key={step} className="flex items-center" data-step-state={done ? 'done' : active ? 'active' : 'todo'}>
            {i > 0 ? <span aria-hidden className={`h-0.5 w-3 lg:w-6 ${pos <= current ? 'bg-text-muted' : 'bg-border'}`} /> : null}
            <span
              aria-hidden
              className={`inline-flex size-5 items-center justify-center rounded-full border-2 ${
                isResult ? RESULT_TONE[outcome as Exclude<Outcome, 'processing'>] : done ? 'border-text-muted bg-text-muted text-on-accent' : active ? 'border-dashed border-info text-info' : 'border-border text-transparent'
              }`}
            >
              {done ? <Icon name={isResult && outcome !== 'filed' ? (outcome === 'review' ? 'help' : 'x') : 'check'} size={12} strokeWidth={3} /> : null}
              {active ? <Icon name="loader" size={12} spin /> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
