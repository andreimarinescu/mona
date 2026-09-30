import {
  cloneElement,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactElement,
  type RefObject,
} from 'react';
import { Icon } from './icon';
import type { MenuProps, Placement, PopoverProps } from './types';
import { cx } from './util';

interface Position {
  top: number;
  left: number;
  minWidth: number | undefined;
}

function usePosition(open: boolean, triggerRef: RefObject<HTMLElement | null>, panelRef: RefObject<HTMLElement | null>, placement?: Placement) {
  const [pos, setPos] = useState<Position | null>(null);
  useEffect(() => {
    if (!open) return;
    const matchWidth = panelRef.current?.dataset.matchWidth === 'true';
    function place() {
      const t = triggerRef.current;
      const p = panelRef.current;
      if (!t || !p) return;
      const r = t.getBoundingClientRect();
      const pw = p.offsetWidth;
      const ph = p.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const gap = 6;
      let top = (placement || '').indexOf('top') === 0 ? r.top - ph - gap : r.bottom + gap;
      if (top + ph > vh - 8 && r.top - ph - gap > 8) top = r.top - ph - gap;
      if (top < 8 && r.bottom + gap + ph < vh) top = r.bottom + gap;
      let left = /end$/.test(placement || '') ? r.right - pw : r.left;
      left = Math.max(8, Math.min(left, vw - pw - 8));
      setPos({ top: Math.round(top), left: Math.round(left), minWidth: matchWidth ? r.width : undefined });
    }
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  return pos;
}

function PopoverBase(props: PopoverProps & { role?: 'menu' }) {
  const controlled = props.open !== undefined;
  const [inner, setInner] = useState(false);
  const open = controlled ? !!props.open : inner;
  function setOpen(v: boolean) {
    if (!controlled) setInner(v);
    if (props.onOpenChange) props.onOpenChange(v);
  }
  const tRef = useRef<HTMLSpanElement>(null);
  const pRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const pos = usePosition(open, tRef, pRef, props.placement);
  useEffect(() => {
    if (!open) return;
    function down(e: MouseEvent) {
      const target = e.target as Node;
      if (pRef.current && !pRef.current.contains(target) && tRef.current && !tRef.current.contains(target)) setOpen(false);
    }
    function key(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
        const b = tRef.current && (tRef.current.querySelector('button,[tabindex],a,input') as HTMLElement | null);
        const el = b || tRef.current;
        if (el) el.focus();
      }
    }
    document.addEventListener('mousedown', down);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('mousedown', down);
      document.removeEventListener('keydown', key);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const trigger =
    typeof props.trigger === 'function'
      ? props.trigger({ open, toggle: () => setOpen(!open), id })
      : cloneElement(props.trigger as ReactElement<Record<string, unknown>>, {
          'aria-expanded': open,
          'aria-controls': id,
          'aria-haspopup': props.role === 'menu' ? 'menu' : 'dialog',
          onClick: () => setOpen(!open),
        });
  return (
    <span className="mona-pop" ref={tRef}>
      {trigger}
      {open ? (
        <div
          ref={pRef}
          id={id}
          role={props.role === 'menu' ? undefined : 'dialog'}
          aria-label={props.label}
          className={cx('mona-pop__panel', props.className)}
          data-match-width={props.matchWidth ? 'true' : undefined}
          style={{ top: pos ? pos.top : -9999, left: pos ? pos.left : -9999, minWidth: pos?.minWidth, width: props.width }}
        >
          {typeof props.children === 'function' ? props.children({ close: () => setOpen(false) }) : props.children}
        </div>
      ) : null}
    </span>
  );
}

export function Popover(props: PopoverProps) {
  return <PopoverBase {...props} />;
}

const ITEM = '[role="menuitem"]:not([aria-disabled="true"])';

function MenuList(props: { items: MenuProps['items']; label?: string; close: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const items = props.items || [];
  useEffect(() => {
    const f = ref.current && ref.current.querySelector<HTMLElement>(ITEM);
    if (f) f.focus();
  }, []);
  function onKey(e: ReactKeyboardEvent) {
    const root = ref.current;
    if (!root) return;
    const list = Array.prototype.slice.call(root.querySelectorAll(ITEM)) as HTMLElement[];
    const i = list.indexOf(document.activeElement as HTMLElement);
    let n: number | null = null;
    if (e.key === 'ArrowDown') n = (i + 1) % list.length;
    if (e.key === 'ArrowUp') n = (i - 1 + list.length) % list.length;
    if (e.key === 'Home') n = 0;
    if (e.key === 'End') n = list.length - 1;
    if (e.key === 'Tab') {
      props.close();
      return;
    }
    if (e.key.length === 1 && /\S/.test(e.key)) {
      const k = e.key.toLowerCase();
      const starts = (el: HTMLElement) => (el.textContent ?? '').trim().toLowerCase().indexOf(k) === 0;
      let j = list.findIndex((el, idx) => idx > i && starts(el));
      if (j < 0) j = list.findIndex(starts);
      if (j >= 0) n = j;
    }
    const target = n !== null ? list[n] : undefined;
    if (target) {
      e.preventDefault();
      target.focus();
    }
  }
  return (
    <div ref={ref} role="menu" aria-label={props.label} className="mona-menu" onKeyDown={onKey}>
      {items.map((it, i) => {
        if ('type' in it && it.type === 'separator') return <div key={'s' + i} role="separator" className="mona-menu__sep" />;
        if ('type' in it && it.type === 'label') {
          return (
            <div key={'l' + i} className="mona-menu__label" role="presentation">
              {it.label}
            </div>
          );
        }
        const item = it as Extract<MenuProps['items'][number], { id: string }>;
        return (
          <div
            key={item.id || i}
            role="menuitem"
            tabIndex={-1}
            aria-disabled={item.disabled ? true : undefined}
            className={cx('mona-menu__item', item.danger && 'mona-menu__item--danger')}
            onClick={() => {
              if (item.disabled) return;
              props.close();
              if (item.onSelect) item.onSelect(item.id);
            }}
            onKeyDown={(e) => {
              if ((e.key === 'Enter' || e.key === ' ') && !item.disabled) {
                e.preventDefault();
                props.close();
                if (item.onSelect) item.onSelect(item.id);
              }
            }}
          >
            {item.icon ? <Icon name={item.icon} size={16} /> : <span className="mona-menu__noicon" />}
            <span className="mona-menu__text">{item.label}</span>
            {item.shortcut ? <kbd className="mona-kbd">{item.shortcut}</kbd> : null}
          </div>
        );
      })}
    </div>
  );
}

export function Menu(props: MenuProps) {
  return (
    <PopoverBase role="menu" placement={props.placement || 'bottom-start'} trigger={props.trigger} open={props.open} onOpenChange={props.onOpenChange}>
      {(api) => <MenuList items={props.items} label={props.label} close={api.close} />}
    </PopoverBase>
  );
}
