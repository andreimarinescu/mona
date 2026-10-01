import { createContext, useContext } from 'react';
import type { PageContext } from '../chat/types';
import type { PageFacts } from '../shell/pageContext';

export type EntityScope = 'all' | (string & {});

export interface ChatOutbox {
  id: number;
  message: string;
  pageContext: PageContext;
}

export interface ChatState {
  open: boolean;
  conversationId: string | undefined;
  /** Bumped when a different conversation is opened, so the thread remounts. */
  generation: number;
  everOpened: boolean;
  /** A message the app sends on the person's behalf once the thread is mounted (the batch banner). */
  outbox: ChatOutbox | null;
}

export interface AppState {
  scope: EntityScope;
  setScope(scope: EntityScope): void;
  chat: ChatState;
  /** What the current screen shows (counts, search), published by the screen for the page context. */
  pageFacts: PageFacts | null;
  setPageFacts(facts: PageFacts | null): void;
  openChat(opts?: { opener?: HTMLElement | null; conversationId?: string; send?: { message: string; pageContext: PageContext } }): void;
  clearOutbox(id: number): void;
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
