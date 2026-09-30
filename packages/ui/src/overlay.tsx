import {
  Children,
  cloneElement,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactElement,
  type RefObject,
} from 'react';
import { Button } from './button';
import { CLOSE } from './i18n';
import { Icon } from './icon';
import { MonaAvatar } from './avatar';
import type { DialogProps, DrawerProps, ToastProps, ToastStackProps, TooltipProps, Tone } from './types';
import { cx, pick } from './util';

const TOAST_ICON = { neutral: 'info', info: 'info', success: 'circle-check', warning: 'alert', danger: 'alert' } as const satisfies Record<Tone, string>;

export function Toast(props: ToastProps) {
  const tone = props.tone || 'neutral';
  const lang = props.lang || 'en';
  return (
    <div className={cx('mona-toast', 'mona-toast--' + tone, props.className)} role={tone === 'danger' ? 'alert' : 'status'}>
      <span className="mona-toast__icon">{props.from === 'mona' ? <MonaAvatar size={20} /> : <Icon name={TOAST_ICON[tone]} size={20} />}</span>
      <div className="mona-toast__text">
        <div className="mona-toast__title">{props.title}</div>
        {props.message ? <div className="mona-toast__msg">{props.message}</div> : null}
      </div>
      {props.action ? (
        <Button variant="ghost" size="sm" className="mona-toast__action" icon={props.action.icon} onClick={props.action.onClick}>
          {props.action.label}
        </Button>
      ) : null}
      {props.onClose ? (
        <button type="button" className="mona-toast__close" aria-label={pick(CLOSE, lang)} onClick={props.onClose}>
          <Icon name="x" size={18} />
        </button>
      ) : null}
    </div>
  );
}

export function ToastStack(props: ToastStackProps) {
  return (
    <div className={cx('mona-toasts', props.inline && 'mona-toasts--inline')} aria-live="polite">
      {props.children}
    </div>
  );
}

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function useModal(open: boolean, onClose: (() => void) | undefined, ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const first = el && ((el.querySelector('[data-autofocus]') as HTMLElement | null) || (el.querySelector(FOCUSABLE) as HTMLElement | null));
    if (first) first.focus();
    else if (el) el.focus();
    function key(e: KeyboardEvent) {
      if (e.key === 'Escape' && onClose) {
        e.stopPropagation();
        onClose();
      }
      if (e.key === 'Tab' && el) {
        const f = el.querySelectorAll<HTMLElement>(FOCUSABLE);
        const a = f[0];
        const z = f[f.length - 1];
        if (!a || !z) return;
        if (e.shiftKey && document.activeElement === a) {
          e.preventDefault();
          z.focus();
        } else if (!e.shiftKey && document.activeElement === z) {
          e.preventDefault();
          a.focus();
        }
      }
    }
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      if (prev && prev.focus) prev.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
}

export function Dialog(props: DialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const lang = props.lang || 'en';
  useModal(props.open, props.onClose, ref);
  if (!props.open) return null;
  return (
    <div
      className="mona-scrim"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && props.onClose && !props.persistent) props.onClose();
      }}
    >
      <div
        ref={ref}
        className={cx('mona-dialog', props.size === 'wide' && 'mona-dialog--wide', props.className)}
        role={props.tone === 'danger' ? 'alertdialog' : 'dialog'}
        aria-modal
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="mona-dialog__head">
          <h2 className="mona-dialog__title" id={titleId}>
            {props.title}
          </h2>
          {props.onClose ? (
            <button type="button" className="mona-dialog__close" aria-label={pick(CLOSE, lang)} onClick={props.onClose}>
              <Icon name="x" size={20} />
            </button>
          ) : null}
        </div>
        <div className="mona-dialog__body">{props.children}</div>
        {props.footer ? <div className="mona-dialog__foot">{props.footer}</div> : null}
      </div>
    </div>
  );
}

export function Drawer(props: DrawerProps) {
  const ref = useRef<HTMLElement>(null);
  const titleId = useId();
  const lang = props.lang || 'en';
  const bottom = props.side === 'bottom';
  useModal(props.open, props.onClose, ref);
  if (!props.open) return null;
  return (
    <div
      className={cx('mona-scrim', 'mona-scrim--drawer', bottom && 'mona-scrim--bottom')}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && props.onClose) props.onClose();
      }}
    >
      <aside
        ref={ref}
        className={cx('mona-drawer', bottom && 'mona-drawer--bottom', props.className)}
        role="dialog"
        aria-modal
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="mona-dialog__head">
          <h2 className="mona-dialog__title" id={titleId}>
            {props.title}
          </h2>
          {props.onClose ? (
            <button type="button" className="mona-dialog__close" aria-label={pick(CLOSE, lang)} onClick={props.onClose}>
              <Icon name="x" size={20} />
            </button>
          ) : null}
        </div>
        <div className="mona-drawer__body">{props.children}</div>
        {props.footer ? <div className="mona-drawer__foot">{props.footer}</div> : null}
      </aside>
    </div>
  );
}

export function Tooltip(props: TooltipProps) {
  const [open, setOpen] = useState(!!props.defaultOpen);
  const id = useId();
  const child = Children.only(props.children) as ReactElement<Record<string, unknown>>;
  const trigger = cloneElement(child, {
    'aria-describedby': open ? id : undefined,
    onMouseEnter: () => setOpen(true),
    onMouseLeave: () => {
      if (!props.defaultOpen) setOpen(false);
    },
    onFocus: () => setOpen(true),
    onBlur: () => {
      if (!props.defaultOpen) setOpen(false);
    },
    onKeyDown: (e: ReactKeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    },
  });
  return (
    <span className="mona-tip">
      {trigger}
      {open ? (
        <span className={cx('mona-tip__bubble', props.side === 'bottom' && 'mona-tip__bubble--bottom')} role="tooltip" id={id}>
          {props.content}
        </span>
      ) : null}
    </span>
  );
}
