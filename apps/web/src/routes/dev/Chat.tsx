import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ConversationThread } from '../../chat/ConversationThread';
import type { PageContext } from '../../chat/types';

const CHAT_PAGE: PageContext = { route: '/dev/chat', summary: 'Chat page' };

export function Chat() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { c, route, summary } = useSearch({ from: '/dev/chat' });
  const [page] = useState<PageContext>(() => (route && summary ? { route, summary } : CHAT_PAGE));
  return (
    <main className="mx-auto flex h-screen max-w-[960px] flex-col gap-4 p-8">
      <h1 className="m-0 font-voice text-text">{t('dev.chat.title')}</h1>
      <div className="min-h-0 flex-1">
        <ConversationThread
          variant="page"
          conversationId={c}
          pageContext={() => page}
          onConversationId={(id) => void navigate({ to: '/dev/chat', search: (prev) => ({ ...prev, c: id }), replace: true })}
        />
      </div>
    </main>
  );
}
