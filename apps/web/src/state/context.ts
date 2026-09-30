import { createContext, useContext } from 'react';

export type EntityScope = 'all' | (string & {});

export interface ChatState {
  open: boolean;
  conversationId: string | undefined;
  /** Bumped when a different conversation is opened, so the thread remounts. */
  generation: number;
  everOpened: boolean;
}

export interface AppState {
  scope: EntityScope;
  setScope(scope: EntityScope): void;
  chat: ChatState;
  openChat(opts?: { opener?: HTMLElement | null; conversationId?: string }): void;
  closeChat(): void;
  setConversationId(id: string): void;
  registerAskButton(el: HTMLElement | null): void;
  registerChatEntry(el: HTMLElement | null): void;
  /** `/`: focus the registered Home entry when on Home, else open (or refocus) the panel. */
  askMona(opts: { home: boolean }): void;
}

export const AppStateContext = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState outside AppStateProvider');
  return ctx;
}
