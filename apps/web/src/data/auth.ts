import { useEffect, useRef } from 'react';
import type { AuthState } from './dto';
import { get, post, request, setCsrfToken } from './http';

export const HEARTBEAT_MS = 60_000;

/** C2 §16.3: `next` is followed only when it starts with a single `/`; anything else goes Home. */
export function safeNext(next: unknown): string {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') && !next.startsWith('/unlock') ? next : '/';
}

export function unlockHref(here: string): { to: '/unlock'; search: { next?: string } } {
  const next = safeNext(here);
  return { to: '/unlock', search: next === '/' ? {} : { next } };
}

const TITLES = /^(dr\.?|docteur|doctor|doamna|domnul|mme|m\.)\s+/i;

export function firstName(profileName: string | null | undefined): string {
  return (profileName ?? '').replace(TITLES, '').trim().split(/\s+/)[0] ?? '';
}

export const fetchAuthState = () => get<AuthState>('/api/auth/state');

export async function unlock(password: string): Promise<AuthState> {
  const state = await request<AuthState>('POST', '/api/auth/unlock', { json: { password } });
  setCsrfToken(state.csrfToken);
  return state;
}

export const lock = () => post<void>('/api/auth/lock');
export const heartbeat = () => post<void>('/api/auth/heartbeat');

const ACTIVITY_EVENTS = ['keydown', 'pointerdown', 'touchstart'] as const;

/** C2 §2.3: at most one heartbeat a minute, and only after the person used the keyboard, pointer or touch. */
export function useHeartbeat(send: () => Promise<unknown> = heartbeat, intervalMs = HEARTBEAT_MS) {
  const active = useRef(false);
  const lastSent = useRef(0);
  useEffect(() => {
    lastSent.current = Date.now();
    const flush = () => {
      if (!active.current) return;
      active.current = false;
      lastSent.current = Date.now();
      void send().catch(() => undefined);
    };
    const onActivity = () => {
      active.current = true;
      if (Date.now() - lastSent.current >= intervalMs) flush();
    };
    for (const type of ACTIVITY_EVENTS) document.addEventListener(type, onActivity, { passive: true, capture: true });
    const timer = setInterval(flush, intervalMs);
    return () => {
      for (const type of ACTIVITY_EVENTS) document.removeEventListener(type, onActivity, { capture: true });
      clearInterval(timer);
    };
  }, [send, intervalMs]);
}
