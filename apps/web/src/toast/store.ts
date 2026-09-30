export type ToastTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export interface ToastInput {
  /** Toasts with the same key merge into one with a higher count. */
  key: string;
  /** i18n key; receives `count` and `n` (the formatted count) plus `values`. */
  message: string;
  values?: Record<string, string | number>;
  tone?: ToastTone;
  from?: 'mona';
  count?: number;
  undo?: () => void;
}

export interface ToastItem {
  id: number;
  key: string;
  message: string;
  values: Record<string, string | number>;
  tone: ToastTone;
  from?: 'mona';
  count: number;
  undo: (() => void)[];
}

export interface ToastStoreOptions {
  max?: number;
  undoWindowMs?: number;
  autoDismissMs?: number;
}

export const MAX_TOASTS = 3;
export const UNDO_WINDOW_MS = 10_000;
export const AUTO_DISMISS_MS = 6_000;

export function createToastStore(options: ToastStoreOptions = {}) {
  const max = options.max ?? MAX_TOASTS;
  const undoWindowMs = options.undoWindowMs ?? UNDO_WINDOW_MS;
  const autoDismissMs = options.autoDismissMs ?? AUTO_DISMISS_MS;
  const listeners = new Set<() => void>();
  const timers = new Map<number, ReturnType<typeof setTimeout>>();
  let visible: ToastItem[] = [];
  let pending: ToastItem[] = [];
  let nextId = 1;

  const emit = () => listeners.forEach((l) => l());

  function arm(item: ToastItem) {
    clearTimeout(timers.get(item.id));
    timers.delete(item.id);
    if (item.tone === 'danger') return;
    const ms = item.undo.length > 0 ? undoWindowMs : autoDismissMs;
    timers.set(item.id, setTimeout(() => dismiss(item.id), ms));
  }

  function show(item: ToastItem) {
    visible = [...visible, item];
    arm(item);
  }

  function promote() {
    while (visible.length < max && pending.length > 0) show(pending.shift()!);
  }

  function dismiss(id: number) {
    clearTimeout(timers.get(id));
    timers.delete(id);
    const before = visible.length + pending.length;
    visible = visible.filter((t) => t.id !== id);
    pending = pending.filter((t) => t.id !== id);
    if (visible.length + pending.length === before) return;
    promote();
    emit();
  }

  function push(input: ToastInput): number {
    const tone = input.tone ?? 'success';
    const count = input.count ?? 1;
    const same = (t: ToastItem) => t.key === input.key && t.tone === tone;
    const merged = visible.find(same);
    if (merged) {
      const next = { ...merged, count: merged.count + count, undo: input.undo ? [...merged.undo, input.undo] : merged.undo };
      visible = visible.map((t) => (t.id === merged.id ? next : t));
      arm(next);
      emit();
      return merged.id;
    }
    const queued = pending.find(same);
    if (queued) {
      const next = { ...queued, count: queued.count + count, undo: input.undo ? [...queued.undo, input.undo] : queued.undo };
      pending = pending.map((t) => (t.id === queued.id ? next : t));
      emit();
      return queued.id;
    }
    const item: ToastItem = {
      id: nextId++,
      key: input.key,
      message: input.message,
      values: input.values ?? {},
      tone,
      from: input.from,
      count,
      undo: input.undo ? [input.undo] : [],
    };
    if (visible.length < max) show(item);
    else if (tone === 'danger' && visible.every((t) => t.tone === 'danger')) {
      dismissNow(visible[0]!.id);
      show(item);
    } else pending.push(item);
    emit();
    return item.id;
  }

  function dismissNow(id: number) {
    clearTimeout(timers.get(id));
    timers.delete(id);
    visible = visible.filter((t) => t.id !== id);
  }

  function undo(id: number) {
    const item = visible.find((t) => t.id === id);
    if (!item) return;
    dismiss(id);
    item.undo.forEach((fn) => fn());
  }

  function clear() {
    timers.forEach((t) => clearTimeout(t));
    timers.clear();
    visible = [];
    pending = [];
    emit();
  }

  return {
    push,
    dismiss,
    undo,
    clear,
    getSnapshot: () => visible,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export type ToastStore = ReturnType<typeof createToastStore>;

export const toasts: ToastStore = createToastStore();
