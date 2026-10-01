import { createContext, useContext } from 'react';

export interface ChatCardContext {
  /** The conversation the card was rendered in, for the C2 §14 note; undefined before the first reply. */
  conversationId(): string | undefined;
  /** Puts text in the composer, focuses it, and gives the next turn this page summary (C6 §5.3). */
  prefill(text: string, summary?: string): void;
}

export const ChatCardContext = createContext<ChatCardContext>({
  conversationId: () => undefined,
  prefill: () => undefined,
});

export function useChatCard(): ChatCardContext {
  return useContext(ChatCardContext);
}
