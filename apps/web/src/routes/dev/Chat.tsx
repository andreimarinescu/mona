import { useNavigate, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { ConversationThread } from '../../chat/ConversationThread';

const PAGE_CONTEXT = { route: '/dev/chat', summary: 'Chat page' };

export function Chat() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { c } = useSearch({ from: '/dev/chat' });
  return (
    <main className="mx-auto flex h-screen max-w-lg flex-col gap-4 p-8">
      <h1 className="font-voice text-text">{t('dev.chat.title')}</h1>
      <ConversationThread
        conversationId={c}
        pageContext={() => PAGE_CONTEXT}
        onConversationId={(id) => void navigate({ to: '/dev/chat', search: { c: id }, replace: true })}
      />
    </main>
  );
}
