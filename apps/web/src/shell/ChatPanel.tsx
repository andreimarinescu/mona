import { Button, Icon, MonaAvatar, Spinner } from '@mona/ui';
import { useNavigate } from '@tanstack/react-router';
import { Suspense, lazy, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppState } from '../state/context';
import { usePageContext, usePageDisplay } from './usePageContext';

const ConversationThread = lazy(() => import('../chat/ConversationThread').then((m) => ({ default: m.ConversationThread })));

export function ChatPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { chat, closeChat, setConversationId, clearOutbox } = useAppState();
  const context = usePageContext();
  const display = usePageDisplay();
  const latest = useRef(context);
  useEffect(() => {
    latest.current = context;
  }, [context]);
  const pageContext = useCallback(() => latest.current, []);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!chat.open) return;
    const target = panel.current?.querySelector<HTMLElement>('[data-chat-composer]') ?? panel.current;
    target?.focus();
  }, [chat.open]);

  if (!chat.everOpened) return null;
  const openAsPage = () => {
    const id = chat.conversationId;
    closeChat({ remount: true });
    void navigate(id ? { to: '/chat/$conversationId', params: { conversationId: id } } : { to: '/chat' });
  };
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
        <Button variant="quiet" iconOnly icon="external" aria-label={t('chat.panel.openAsPage')} onClick={openAsPage} />
        <Button variant="quiet" iconOnly icon="x" aria-label={t('shell.chat.close')} onClick={() => closeChat()} />
      </header>
      <p className="m-0 flex items-center gap-2 border-b border-border pb-3 font-ui text-[13px] leading-[18px] text-text-muted" data-testid="page-context">
        <Icon name="info" size={14} />
        {t('shell.chat.sees', { summary: display })}
      </p>
      <div className="min-h-0 flex-1">
        <Suspense fallback={<Spinner label={t('chat.loading')} />}>
          <ConversationThread
            key={chat.generation}
            variant="panel"
            conversationId={chat.conversationId}
            pageContext={pageContext}
            onConversationId={setConversationId}
            autoFocus
            outbox={chat.outbox}
            onOutboxSent={clearOutbox}
          />
        </Suspense>
      </div>
    </aside>
  );
}
