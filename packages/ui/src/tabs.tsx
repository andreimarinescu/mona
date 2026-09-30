import { useRef, useState, type KeyboardEvent } from 'react';
import type { TabsProps } from './types';
import { cx } from './util';

export function Tabs(props: TabsProps) {
  const tabs = props.tabs || [];
  const controlled = props.value !== undefined;
  const [inner, setInner] = useState(props.defaultValue || tabs[0]?.id);
  const value = controlled ? props.value : inner;
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function select(id: string) {
    if (!controlled) setInner(id);
    if (props.onChange) props.onChange(id);
  }

  function onKey(e: KeyboardEvent) {
    const i = tabs.findIndex((t) => t.id === value);
    let n: number | null = null;
    if (e.key === 'ArrowRight') n = (i + 1) % tabs.length;
    if (e.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length;
    if (e.key === 'Home') n = 0;
    if (e.key === 'End') n = tabs.length - 1;
    const target = n !== null ? tabs[n] : undefined;
    if (target) {
      e.preventDefault();
      select(target.id);
      refs.current[target.id]?.focus();
    }
  }

  return (
    <div className={cx('mona-tabs', props.className)} role="tablist" aria-label={props.label} onKeyDown={onKey}>
      {tabs.map((t) => {
        const on = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={'tab-' + t.id}
            aria-selected={on}
            aria-controls={t.panelId}
            tabIndex={on ? 0 : -1}
            className="mona-tab"
            onClick={() => select(t.id)}
          >
            {t.label}
            {t.count != null ? <span className="mona-tab__count">{t.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
