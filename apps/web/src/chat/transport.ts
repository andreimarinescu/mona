import { DefaultChatTransport } from 'ai';
import type { Lang } from '@mona/ui';
import { csrfHeaders } from '../data/http';
import type { MonaUIMessage, PageContext } from './types';

export interface TurnContext {
  conversationId?: string;
  pageContext: () => PageContext;
  locale: () => string;
}

export function lastUserText(messages: MonaUIMessage[]): string {
  const last = messages.findLast((m) => m.role === 'user');
  return (last?.parts ?? []).map((p) => (p.type === 'text' ? p.text : '')).join('');
}

/** Sends only the new user text; Hermes keeps the history (C3 §2). */
export function monaTransport(ctx: TurnContext) {
  let conversationId = ctx.conversationId;
  let nextContext: PageContext | null = null;
  let replyLanguage: Lang | undefined;
  const transport = new DefaultChatTransport<MonaUIMessage>({
    api: '/api/chat',
    headers: csrfHeaders,
    prepareSendMessagesRequest: ({ messages }) => {
      const override = nextContext;
      nextContext = null;
      return {
        body: {
          conversationId,
          message: lastUserText(messages),
          pageContext: override ?? ctx.pageContext(),
          locale: ctx.locale(),
          ...(replyLanguage ? { replyLanguage } : {}),
        },
      };
    },
  });
  return {
    transport,
    conversationId: () => conversationId,
    /** The next request carries this page context instead of the route's. */
    overrideNext: (context: PageContext) => {
      nextContext = context;
    },
    setConversationId: (id: string) => {
      conversationId = id;
    },
    /** C3 §2: pinned by "Keep …"; sent on every later turn. */
    setReplyLanguage: (lang: Lang) => {
      replyLanguage = lang;
    },
  };
}
