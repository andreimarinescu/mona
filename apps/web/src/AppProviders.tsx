import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { queryClient } from './queryClient';
import { AppStateProvider } from './state/AppStateProvider';

export function AppProviders({ children, client = queryClient }: { children: ReactNode; client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <AppStateProvider>{children}</AppStateProvider>
    </QueryClientProvider>
  );
}
