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
    <main className="mx-auto flex h-screen max-w-lg flex-col gap-4 p-8">
      <h1 className="font-voice text-text">{t('dev.chat.title')}</h1>
      <ConversationThread
        conversationId={c}
        pageContext={() => page}
        onConversationId={(id) =>
          void navigate({ to: '/dev/chat', search: (prev) => ({ ...prev, c: id }), replace: true })
        }
      />
    </main>
  );
}
