import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryHistory, createRootRoute, createRouter } from '@tanstack/react-router';
import { act, render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { ChatCardContext } from '../chat/context';
import { AppStateProvider } from '../state/AppStateProvider';

export interface RenderInAppOptions {
  conversationId?: string;
  prefill?: (text: string, summary?: string) => void;
}

/** Renders inside a memory router, a fresh query client, app state and a chat card context. */
export async function renderInApp(ui: ReactNode, { conversationId, prefill = () => undefined }: RenderInAppOptions = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const card = { conversationId: () => conversationId, prefill };
  const root = createRootRoute({ component: () => <ChatCardContext.Provider value={card}>{ui}</ChatCardContext.Provider> });
  const router = createRouter({ routeTree: root, history: createMemoryHistory({ initialEntries: ['/'] }) });
  const result = render(
    <QueryClientProvider client={client}>
      <AppStateProvider>
        <RouterProvider router={router} />
      </AppStateProvider>
    </QueryClientProvider>,
  );
  await act(() => router.load());
  return { ...result, client, router };
}
