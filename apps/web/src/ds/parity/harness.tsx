import { cleanup, render, screen, fireEvent, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import type { ComponentType, ReactElement } from 'react';
import { vi } from 'vitest';

export type Mona = Record<string, ComponentType<any>> & { format: any; i18n: any };

export interface Log {
  entries: unknown[];
  fn: (name: string) => (...args: unknown[]) => void;
}

export interface Ctx {
  user: UserEvent;
  screen: typeof screen;
  within: typeof within;
  fireEvent: typeof fireEvent;
  log: Log;
  snap: () => void;
}

export interface Case {
  name: string;
  ui: (M: Mona, log: Log) => ReactElement;
  steps?: (ctx: Ctx) => Promise<void>;
}

const ID_TOKEN = /_r_[0-9a-z]+_|«r[0-9a-z]+»|:r[0-9a-z]+:/g;

function simplify(a: unknown): unknown {
  if (typeof a === 'function') return '[fn]';
  if (a && typeof a === 'object' && 'nativeEvent' in a) return '[event]';
  if (Array.isArray(a)) return a.map(simplify);
  if (a instanceof File) return `File(${a.name},${a.size})`;
  return a;
}

function makeLog(): Log {
  const entries: unknown[] = [];
  return { entries, fn: (name) => (...args) => void entries.push([name, ...args.map(simplify)]) };
}

function canon(node: Node, ids: Map<string, string>, out: string[]): void {
  const mapIds = (s: string) =>
    s.replace(ID_TOKEN, (m) => {
      if (!ids.has(m)) ids.set(m, `ID${ids.size}`);
      return ids.get(m) as string;
    });
  if (node.nodeType === Node.TEXT_NODE) {
    out.push(JSON.stringify(mapIds(node.textContent ?? '')));
    return;
  }
  if (!(node instanceof HTMLElement || node instanceof SVGElement)) return;
  const attrs = [...node.attributes]
    .filter((a) => a.name !== 'style')
    .map((a) => `${a.name}=${JSON.stringify(mapIds(a.value))}`);
  const style = node.getAttribute('style');
  if (style !== null) {
    const decls = [...Array(node.style.length).keys()].map((i) => {
      const p = node.style.item(i);
      return `${p}:${node.style.getPropertyValue(p)}`;
    });
    attrs.push(`style=${JSON.stringify(decls.sort().join(';'))}`);
  }
  attrs.sort();
  const props: string[] = [];
  if (node instanceof HTMLInputElement) {
    props.push(`.value=${JSON.stringify(node.value)}`, `.checked=${node.checked}`, `.indeterminate=${node.indeterminate}`, `.disabled=${node.disabled}`);
  }
  if (node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) props.push(`.value=${JSON.stringify(node.value)}`);
  if (node instanceof HTMLElement) props.push(`.hidden=${node.hidden}`);
  if (node === document.activeElement) props.push('FOCUSED');
  out.push(`<${node.tagName.toLowerCase()} ${attrs.join(' ')} ${props.join(' ')}>`);
  node.childNodes.forEach((c) => canon(c, ids, out));
  out.push(`</${node.tagName.toLowerCase()}>`);
}

export interface Run {
  snapshots: string[][];
  log: unknown[];
  warnings: string[];
}

export async function run(c: Case, M: Mona): Promise<Run> {
  const ids = new Map<string, string>();
  const snapshots: string[][] = [];
  const log = makeLog();
  const warnings: string[] = [];
  const spies = (['error', 'warn'] as const).map((k) =>
    vi.spyOn(console, k).mockImplementation((...args: unknown[]) => void warnings.push(`${k}: ${String(args[0]).split('\n')[0]}`)),
  );
  const snap = () => {
    const out: string[] = [];
    canon(document.body, ids, out);
    snapshots.push(out);
  };
  try {
    render(c.ui(M, log));
    snap();
    if (c.steps) {
      const user = userEvent.setup();
      await c.steps({ user, screen, within, fireEvent, log, snap });
      snap();
    }
  } finally {
    cleanup();
    spies.forEach((s) => s.mockRestore());
  }
  return { snapshots, log: log.entries, warnings };
}

export function combos<T extends Record<string, readonly unknown[]>>(axes: T): Array<{ [K in keyof T]: T[K][number] }> {
  let acc: Array<Record<string, unknown>> = [{}];
  for (const [k, vals] of Object.entries(axes)) acc = acc.flatMap((a) => vals.map((v) => ({ ...a, [k]: v })));
  return acc as Array<{ [K in keyof T]: T[K][number] }>;
}

export function label(props: Record<string, unknown>): string {
  return Object.entries(props)
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' ');
}

function bind(v: unknown, key: string, log: Log): unknown {
  if (v === '$fn') return log.fn(key);
  if (v && typeof v === 'object' && Object.getPrototypeOf(v) === Object.prototype) {
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, bind(x, k, log)]));
  }
  return v;
}

export function simple(name: string, comp: string, props: Record<string, unknown>, steps?: Case['steps']): Case {
  return {
    name,
    ui: (M, log) => {
      const C = M[comp] as ComponentType<any>;
      const p = Object.fromEntries(Object.entries(props).map(([k, v]) => [k, bind(v, k, log)]));
      return <C {...p} />;
    },
    steps,
  };
}
