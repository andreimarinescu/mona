import type {
  DataMessagePartProps,
  ReasoningMessagePartProps,
  TextMessagePartProps,
  ToolCallMessagePartProps,
} from '@assistant-ui/react';
import { useAuiState } from '@assistant-ui/react';
import { useTranslation } from 'react-i18next';
import { Badge, Button, Card, ConfidenceMeter, Icon, Spinner, format, type Lang } from '../ds';
import type { DocCardData, InterviewCardData } from './types';

function useLang(): Lang {
  const { i18n } = useTranslation();
  return (['en', 'fr', 'ro'].includes(i18n.language) ? i18n.language : 'en') as Lang;
}

export function ThinkingBlock({ text, status }: ReasoningMessagePartProps) {
  const { t } = useTranslation();
  const live = status.type === 'running';
  const ms = useAuiState((s) => s.message.metadata.custom?.reasoningMs) as number | undefined;
  const label = live
    ? t('dev.chat.thinking.live')
    : ms
      ? t('dev.chat.thinking.done', { seconds: Math.max(1, Math.round(ms / 1000)) })
      : t('dev.chat.thinking.doneShort');
  return (
    <details data-testid="thinking" data-live={live} className="text-text-muted">
      <summary className="flex cursor-pointer items-center gap-2">
        {live ? <Spinner size={16} /> : <Icon name="check" />}
        <span>{label}</span>
      </summary>
      <p className="whitespace-pre-wrap">{text}</p>
    </details>
  );
}

export function MonaText({ text }: TextMessagePartProps) {
  return (
    <p data-testid="mona-text" className="whitespace-pre-wrap text-text">
      {text}
    </p>
  );
}

export function UserText({ text }: TextMessagePartProps) {
  return <p className="whitespace-pre-wrap">{text}</p>;
}

export function ToolActivityChip({ toolName, result }: ToolCallMessagePartProps) {
  const { t, i18n } = useTranslation();
  const live = result === undefined;
  const key = i18n.exists(`dev.chat.tool.${toolName}.done`) ? toolName : 'generic';
  return (
    <span
      data-testid="tool-chip"
      data-tool={toolName}
      data-live={live}
      className="inline-flex items-center gap-2 text-text-muted"
    >
      {live ? <Spinner size={16} /> : <Icon name="check" />}
      {t(`dev.chat.tool.${key}.${live ? 'running' : 'done'}`)}
    </span>
  );
}

export function DocCard({ data }: DataMessagePartProps<DocCardData>) {
  const doc: DocCardData = data;
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div data-card="doc" data-id={doc.id}>
      <Card
        eyebrow={doc.entityName}
        title={doc.title}
        status={doc.status}
        meta={doc.date ? format.date(doc.date, lang, 'medium') : undefined}
        actions={
          <Button size="sm" variant="secondary" icon="file">
            {t('dev.chat.doc.open')}
          </Button>
        }
      >
        <div className="flex flex-col gap-1">
          {doc.amount && <strong>{format.money(doc.amount.value, doc.amount.currency, lang)}</strong>}
          {doc.dueDate && <span>{t('dev.chat.doc.due', { date: format.date(doc.dueDate, lang, 'medium') })}</span>}
          <span className="font-code text-text-muted">{[...doc.path, doc.fileName].join(' / ')}</span>
          {doc.confidence != null && <ConfidenceMeter value={doc.confidence} lang={lang} />}
        </div>
      </Card>
    </div>
  );
}

export function InterviewCard({ data }: DataMessagePartProps<InterviewCardData>) {
  const interview: InterviewCardData = data;
  const { t } = useTranslation();
  const question = interview.questions[0];
  if (!question) return null;
  return (
    <div data-card="interview" data-id={interview.id}>
      <Card from="mona" voice={question.question} lang={question.lang}>
        <div className="flex flex-col gap-2">
          <Badge tone="info">{t('dev.chat.interview.affects', { count: question.affectsCount })}</Badge>
          {question.options.map((o, i) => (
            <Button
              key={o.id}
              data-option={o.id}
              variant={o.suggested ? 'primary' : 'secondary'}
              aria-keyshortcuts={String(i + 1)}
            >
              {o.label}
              {o.suggested && <Badge tone="accent">{t('dev.chat.interview.suggested')}</Badge>}
            </Button>
          ))}
        </div>
      </Card>
    </div>
  );
}
