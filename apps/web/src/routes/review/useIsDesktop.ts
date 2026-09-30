import { useSyncExternalStore } from 'react';

const QUERY = '(min-width: 1024px)';

function subscribe(cb: () => void) {
  const mq = globalThis.matchMedia?.(QUERY);
  mq?.addEventListener('change', cb);
  return () => mq?.removeEventListener('change', cb);
}

export function useIsDesktop(): boolean {
  return useSyncExternalStore(subscribe, () => globalThis.matchMedia?.(QUERY).matches ?? true, () => true);
}
