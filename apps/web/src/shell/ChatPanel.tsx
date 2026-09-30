import { Button, MonaAvatar, Spinner } from '@mona/ui';
import { Suspense, lazy, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppState } from '../state/context';
import { usePageContext } from './usePageContext';

const ConversationThread = lazy(() => import('../chat/ConversationThread').then((m) => ({ default: m.ConversationThread })));

export function ChatPanel() {
  const { t } = useTranslation();
  const { chat, closeChat, setConversationId } = useAppState();
  const context = usePageContext();
  const latest = useRef(context);
  useEffect(() => {
    latest.current = context;
  }, [context]);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!chat.open) return;
    const target = panel.current?.querySelector<HTMLElement>('[data-chat-composer]') ?? panel.current;
    target?.focus();
  }, [chat.open]);

  if (!chat.everOpened) return null;
  return (
    <aside
      ref={panel}
      role="complementary"
      aria-label={t('shell.chat.title')}
      tabIndex={-1}
      className={`${chat.open ? 'flex' : 'hidden'} fixed inset-y-0 right-0 z-40 box-border w-full flex-col gap-3 border-l border-border bg-surface-raised p-4 shadow-3 outline-none lg:w-[460px]`}
    >
      <header className="flex items-center gap-3">
        <MonaAvatar size={32} />
        <h2 className="m-0 flex-1 font-ui text-[18px] leading-[26px] font-semibold text-text">{t('shell.chat.title')}</h2>
        <Button variant="quiet" iconOnly icon="x" aria-label={t('shell.chat.close')} onClick={closeChat} />
      </header>
      <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted" data-testid="page-context">
        {t('shell.chat.sees', { summary: context.summary })}
      </p>
      <div className="min-h-0 flex-1">
        <Suspense fallback={<Spinner label={t('dev.chat.loading')} />}>
          <ConversationThread
            key={chat.generation}
            conversationId={chat.conversationId}
            pageContext={() => latest.current}
            onConversationId={setConversationId}
            autoFocus
          />
        </Suspense>
      </div>
    </aside>
  );
}
