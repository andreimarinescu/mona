import { useSyncExternalStore } from 'react';
import { toasts, type ToastItem, type ToastStore } from './store';

export function useToasts(store: ToastStore = toasts): ToastItem[] {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
