import { DefaultChatTransport } from 'ai';
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
  const transport = new DefaultChatTransport<MonaUIMessage>({
    api: '/api/chat',
    prepareSendMessagesRequest: ({ messages }) => ({
      body: {
        conversationId,
        message: lastUserText(messages),
        pageContext: (() => {
          const override = nextContext;
          nextContext = null;
          return override ?? ctx.pageContext();
        })(),
        locale: ctx.locale(),
      },
    }),
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
  };
}
