import { Button, MonaAvatar } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { STREAM_CODES, chatErrorCode } from './errorCode';

/** "Mona is offline" for `mona_offline`; an inline line with Try again for anything else. */
export function ChatError({ error, onRetry }: { error: Error; onRetry(): void }) {
  const { t } = useTranslation();
  const code = chatErrorCode(error);
  const text = STREAM_CODES.includes(code) ? t(`chat.error.${code}`) : t(`errors.${code}`);
  if (code === 'mona_offline') {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-lg border border-border bg-surface-sunken p-4" data-testid="chat-offline">
        <MonaAvatar size={32} state="offline" />
        <div className="flex flex-1 flex-col gap-2">
          <strong className="font-ui text-[15px] leading-[22px] text-text">{t('chat.offline.title')}</strong>
          <span className="font-ui text-[15px] leading-[22px] text-text-muted">{text}</span>
          <span>
            <Button size="sm" variant="secondary" icon="undo" onClick={onRetry}>
              {t('common.retry')}
            </Button>
          </span>
        </div>
      </div>
    );
  }
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 pl-11 font-ui text-[15px] leading-[22px] text-text-muted" data-testid="chat-error" data-code={code}>
      <span>{text}</span>
      <Button size="sm" variant="ghost" onClick={onRetry}>
        {t('common.retry')}
      </Button>
    </div>
  );
}
