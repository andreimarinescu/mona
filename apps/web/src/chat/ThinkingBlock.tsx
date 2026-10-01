import { Icon } from '@mona/ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useBlockSeconds } from './reasoningClock';

export interface ThinkingBlockProps {
  /** `messageId:partIndex`, so each block keeps its own time. */
  blockKey: string;
  text: string;
  live: boolean;
  /** The turn's `reasoningMs`, passed only when this is the message's one reasoning block. */
  onlyBlockMs?: number;
}

export function ThinkingBlock({ blockKey, text, live, onlyBlockMs }: ThinkingBlockProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const seconds = useBlockSeconds(blockKey, live, onlyBlockMs);
  const label = live ? t('chat.thinking.live') : seconds === null ? t('chat.thinking.untimed') : t('chat.thinking.done', { count: seconds });
  return (
    <details
      data-testid="thinking"
      data-live={live}
      data-seconds={seconds ?? undefined}
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className={`rounded-md px-4 py-3 ${live ? 'border border-dashed border-info bg-surface' : 'bg-surface-sunken'}`}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 font-ui text-[14px] leading-5 [&::-webkit-details-marker]:hidden">
        <Icon name={live ? 'loader' : open ? 'chevron-down' : 'chevron-right'} spin={live} size={16} />
        <span className={`flex-1 font-semibold ${live ? 'text-info' : 'text-text'}`} aria-live={live ? 'polite' : undefined}>
          {label}
        </span>
        <span className="text-text-muted">{open ? t('chat.thinking.hide') : t('chat.thinking.show')}</span>
      </summary>
      <p className="m-0 mt-2 font-ui text-[14px] leading-[22px] whitespace-pre-wrap text-text-muted">{text.trim()}</p>
    </details>
  );
}
