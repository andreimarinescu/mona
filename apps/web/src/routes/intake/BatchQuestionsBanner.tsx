import { Banner, Button } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { BatchSummary } from '../../data/dto';
import { useAppState } from '../../state/context';
import { showsQuestionsBanner } from './summary';

export function BatchQuestionsBanner({ batch }: { batch: BatchSummary }) {
  const { t } = useTranslation();
  const { openChat } = useAppState();
  if (!showsQuestionsBanner(batch)) return null;
  const count = batch.debrief!.openQuestions;
  const state = batch.status === 'running' ? 'running' : 'finished';
  return (
    <Banner
      tone="info"
      from="mona"
      title={t('intake.banner.questions', { count })}
      actions={
        <Button
          variant="primary"
          iconEnd="arrow-right"
          onClick={(e) =>
            openChat({
              opener: e.currentTarget,
              send: {
                message: t('chat.banner.debrief'),
                pageContext: { route: '/intake', summary: `Intake, batch ${batch.id} ${state}, ${count} questions` },
              },
            })
          }
        >
          {t('intake.banner.answer')}
        </Button>
      }
    >
      {t('intake.banner.hint')}
    </Banner>
  );
}
