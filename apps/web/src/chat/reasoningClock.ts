import { createContext, useContext, useEffect, useState, useSyncExternalStore } from 'react';

/** Wall time of each reasoning block, measured as it streams: C3's `reasoningMs` is the turn's sum. */
export class ReasoningClock {
  private readonly spans = new Map<string, { start: number; end?: number }>();
  private readonly listeners = new Set<() => void>();

  constructor(private readonly now: () => number = () => Date.now()) {}

  observe(key: string, live: boolean) {
    const span = this.spans.get(key);
    if (live && !span) this.spans.set(key, { start: this.now() });
    else if (!live && span && span.end === undefined) {
      span.end = this.now();
      this.listeners.forEach((l) => l());
    }
  }

  elapsed(key: string): number {
    const span = this.spans.get(key);
    return span ? (span.end ?? this.now()) - span.start : 0;
  }

  measured(key: string): number | null {
    const span = this.spans.get(key);
    return span?.end === undefined ? null : span.end - span.start;
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
}

export const ReasoningClockContext = createContext(new ReasoningClock());

export function toSeconds(ms: number): number {
  return Math.max(1, Math.round(ms / 1000));
}

/** Seconds for one block: measured live, else the turn's `reasoningMs` when this is its only block, else unknown. */
export function useBlockSeconds(key: string, live: boolean, onlyBlockMs: number | undefined): number | null {
  const clock = useContext(ReasoningClockContext);
  useEffect(() => clock.observe(key, live), [clock, key, live]);
  const measured = useSyncExternalStore(clock.subscribe, () => clock.measured(key));
  if (live) return null;
  if (measured !== null) return toSeconds(measured);
  return onlyBlockMs ? toSeconds(onlyBlockMs) : null;
}

/** Whole seconds a live block has been open, re-read once a second. */
export function useLiveSeconds(key: string, live: boolean): number {
  const clock = useContext(ReasoningClockContext);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [live]);
  return Math.floor(clock.elapsed(key) / 1000);
}
