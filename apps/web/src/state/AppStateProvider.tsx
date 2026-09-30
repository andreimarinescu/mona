import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppStateContext, type AppState, type ChatState, type EntityScope } from './context';

const INITIAL_CHAT: ChatState = { open: false, conversationId: undefined, generation: 0, everOpened: false };

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<EntityScope>('all');
  const [chat, setChat] = useState<ChatState>(INITIAL_CHAT);
  const opener = useRef<HTMLElement | null>(null);
  const askButton = useRef<HTMLElement | null>(null);
  const chatEntry = useRef<HTMLElement | null>(null);
  const chatOpen = useRef(false);

  const openChat = useCallback<AppState['openChat']>((opts) => {
    const active = document.activeElement;
    if (!chatOpen.current) {
      opener.current = opts?.opener ?? (active instanceof HTMLElement && active !== document.body ? active : null);
    }
    chatOpen.current = true;
    setChat((c) => {
      const switched = opts?.conversationId !== undefined && opts.conversationId !== c.conversationId;
      return {
        open: true,
        everOpened: true,
        conversationId: switched ? opts.conversationId : c.conversationId,
        generation: switched ? c.generation + 1 : c.generation,
      };
    });
  }, []);

  const closeChat = useCallback(() => {
    if (!chatOpen.current) return;
    chatOpen.current = false;
    setChat((c) => ({ ...c, open: false }));
    const target = opener.current?.isConnected ? opener.current : askButton.current;
    opener.current = null;
    target?.focus();
  }, []);

  const setConversationId = useCallback((id: string) => setChat((c) => ({ ...c, conversationId: id })), []);
  const registerAskButton = useCallback((el: HTMLElement | null) => {
    askButton.current = el;
  }, []);
  const registerChatEntry = useCallback((el: HTMLElement | null) => {
    chatEntry.current = el;
  }, []);

  const askMona = useCallback<AppState['askMona']>(
    ({ home }) => {
      if (home && chatEntry.current?.isConnected) {
        chatEntry.current.focus();
        return;
      }
      if (chatOpen.current) {
        document.querySelector<HTMLElement>('[data-chat-composer]')?.focus();
        return;
      }
      openChat();
    },
    [openChat],
  );

  const value = useMemo<AppState>(
    () => ({ scope, setScope, chat, openChat, closeChat, setConversationId, registerAskButton, registerChatEntry, askMona }),
    [scope, chat, openChat, closeChat, setConversationId, registerAskButton, registerChatEntry, askMona],
  );
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}
