import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AUTO_DISMISS_MS, UNDO_WINDOW_MS, createToastStore } from './store';

const filed = { key: 'filed', message: 'toast.filed' };

describe('toast store', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('groups toasts with the same key into one with a count', () => {
    const store = createToastStore();
    for (let i = 0; i < 12; i++) store.push(filed);
    const [only, ...rest] = store.getSnapshot();
    expect(rest).toEqual([]);
    expect(only).toMatchObject({ key: 'filed', count: 12 });
  });

  it('shows at most three and queues the rest until a slot frees', () => {
    const store = createToastStore();
    const ids = ['a', 'b', 'c', 'd', 'e'].map((key) => store.push({ key, message: `toast.${key}` }));
    expect(store.getSnapshot().map((t) => t.key)).toEqual(['a', 'b', 'c']);
    store.dismiss(ids[0]!);
    expect(store.getSnapshot().map((t) => t.key)).toEqual(['b', 'c', 'd']);
    vi.advanceTimersByTime(AUTO_DISMISS_MS);
    expect(store.getSnapshot().map((t) => t.key)).toEqual(['e']);
    vi.advanceTimersByTime(AUTO_DISMISS_MS);
    expect(store.getSnapshot()).toEqual([]);
  });

  it('merges into a queued toast of the same key', () => {
    const store = createToastStore();
    for (const key of ['a', 'b', 'c']) store.push({ key, message: key });
    store.push(filed);
    store.push(filed);
    store.dismiss(store.getSnapshot()[0]!.id);
    expect(store.getSnapshot().at(-1)).toMatchObject({ key: 'filed', count: 2 });
  });

  it('keeps a toast with an Undo for at least 8 seconds', () => {
    const store = createToastStore();
    store.push({ ...filed, undo: () => {} });
    vi.advanceTimersByTime(8_000);
    expect(store.getSnapshot()).toHaveLength(1);
    vi.advanceTimersByTime(UNDO_WINDOW_MS - 8_000);
    expect(store.getSnapshot()).toHaveLength(0);
  });

  it('dismisses a toast without Undo sooner than one with Undo', () => {
    const store = createToastStore();
    store.push(filed);
    vi.advanceTimersByTime(AUTO_DISMISS_MS);
    expect(store.getSnapshot()).toHaveLength(0);
    expect(AUTO_DISMISS_MS).toBeLessThan(UNDO_WINDOW_MS);
  });

  it('restarts the window when another toast joins the group', () => {
    const store = createToastStore();
    store.push({ ...filed, undo: () => {} });
    vi.advanceTimersByTime(9_000);
    store.push({ ...filed, undo: () => {} });
    vi.advanceTimersByTime(8_000);
    expect(store.getSnapshot()).toHaveLength(1);
  });

  it('runs every grouped undo once and removes the toast', () => {
    const store = createToastStore();
    const first = vi.fn();
    const second = vi.fn();
    const id = store.push({ ...filed, undo: first });
    store.push({ ...filed, undo: second });
    store.undo(id);
    expect(first).toHaveBeenCalledOnce();
    expect(second).toHaveBeenCalledOnce();
    expect(store.getSnapshot()).toEqual([]);
    store.undo(id);
    expect(first).toHaveBeenCalledOnce();
  });

  it('keeps danger toasts until dismissed', () => {
    const store = createToastStore();
    const id = store.push({ key: 'err', message: 'toast.failed', tone: 'danger' });
    vi.advanceTimersByTime(10 * UNDO_WINDOW_MS);
    expect(store.getSnapshot()).toHaveLength(1);
    store.dismiss(id);
    expect(store.getSnapshot()).toHaveLength(0);
  });

  it('replaces the oldest danger toast when three are open and another arrives', () => {
    const store = createToastStore();
    for (const key of ['e1', 'e2', 'e3', 'e4']) store.push({ key, message: key, tone: 'danger' });
    expect(store.getSnapshot().map((t) => t.key)).toEqual(['e2', 'e3', 'e4']);
  });

  it('notifies subscribers with a new snapshot only on change', () => {
    const store = createToastStore();
    const listener = vi.fn();
    store.subscribe(listener);
    const before = store.getSnapshot();
    store.push(filed);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot()).not.toBe(before);
    store.dismiss(9999);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
