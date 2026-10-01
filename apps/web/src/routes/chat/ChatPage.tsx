import { Button, MonaAvatar, Spinner } from '@mona/ui';
import { useNavigate, useParams } from '@tanstack/react-router';
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ConversationList } from '../../chat/ConversationList';
import { useConversations } from '../../data/conversations';
import { usePageContext } from '../../shell/usePageContext';
import { useAppState } from '../../state/context';

const ConversationThread = lazy(() => import('../../chat/ConversationThread').then((m) => ({ default: m.ConversationThread })));

interface ThreadSlot {
  key: number;
  /** The id the thread was opened with (undefined: a new conversation). */
  id: string | undefined;
  /** The route's id this slot has seen. */
  route: string | undefined;
  /** The id a new conversation received from its first reply. */
  own: string | undefined;
}

function Empty() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <MonaAvatar size={56} />
      <h3 className="m-0 font-voice text-[24px] leading-8 font-normal text-text">{t('chat.page.emptyTitle')}</h3>
      <p className="m-0 max-w-[520px] font-ui text-[15px] leading-[22px] text-text-muted">{t('chat.page.emptyBody')}</p>
    </div>
  );
}

export function ChatPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { openChat } = useAppState();
  const routeId = useParams({ strict: false }).conversationId as string | undefined;
  const [slot, setSlot] = useState<ThreadSlot>({ key: 0, id: routeId, route: routeId, own: undefined });
  if (routeId !== slot.route) {
    const ours = routeId !== undefined && routeId === slot.own;
    setSlot(ours ? { ...slot, route: routeId } : { key: slot.key + 1, id: routeId, route: routeId, own: undefined });
  }
  const current = slot.own ?? slot.id;
  const [listOpen, setListOpen] = useState(false);
  const context = usePageContext();
  const latest = useRef(context);
  useEffect(() => {
    latest.current = context;
  }, [context]);
  const pageContext = useCallback(() => latest.current, []);
  const title = useConversations('').items.find((c) => c.id === current)?.title;

  const onConversationId = useCallback((id: string) => setSlot((s) => ({ ...s, own: id })), []);
  useEffect(() => {
    if (slot.own && slot.route !== slot.own) void navigate({ to: '/chat/$conversationId', params: { conversationId: slot.own }, replace: true });
  }, [slot.own, slot.route, navigate]);

  return (
    <div className="flex h-[calc(100dvh-6rem)] min-h-0 lg:h-screen">
      <h1 className="mona-sr">{t('nav.chat')}</h1>
      <div className={`${listOpen ? 'flex' : 'hidden'} box-border w-full shrink-0 flex-col border-r border-border bg-surface px-4 py-6 lg:flex lg:w-[292px]`}>
        <ConversationList activeId={current} onPick={() => setListOpen(false)} />
      </div>
      <div className={`${listOpen ? 'hidden' : 'flex'} min-w-0 flex-1 flex-col lg:flex`}>
        <header className="box-border flex min-h-[72px] items-center gap-3 border-b border-border px-4 lg:px-10">
          <span className="lg:hidden">
            <Button variant="quiet" size="sm" icon="chevron-left" onClick={() => setListOpen(true)}>
              {t('chat.page.back')}
            </Button>
          </span>
          <h2 className="m-0 min-w-0 flex-1 truncate font-ui text-[20px] leading-7 font-semibold text-text" data-testid="chat-title">
            {title ?? (current ? t('nav.chat') : t('chat.page.newTitle'))}
          </h2>
          <span className="hidden lg:inline">
            <Button
              variant="secondary"
              size="sm"
              icon="external"
              onClick={() => {
                void navigate({ to: '/' });
                openChat({ conversationId: current, reload: true });
              }}
            >
              {t('chat.page.openAsPanel')}
            </Button>
          </span>
        </header>
        <div className="min-h-0 flex-1">
          <Suspense fallback={<Spinner label={t('chat.loading')} />}>
            <ConversationThread key={slot.key} variant="page" conversationId={slot.id} pageContext={pageContext} onConversationId={onConversationId} autoFocus empty={<Empty />} />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
