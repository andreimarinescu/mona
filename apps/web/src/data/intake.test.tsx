import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { queryWrapper, useMockApi } from '../test/mockApi';
import { MAX_FILES, MAX_FILE_BYTES, MAX_REQUEST_BYTES, planUpload, useBatch } from './intake';

const file = (size: number, name = 'a.pdf') => ({ name, size }) as File;
const pdf = (text: string) => ({ name: `${text}.pdf`, type: 'application/pdf', bytes: new TextEncoder().encode(`%PDF-1.4 ${text}`) });

describe('planUpload (C2 §5.1 limits)', () => {
  it('sends what fits and sets the rest aside', () => {
    const big = file(MAX_FILE_BYTES + 1, 'big.pdf');
    const ok = file(1_000, 'ok.pdf');
    expect(planUpload([ok, big])).toEqual({ send: [ok], overLimit: [big] });
  });

  it('keeps at most 50 files', () => {
    const files = Array.from({ length: MAX_FILES + 3 }, (_, i) => file(10, `f${i}.pdf`));
    const plan = planUpload(files);
    expect(plan.send).toHaveLength(MAX_FILES);
    expect(plan.overLimit).toHaveLength(3);
  });

  it('keeps the request under 250 MB', () => {
    const files = Array.from({ length: 12 }, (_, i) => file(MAX_FILE_BYTES, `f${i}.pdf`));
    const plan = planUpload(files);
    expect(plan.send.length * MAX_FILE_BYTES).toBeLessThanOrEqual(MAX_REQUEST_BYTES);
    expect(plan.send.length + plan.overLimit.length).toBe(12);
  });
});

describe('useBatch polling against the mock C2', () => {
  const api = useMockApi(() => ({ stepMs: 100, debriefDelayMs: 4_000, now: () => Date.now() }));

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function count(paths: string[], id: string) {
    return paths.filter((p) => p.endsWith(`/api/batches/${id}`)).length;
  }

  async function run(files: { name: string; type: string; bytes: Uint8Array }[], untilMs: number) {
    const world = api.world();
    const seen: string[] = [];
    api.server.events.on('request:start', ({ request }) => void seen.push(new URL(request.url).pathname));
    const created = await world.intake(files, { visitor: false });
    const id = created.batch.id;
    const { Wrapper } = queryWrapper();
    const hook = renderHook(() => useBatch(id), { wrapper: Wrapper });
    const timeline: { at: number; requests: number; status?: string; debrief?: string }[] = [];
    for (let t = 0; t <= untilMs; t += 500) {
      await vi.advanceTimersByTimeAsync(500);
      const b = hook.result.current.data?.batch;
      timeline.push({ at: t, requests: count(seen, id), status: b?.status, debrief: b?.debrief?.status });
    }
    api.server.events.removeAllListeners();
    return timeline;
  }

  it('keeps polling after done until the debrief appears, then stops', async () => {
    const timeline = await run([pdf('scan_needs_review')], 12_000);
    const doneAt = timeline.find((p) => p.status === 'done')!;
    const readyAt = timeline.find((p) => p.debrief === 'ready')!;
    expect(doneAt).toBeDefined();
    expect(readyAt).toBeDefined();
    expect(readyAt.at).toBeGreaterThan(doneAt.at);
    const between = timeline.filter((p) => p.at >= doneAt.at && p.at <= readyAt.at);
    expect(between[between.length - 1]!.requests).toBeGreaterThan(between[0]!.requests);
    const last = timeline[timeline.length - 1]!;
    const afterReady = timeline.filter((p) => p.at >= readyAt.at + 500);
    expect(afterReady[0]!.requests).toBe(last.requests);
  });

  it('stops at done when nothing needs review', async () => {
    const timeline = await run([pdf('invoice_clean')], 12_000);
    const doneAt = timeline.find((p) => p.status === 'done')!;
    const settled = timeline.filter((p) => p.at >= doneAt.at + 500);
    expect(settled.length).toBeGreaterThan(3);
    expect(new Set(settled.map((p) => p.requests)).size).toBe(1);
  });
});
