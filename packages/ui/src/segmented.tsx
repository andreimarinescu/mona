import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Icon } from './icon';
import { LANGS, THEME_LABELS } from './i18n';
import type { LanguageSwitchProps, SegmentedControlProps, ThemeToggleProps } from './types';
import { cx, pick } from './util';

interface SegOption {
  id: string;
  lang?: string;
  aria?: string;
  title?: string;
  content: ReactNode;
}

interface SegmentedProps {
  label?: string;
  value?: string;
  onChange?: (id: string) => void;
  icons?: boolean;
  className?: string;
  options: SegOption[];
}

function Segmented(props: SegmentedProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const opts = props.options;
  function onKey(e: KeyboardEvent) {
    const i = opts.findIndex((o) => o.id === props.value);
    let n: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') n = (i + 1) % opts.length;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') n = (i - 1 + opts.length) % opts.length;
    const target = n !== null ? opts[n] : undefined;
    if (target) {
      e.preventDefault();
      if (props.onChange) props.onChange(target.id);
      refs.current[target.id]?.focus();
    }
  }
  return (
    <div className={cx('mona-seg', props.icons && 'mona-seg--icons', props.className)} role="radiogroup" aria-label={props.label} onKeyDown={onKey}>
      {opts.map((o) => {
        const on = o.id === props.value;
        return (
          <button
            key={o.id}
            ref={(el) => {
              refs.current[o.id] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            className="mona-seg__opt"
            lang={o.lang}
            aria-label={o.aria}
            title={o.title}
            onClick={() => {
              if (props.onChange) props.onChange(o.id);
            }}
          >
            {o.content}
          </button>
        );
      })}
    </div>
  );
}

export function LanguageSwitch(props: LanguageSwitchProps) {
  const [inner, setInner] = useState(props.defaultValue || 'en');
  const value = props.value !== undefined ? props.value : inner;
  const set = (v: string) => {
    setInner(v as typeof inner);
    if (props.onChange) props.onChange(v as typeof inner);
  };
  return (
    <Segmented
      label={props.label || 'Language · Langue · Limbă'}
      value={value}
      onChange={set}
      className={props.className}
      options={LANGS.map((l) => ({ id: l.id, lang: l.id, aria: l.name, title: l.name, content: l.short }))}
    />
  );
}

type ThemeId = 'light' | 'dark' | 'system';
const THEME_OPTIONS: Array<{ id: ThemeId; icon: 'sun' | 'moon' | 'monitor' }> = [
  { id: 'light', icon: 'sun' },
  { id: 'dark', icon: 'moon' },
];
const THEME_SYSTEM: { id: ThemeId; icon: 'sun' | 'moon' | 'monitor' } = { id: 'system', icon: 'monitor' };

export function ThemeToggle(props: ThemeToggleProps) {
  const t = pick(THEME_LABELS, props.lang);
  const [inner, setInner] = useState<ThemeId>(props.defaultValue || 'system');
  const value = props.value !== undefined ? props.value : inner;
  const set = (v: string) => {
    setInner(v as ThemeId);
    if (props.onChange) props.onChange(v as ThemeId);
  };
  const opts = props.system !== false ? [...THEME_OPTIONS, THEME_SYSTEM] : THEME_OPTIONS;
  return (
    <Segmented
      label={t.group}
      value={value}
      onChange={set}
      icons={!props.showLabels}
      className={props.className}
      options={opts.map((o) => ({
        id: o.id,
        aria: t[o.id],
        title: t[o.id],
        content: [<Icon key="i" name={o.icon} size={16} />, props.showLabels ? <span key="l">{t[o.id]}</span> : null],
      }))}
    />
  );
}

export function SegmentedControl(props: SegmentedControlProps) {
  const controlled = props.value !== undefined;
  const [inner, setInner] = useState(props.defaultValue || props.options[0]?.value);
  const value = controlled ? props.value : inner;
  return (
    <Segmented
      label={props.label}
      value={value}
      className={props.className}
      icons={props.iconOnly}
      onChange={(v) => {
        if (!controlled) setInner(v);
        if (props.onChange) props.onChange(v);
      }}
      options={props.options.map((o) => ({
        id: o.value,
        aria: props.iconOnly ? o.label : undefined,
        title: props.iconOnly ? o.label : undefined,
        content: [o.icon ? <Icon key="i" name={o.icon} size={16} /> : null, props.iconOnly ? null : <span key="l">{o.label}</span>],
      }))}
    />
  );
}
