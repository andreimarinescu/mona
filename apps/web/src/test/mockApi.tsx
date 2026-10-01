import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setupServer } from 'msw/node';
import type { ReactNode } from 'react';
import { afterAll, afterEach, beforeAll, beforeEach, vi } from 'vitest';
import { createChat, createHandlers, createWorld, type World, type WorldOptions } from '../mocks';
import type { MockChat } from '../mocks/chat';
import { AppStateProvider } from '../state/AppStateProvider';
import { toasts } from '../toast/store';

/** Serves the mock C2 API over MSW for a test file; `world()` is a fresh one per test. */
export function useMockApi(options: WorldOptions | (() => WorldOptions) = {}) {
  const server = setupServer();
  const nativeFetch = globalThis.fetch;
  let current: World;
  let chat: MockChat;

  beforeAll(() => {
    vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) =>
      nativeFetch(typeof input === 'string' && input.startsWith('/') ? `${location.origin}${input}` : input, init),
    );
    server.listen({ onUnhandledFrame: 'error' });
  });
  beforeEach(() => {
    const opts = typeof options === 'function' ? options() : options;
    current = createWorld(opts);
    chat = createChat(current, { chunkDelayMs: opts.chatDelayMs ?? 0, draftMs: opts.draftMs ?? 0 });
    server.resetHandlers(...createHandlers(current, {}, chat));
  });
  afterEach(() => {
    toasts.clear();
  });
  afterAll(() => {
    server.close();
    vi.unstubAllGlobals();
  });
  return { world: () => current, chat: () => chat, server };
}

export function queryWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return {
    client,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <AppStateProvider>{children}</AppStateProvider>
      </QueryClientProvider>
    ),
  };
}
