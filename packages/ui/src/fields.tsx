import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { Icon } from './icon';
import { format } from './format';
import { ui } from './i18n';
import { Tag } from './tag';
import type {
  CheckboxProps,
  ComboboxOption,
  ComboboxProps,
  FileInputProps,
  FormFieldProps,
  InputProps,
  RadioGroupProps,
  SearchFieldProps,
  SelectProps,
  SwitchProps,
  TextareaProps,
} from './types';
import { cx } from './util';

interface FieldShell {
  id: string;
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  optional?: string;
  className?: string;
}

function renderField(props: FieldShell, control: (describedBy?: string) => ReactNode) {
  const hintId = props.id + '-hint';
  return (
    <div className={cx('mona-field', props.error && 'mona-field--error', props.className)}>
      {props.label ? (
        <label className="mona-field__label" htmlFor={props.id}>
          {props.label}
          {props.optional ? <span className="mona-field__opt">{' · ' + props.optional}</span> : null}
        </label>
      ) : null}
      {control(props.error || props.hint ? hintId : undefined)}
      {props.error ? (
        <div className="mona-field__hint" id={hintId}>
          <Icon name="alert" size={16} label={undefined} />
          <span>{props.error}</span>
        </div>
      ) : props.hint ? (
        <div className="mona-field__hint" id={hintId}>
          {props.hint}
        </div>
      ) : null}
    </div>
  );
}

export function Input(props: InputProps) {
  const autoId = useId();
  const id = props.id || autoId;
  const { label: _label, hint: _hint, error, optional: _optional, icon, className: _className, id: _id, ...rest } = props;
  return renderField({ ...props, id }, (describedBy) => (
    <div className="mona-field__wrap">
      {icon ? (
        <span className="mona-field__lead">
          <Icon name={icon} size={18} />
        </span>
      ) : null}
      <input
        type="text"
        {...rest}
        id={id}
        className={cx('mona-field__control', icon && 'mona-field__control--with-lead')}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      />
    </div>
  ));
}

