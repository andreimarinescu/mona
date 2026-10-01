import { useSyncExternalStore } from 'react';

export function useMinWidth(px: number): boolean {
  const query = `(min-width: ${px}px)`;
  return useSyncExternalStore(
    (cb) => {
      const mq = globalThis.matchMedia?.(query);
      mq?.addEventListener('change', cb);
      return () => mq?.removeEventListener('change', cb);
    },
    () => globalThis.matchMedia?.(query).matches ?? false,
    () => false,
  );
}
