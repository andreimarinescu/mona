import { QueryClient } from '@tanstack/react-query';
import { retryTransient } from './data/http';

export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: retryTransient } } });
