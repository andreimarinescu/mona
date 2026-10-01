import { setupWorker } from 'msw/browser';
import { chatBodies, createHandlers } from './handlers';
import { createWorld } from './world';

export const MSW_FLAG = 'mona.msw';

export async function startMockApi() {
  const params = new URLSearchParams(globalThis.location?.search);
  const flag = (name: string) => params.get(`msw${name[0]!.toUpperCase()}${name.slice(1)}`) ?? globalThis.localStorage?.getItem(`mona.msw.${name}`) ?? undefined;
  const autoLock = Number(flag('autoLock'));
  const world = createWorld({
    stepMs: Number(flag('step') ?? 600),
    seed: flag('seed') !== '0',
    locked: flag('locked') === '1',
    locale: ['en', 'fr', 'ro'].includes(flag('locale') ?? '') ? (flag('locale') as 'en' | 'fr' | 'ro') : undefined,
    autoLockMinutes: Number.isFinite(autoLock) && autoLock > 0 ? autoLock : undefined,
  });
  if (flag('brain') === 'offline') world.account.setMona('offline');
  const chatDelayMs = Number(flag('chatDelay') ?? 25);
  const worker = setupWorker(...createHandlers(world, { chatDelayMs }));
  await worker.start({ onUnhandledFrame: 'bypass', quiet: true });
  Object.assign(window, { __mock: world, __chatBodies: chatBodies });
}
