import { useChat } from '@ai-sdk/react';
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from '@assistant-ui/react';
import { useAISDKRuntime } from '@assistant-ui/react-ai-sdk';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DocCard, InterviewCard, MonaText, ThinkingBlock, ToolActivityChip, UserText } from '../../chat/parts';
import { monaTransport } from '../../chat/transport';
import type { MonaUIMessage } from '../../chat/types';
import { Banner, Spinner } from '../../ds';

const PAGE_CONTEXT = { route: '/dev/chat', summary: 'Chat page' };

function UserMessage() {
  return (
    <MessagePrimitive.Root className="self-end rounded-md bg-accent-soft p-3" data-role="user">
      <MessagePrimitive.Parts components={{ Text: UserText }} />
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="flex flex-col gap-3" data-role="assistant">
      <MessagePrimitive.Parts
        components={{
          Text: MonaText,
          Reasoning: ThinkingBlock,
          tools: { Fallback: ToolActivityChip },
          data: { by_name: { doc: DocCard, interview: InterviewCard } },
        }}
      />
    </MessagePrimitive.Root>
  );
}

function Thread({ conversationId, initial }: { conversationId?: string; initial: MonaUIMessage[] }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [mona] = useState(() =>
    monaTransport({
      conversationId,
      pageContext: () => PAGE_CONTEXT,
      locale: () => i18n.language,
    }),
  );
  const chat = useChat<MonaUIMessage>({
    id: conversationId,
    messages: initial,
    transport: mona.transport,
    onFinish: ({ message }) => {
      const id = message.metadata?.conversationId;
      if (id && id !== mona.conversationId()) {
        mona.setConversationId(id);
        void navigate({ to: '/dev/chat', search: { c: id }, replace: true });
      }
    },
  });
  const runtime = useAISDKRuntime(chat);
  const error = chat.error?.message;
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex h-full flex-col gap-4" data-chat-status={chat.status}>
        <ThreadPrimitive.Viewport className="flex flex-1 flex-col gap-4 overflow-y-auto" aria-live="polite">
          <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
        </ThreadPrimitive.Viewport>
        {error && (
          <Banner tone="danger" from="mona">
            {i18n.exists(`dev.chat.error.${error}`) ? t(`dev.chat.error.${error}`) : t('dev.chat.error.internal')}
          </Banner>
        )}
        <ComposerPrimitive.Root className="flex gap-2">
          <ComposerPrimitive.Input
            className="flex-1 rounded-md border border-border p-2"
            placeholder={t('dev.chat.composer.placeholder')}
            aria-label={t('dev.chat.composer.placeholder')}
          />
          <ComposerPrimitive.Send className="rounded-md bg-accent px-4 text-on-accent">
            {t('dev.chat.composer.send')}
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

export function Chat() {
  const { t } = useTranslation();
  const { c } = useSearch({ from: '/dev/chat' });
  const [conversationId] = useState(c);
  const transcript = useQuery({
    queryKey: ['conversation-messages', conversationId],
    enabled: !!conversationId,
    staleTime: Infinity,
    queryFn: async (): Promise<MonaUIMessage[]> => {
      const res = await fetch(`/api/conversations/${conversationId}/messages`);
      if (!res.ok) throw new Error(`transcript ${res.status}`);
      return res.json();
    },
  });
  return (
    <main className="mx-auto flex h-screen max-w-lg flex-col gap-4 p-8">
      <h1 className="font-voice text-text">{t('dev.chat.title')}</h1>
      {conversationId && transcript.isPending ? (
        <Spinner label={t('dev.chat.loading')} />
      ) : (
        <Thread conversationId={conversationId} initial={transcript.data ?? []} />
      )}
    </main>
  );
}
