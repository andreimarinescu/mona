import { setupWorker } from 'msw/browser';
import { chatBodies, createHandlers } from './handlers';
import { createWorld } from './world';

export const MSW_FLAG = 'mona.msw';

export async function startMockApi() {
  const params = new URLSearchParams(globalThis.location?.search);
  const world = createWorld({ stepMs: Number(params.get('mswStep') ?? globalThis.localStorage?.getItem('mona.msw.step') ?? 600) });
  const chatDelayMs = Number(globalThis.localStorage?.getItem('mona.msw.chatDelay') ?? 25);
  const worker = setupWorker(...createHandlers(world, { chatDelayMs }));
  await worker.start({ onUnhandledFrame: 'bypass', quiet: true });
  Object.assign(window, { __mock: world, __chatBodies: chatBodies });
}