export function Select(props: SelectProps) {
  const autoId = useId();
  const id = props.id || autoId;
  const { label: _label, hint: _hint, error, optional: _optional, options, placeholder, className: _className, id: _id, ...rest } = props;
  return renderField({ ...props, id }, (describedBy) => (
    <div className="mona-field__wrap">
      <select {...rest} id={id} className="mona-field__control" aria-invalid={error ? true : undefined} aria-describedby={describedBy}>
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {(options || []).map((o) =>
          'options' in o ? (
            <optgroup key={o.label} label={o.label}>
              {o.options.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </optgroup>
          ) : (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ),
        )}
      </select>
      <span className="mona-field__chev">
        <Icon name="chevron-down" size={18} />
      </span>
    </div>
  ));
}

export function FormField(props: FormFieldProps) {
  const autoId = useId();
  const id = props.id || autoId;
  const hintId = id + '-hint';
  const described = props.error || props.hint ? hintId : undefined;
  const child = props.children;
  const invalid = props.error ? true : undefined;
  const control =
    typeof child === 'function'
      ? child({ id, 'aria-describedby': described, 'aria-invalid': invalid })
      : isValidElement<{ id?: string }>(child)
        ? cloneElement(child, { id: child.props.id || id, 'aria-describedby': described, 'aria-invalid': invalid } as Record<string, unknown>)
        : child;
  const opt = props.optional === true ? ui(props.lang, 'optional') : props.optional;
  return (
    <div className={cx('mona-field', props.error && 'mona-field--error', props.className)}>
      {props.label ? (
        <label className="mona-field__label" htmlFor={id}>
          {props.label}
          {opt ? <span className="mona-field__opt">{' · ' + opt}</span> : null}
        </label>
      ) : null}
      {control}
      {props.error ? (
        <div className="mona-field__hint" id={hintId}>
          <Icon name="alert" size={16} />
          <span>{props.error}</span>
        </div>
      ) : props.hint ? (
        <div className="mona-field__hint" id={hintId}>
          {props.hint}
        </div>
      ) : null}
    </div>
  );
}

export function Checkbox(props: CheckboxProps) {
  const autoId = useId();
  const id = props.id || autoId;
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = !!props.indeterminate;
  }, [props.indeterminate]);
  const { label, description, indeterminate: _indeterminate, error, className, id: _id, ...rest } = props;
  return (
    <div className={cx('mona-check', error && 'mona-check--error', props.disabled && 'mona-check--disabled', className)}>
      <span className="mona-check__box-wrap">
        <input
          type="checkbox"
          {...rest}
          id={id}
          ref={ref}
          className="mona-check__input"
          aria-describedby={description ? id + '-d' : undefined}
          aria-invalid={error ? true : undefined}
        />
        <span className="mona-check__box" aria-hidden>
          <svg className="mona-check__tick" viewBox="0 0 16 16" width={14} height={14}>
            <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <svg className="mona-check__dash" viewBox="0 0 16 16" width={14} height={14}>
            <path d="M4 8h8" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" />
          </svg>
        </span>
      </span>
      {label ? (
        <span className="mona-check__text">
          <label htmlFor={id} className="mona-check__label">
            {label}
          </label>
          {description ? (
            <span className="mona-check__desc" id={id + '-d'}>
              {description}
            </span>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}

export function RadioGroup(props: RadioGroupProps) {
  const name = useId();
  const controlled = props.value !== undefined;
  const [inner, setInner] = useState(props.defaultValue);
  const value = controlled ? props.value : inner;
  function set(v: string) {
    if (!controlled) setInner(v);
    if (props.onChange) props.onChange(v);
  }
  const cards = props.variant === 'cards';
  return (
    <fieldset
      className={cx('mona-radios', cards && 'mona-radios--cards', props.orientation === 'horizontal' && 'mona-radios--row', props.error && 'mona-radios--error', props.className)}
    >
      {props.legend ? <legend className="mona-field__label">{props.legend}</legend> : null}
      <div className="mona-radios__list">
        {(props.options || []).map((o) => {
          const id = name + '-' + o.value;
          const on = value === o.value;
          return (
            <label key={o.value} htmlFor={id} className={cx('mona-radio', on && 'mona-radio--on', o.disabled && 'mona-check--disabled')}>
              <input
                type="radio"
                id={id}
                name={props.name || name}
                value={o.value}
                checked={on}
                disabled={o.disabled}
                className="mona-radio__input"
                onChange={() => set(o.value)}
              />
              <span className="mona-radio__dot" aria-hidden />
              <span className="mona-check__text">
                <span className="mona-check__label">{o.label}</span>
                {o.description ? <span className="mona-check__desc">{o.description}</span> : null}
              </span>
              {cards && o.meta ? <span className="mona-radio__meta">{o.meta}</span> : null}
            </label>
          );
        })}
      </div>
      {props.error ? (
        <div className="mona-field__hint">
          <Icon name="alert" size={16} />
          <span>{props.error}</span>
        </div>
      ) : props.hint ? (
        <div className="mona-field__hint">{props.hint}</div>
      ) : null}
    </fieldset>
  );
}

export function Switch(props: SwitchProps) {
  const autoId = useId();
  const id = props.id || autoId;
  const controlled = props.checked !== undefined;
  const [inner, setInner] = useState(!!props.defaultChecked);
  const on = controlled ? !!props.checked : inner;
  function toggle() {
    if (props.disabled) return;
    if (!controlled) setInner(!on);
    if (props.onChange) props.onChange(!on);
  }
  return (
    <div className={cx('mona-switch', props.disabled && 'mona-check--disabled', props.className)}>
      <span className="mona-check__text">
        <label htmlFor={id} className="mona-check__label">
          {props.label}
        </label>
        {props.description ? (
          <span className="mona-check__desc" id={id + '-d'}>
            {props.description}
          </span>
        ) : null}
      </span>
      <button
        type="button"
        role="switch"
        id={id}
        aria-checked={on}
        disabled={props.disabled}
        aria-describedby={props.description ? id + '-d' : undefined}
        className="mona-switch__track"
        onClick={toggle}
      >
        <span className="mona-switch__thumb">{on ? <Icon name="check" size={12} strokeWidth={3} /> : null}</span>
      </button>
    </div>
  );
}

export function Textarea(props: TextareaProps) {
  const lang = props.lang || 'en';
  const ref = useRef<HTMLTextAreaElement>(null);
  const controlled = props.value !== undefined;
  const [inner, setInner] = useState<TextareaProps['value']>(props.defaultValue || '');
  const val = controlled ? props.value : inner;
  useEffect(() => {
    if (props.autoResize && ref.current) {
      ref.current.style.height = 'auto';
      ref.current.style.height = ref.current.scrollHeight + 'px';
    }
  }, [val, props.autoResize]);
  const {
    label: _label,
    hint: _hint,
    error: _error,
    optional: _optional,
    autoResize: _autoResize,
    className: _className,
    lang: _lang,
    value: _value,
    defaultValue: _defaultValue,
    onChange: _onChange,
    showCount: _showCount,
    ...rest
  } = props;
  const count =
    props.maxLength && props.showCount !== false
      ? format.number(String(val).length, lang) + ' / ' + format.number(props.maxLength, lang)
      : null;
  return (
    <FormField
      label={props.label}
      error={props.error}
      optional={props.optional}
      lang={lang}
      id={props.id}
      className={props.className}
      hint={
        count ? (
          <span className="mona-field__hint-row">
            <span>{props.hint}</span>
            <span className="mona-num" aria-live="polite">
              {count}
            </span>
          </span>
        ) : (
          props.hint
        )
      }
    >
      <textarea
        rows={4}
        {...rest}
        ref={ref}
        value={val}
        className="mona-field__control mona-field__control--area"
        onChange={(e) => {
          if (!controlled) setInner(e.target.value);
          if (props.onChange) props.onChange(e);
        }}
      />
    </FormField>
  );
}

export function SearchField(props: SearchFieldProps) {
  const lang = props.lang || 'en';
  const ref = useRef<HTMLInputElement>(null);
  const controlled = props.value !== undefined;
  const [inner, setInner] = useState(props.defaultValue || '');
  const val = controlled ? (props.value as string) : inner;
  function set(v: string) {
    if (!controlled) setInner(v);
    if (props.onChange) props.onChange(v);
  }
  const label = props.label || ui(lang, 'search');
  return (
    <div className={cx('mona-search', props.size === 'sm' && 'mona-search--sm', props.className)} role="search">
      <span className="mona-field__lead">
        <Icon name="search" size={18} />
      </span>
      <input
        ref={ref}
        type="search"
        className="mona-field__control mona-field__control--with-lead mona-search__input"
        aria-label={label}
        placeholder={props.placeholder || label}
        value={val}
        onChange={(e) => set(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && props.onSearch) props.onSearch(val);
          if (e.key === 'Escape' && val) {
            e.preventDefault();
            set('');
          }
        }}
      />
      {val ? (
        <button
          type="button"
          className="mona-search__clear"
          aria-label={ui(lang, 'clear')}
          onClick={() => {
            set('');
            if (ref.current) ref.current.focus();
          }}
        >
          <Icon name="x" size={16} />
        </button>
      ) : null}
    </div>
  );
}

function norm(s: string): string {
  return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

export function Combobox(props: ComboboxProps) {
  const lang = props.lang || 'en';
  const autoId = useId();
  const id = props.id || autoId;
  const listId = id + '-list';
  const multiple = !!props.multiple;
  const controlled = props.value !== undefined;
  const [inner, setInner] = useState<string | string[] | null>(props.defaultValue != null ? props.defaultValue : multiple ? [] : null);
  const value = controlled ? (props.value as string | string[] | null) : inner;
  const selected = multiple ? (value as string[]) : [];
  function setValue(v: string | string[] | null) {
    if (!controlled) setInner(v);
    if (props.onChange) props.onChange(v);
  }
  const opts = props.options || [];
  const byVal: Record<string, ComboboxOption | undefined> = {};
  opts.forEach((o) => {
    byVal[o.value] = o;
  });
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const current = !multiple && value != null ? byVal[value as string] : undefined;
  const shown = !multiple && !open && current ? current.label : query;
  const filtered = opts.filter((op) => !query || norm(op.label + ' ' + (op.group || '') + ' ' + (op.description || '')).indexOf(norm(query)) >= 0);
  useEffect(() => {
    function down(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', down);
    return () => document.removeEventListener('mousedown', down);
  }, []);
  function isSel(v: string) {
    return multiple ? selected.indexOf(v) >= 0 : value === v;
  }
  function choose(op: ComboboxOption | undefined) {
    if (!op || op.disabled) return;
    if (multiple) {
      setValue(isSel(op.value) ? selected.filter((v) => v !== op.value) : selected.concat([op.value]));
      setQuery('');
    } else {
      setValue(op.value);
      setQuery('');
      setOpen(false);
    }
  }
  function onKey(e: ReactKeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive(Math.min(active + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(Math.max(active - 1, 0));
    } else if (e.key === 'Enter' && open) {
      e.preventDefault();
      choose(filtered[active]);
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault();
        setOpen(false);
        setQuery('');
      }
    } else if (e.key === 'Backspace' && multiple && !query && selected.length) setValue(selected.slice(0, -1));
  }
  const describedBy = props.label && (props.error || props.hint) ? id + '-hint' : props['aria-describedby'];
  const activeOption = filtered[active];
  let lastGroup: string | null = null;
  const rows: ReactNode[] = [];
  filtered.forEach((op, i) => {
    if (op.group && op.group !== lastGroup) {
      lastGroup = op.group;
      rows.push(
        <li key={'g' + op.group} role="presentation" className="mona-menu__label">
          {op.group}
        </li>,
      );
    }
    rows.push(
      <li
        key={op.value}
        id={listId + '-' + i}
        role="option"
        aria-selected={isSel(op.value)}
        aria-disabled={op.disabled || undefined}
        className={cx('mona-combo__opt', i === active && 'mona-combo__opt--active')}
        onMouseDown={(e) => {
          e.preventDefault();
          choose(op);
        }}
        onMouseEnter={() => setActive(i)}
      >
        <span className="mona-combo__check">{isSel(op.value) ? <Icon name="check" size={16} strokeWidth={2.6} /> : null}</span>
        <span className="mona-combo__text">
          <span>{op.label}</span>
          {op.description ? <span className="mona-check__desc">{op.description}</span> : null}
        </span>
      </li>,
    );
  });
  const control = (
    <div ref={wrapRef} className={cx('mona-combo', open && 'mona-combo--open', !props.label && props.className)}>
      <div
        className={cx('mona-field__control', 'mona-combo__box')}
        onClick={() => {
          if (inputRef.current) inputRef.current.focus();
          setOpen(true);
        }}
      >
        {multiple
          ? selected.map((v) => {
              const o = byVal[v];
              return o ? (
                <Tag key={v} size="sm" lang={lang} onRemove={() => setValue(selected.filter((x) => x !== v))}>
                  {o.label}
                </Tag>
              ) : null;
            })
          : null}
        <input
          ref={inputRef}
          id={id}
          className="mona-combo__input"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && activeOption ? listId + '-' + active : undefined}
          aria-describedby={describedBy}
          aria-invalid={props.error ? true : undefined}
          aria-label={props.label ? undefined : props['aria-label']}
          placeholder={multiple && selected.length ? '' : props.placeholder}
          value={shown}
          disabled={props.disabled}
          autoComplete="off"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
        />
        <span className="mona-field__chev">
          <Icon name="chevron-down" size={18} />
        </span>
      </div>
      {open ? (
        <ul id={listId} role="listbox" aria-multiselectable={multiple || undefined} className="mona-combo__list">
          {filtered.length ? (
            rows
          ) : (
            <li className="mona-combo__empty" role="presentation">
              {props.emptyText || ui(lang, 'noMatch')}
            </li>
          )}
        </ul>
      ) : null}
    </div>
  );
  if (!props.label) return control;
  return (
    <FormField id={id} label={props.label} hint={props.hint} error={props.error} optional={props.optional} lang={lang} className={props.className}>
      {() => control}
    </FormField>
  );
}

export function FileInput(props: FileInputProps) {
  const lang = props.lang || 'en';
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  function take(list: ArrayLike<File> | null | undefined) {
    const arr = Array.prototype.slice.call(list || []) as File[];
    const next = props.multiple ? files.concat(arr) : arr.slice(0, 1);
    setFiles(next);
    if (props.onFiles) props.onFiles(next);
  }
  function removeAt(i: number) {
    const next = files.filter((_, j) => j !== i);
    setFiles(next);
    if (props.onFiles) props.onFiles(next);
  }
  return (
    <FormField id={id} label={props.label} hint={props.hint} error={props.error} optional={props.optional} lang={lang} className={props.className}>
      <div className="mona-file">
        <label
          htmlFor={id}
          className={cx('mona-file__drop', drag && 'mona-file__drop--over')}
          onDragOver={(e: DragEvent) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e: DragEvent) => {
            e.preventDefault();
            setDrag(false);
            take(e.dataTransfer.files);
          }}
        >
          <Icon name="file" size={24} />
          <span>
            {ui(lang, 'drop') + ' '}
            <span className="mona-file__choose">{ui(lang, 'choose')}</span>
          </span>
          {props.accept ? <span className="mona-check__desc">{props.acceptLabel || props.accept}</span> : null}
          <input
            ref={inputRef}
            id={id}
            type="file"
            className="mona-sr"
            accept={props.accept}
            multiple={props.multiple}
            onChange={(e) => {
              take(e.target.files);
              e.target.value = '';
            }}
          />
        </label>
        {files.length ? (
          <ul className="mona-file__list">
            {files.map((file, i) => (
              <li key={i + file.name}>
                <Icon name="file" size={16} />
                <span className="mona-file__name">{file.name}</span>
                <span className="mona-sources__detail">{format.fileSize(file.size, lang)}</span>
                <button type="button" className="mona-toast__close" aria-label={ui(lang, 'remove') + ' ' + file.name} onClick={() => removeAt(i)}>
                  <Icon name="x" size={16} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </FormField>
  );
}

