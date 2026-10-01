import { MonaAvatar } from '@mona/ui';
import { isToolUIPart, getToolName } from 'ai';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { DocumentSummary } from '../data/dto';
import { useLang } from '../shell/useLang';
import { AttachmentChip } from './AttachmentChip';
import { DeadlineCard } from './cards/DeadlineCard';
import { DocCard } from './cards/DocCard';
import { DraftCard } from './cards/DraftCard';
import { ExportCard } from './cards/ExportCard';
import { InterviewCard } from './cards/InterviewCard';
import { ChatRulePreview } from './cards/ChatRulePreview';
import { citedNumbers } from './citations';
import { CitedSources, MonaText } from './MonaText';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolActivityChip, type ToolState } from './ToolActivityChip';
import type { MonaPart, MonaUIMessage } from './types';

export function UserMessage({ message }: { message: MonaUIMessage }) {
  const { t } = useTranslation();
  const text = message.parts.map((p) => (p.type === 'text' ? p.text : '')).join('');
  const attachments = message.metadata?.attachments ?? [];
  return (
    <div data-role="user" className="flex max-w-[85%] flex-col items-end gap-2 self-end">
      <span className="mona-sr">{t('chat.you')}</span>
      {attachments.length > 0 ? (
        <div className="flex flex-wrap justify-end gap-2">
          {attachments.map((a, i) => (
            <AttachmentChip key={`${a.name}-${i}`} attachment={a} />
          ))}
        </div>
      ) : null}
      <p className="m-0 rounded-lg bg-accent-soft px-4 py-3 font-ui text-[17px] leading-[27px] whitespace-pre-wrap text-text">{text}</p>
    </div>
  );
}

function toolState(part: MonaPart): ToolState {
  if (!isToolUIPart(part)) return 'done';
  if (part.state === 'output-available') return 'done';
  if (part.state === 'output-error' || part.state === 'output-denied') return 'interrupted';
  return 'running';
}

function DataCard({ part }: { part: MonaPart }) {
  switch (part.type) {
    case 'data-doc':
      return <DocCard doc={part.data} />;
    case 'data-deadline':
      return <DeadlineCard deadline={part.data} />;
    case 'data-interview':
      return <InterviewCard interview={part.data} />;
    case 'data-rulePreview':
      return <ChatRulePreview ruleId={part.data.rule.id} snapshot={part.data} />;
    case 'data-draft':
      return <DraftCard draft={part.data} />;
    case 'data-export':
      return <ExportCard pack={part.data} />;
    default:
      return null;
  }
}

export interface MonaMessageProps {
  message: MonaUIMessage;
  streaming: boolean;
  newest: boolean;
}

/** Avatar and body: reasoning, tool chips, text with citations, then the cards, in stream order. */
export function MonaMessage({ message, streaming, newest }: MonaMessageProps) {
  const lang = useLang();
  const reply = message.metadata?.replyLanguage;
  const textLang = reply && reply !== lang ? reply : undefined;
  const docs = message.parts.filter((p): p is Extract<MonaPart, { type: 'data-doc' }> => p.type === 'data-doc').map((p) => p.data as DocumentSummary);
  const reasoningBlocks = message.parts.filter((p) => p.type === 'reasoning').length;
  const cited: number[] = [];
  const body: ReactNode[] = [];
  let chips: ReactNode[] = [];
  const flushChips = (key: string) => {
    if (chips.length > 0) body.push(<div key={`chips-${key}`} className="flex flex-wrap gap-2">{chips}</div>);
    chips = [];
  };
  message.parts.forEach((part, i) => {
    if (isToolUIPart(part)) {
      chips.push(<ToolActivityChip key={part.toolCallId} toolName={getToolName(part)} state={toolState(part)} />);
      return;
    }
    flushChips(String(i));
    if (part.type === 'reasoning') {
      body.push(
        <ThinkingBlock
          key={`r${i}`}
          blockKey={`${message.id}:${i}`}
          text={part.text}
          live={part.state === 'streaming'}
          onlyBlockMs={reasoningBlocks === 1 ? message.metadata?.reasoningMs : undefined}
        />,
      );
    } else if (part.type === 'text') {
      if (!part.text.trim()) return;
      cited.push(...citedNumbers(part.text, docs.length));
      body.push(<MonaText key={`t${i}`} text={part.text.trim()} streaming={part.state === 'streaming'} docs={docs} lang={textLang} />);
    } else if (part.type.startsWith('data-')) {
      body.push(<DataCard key={`${part.type}:${(part as { id?: string }).id ?? i}`} part={part} />);
    }
  });
  flushChips('end');
  if (cited.length > 0) body.push(<CitedSources key="sources" docs={docs} cited={cited} />);
  return (
    <div data-role="assistant" className="flex items-start gap-3" aria-busy={streaming || undefined} aria-live={newest ? 'polite' : undefined}>
      <MonaAvatar size={32} state={streaming ? 'thinking' : 'idle'} className="mt-1 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">{body}</div>
    </div>
  );
}
