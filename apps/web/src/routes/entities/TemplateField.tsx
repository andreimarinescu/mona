import { useId, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { TOKEN_CHIPS, parseTemplate, type TemplateKind } from '../../data/template';

export interface TemplateFieldError {
  offset: number;
  message?: string;
}

export interface TemplateFieldProps {
  kind: TemplateKind;
  label: string;
  value: string;
  onChange(value: string): void;
  error?: TemplateFieldError | null;
  /** The extension the file adds on its own; shown after the field, never typed. */
  suffix?: string;
  hint?: string;
}

const CHIP = 'inline-flex items-center rounded-full border border-dashed border-info bg-info-soft px-2.5 py-0.5 [font:var(--type-filename)] text-info';

/** Literal text plus token chips: the text is edited in the field, the chips insert tokens, and the strip below shows how it reads. */
export function TemplateField({ kind, label, value, onChange, error, suffix, hint }: TemplateFieldProps) {
  const { t } = useTranslation();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const { parts } = parseTemplate(value, kind);

  function insert(token: string) {
    const el = input.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    onChange(value.slice(0, start) + token + value.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + token.length, start + token.length);
    });
  }

  return (
    <div className="flex flex-col gap-2" data-testid={`template-field-${kind}`}>
      <label htmlFor={id} className="font-ui text-[14px] leading-5 font-semibold text-text">
        {label}
      </label>
      <div className={`flex items-center gap-2 rounded-md border bg-surface-raised px-3 ${error ? 'border-danger' : 'border-border-strong'}`}>
        <input
          ref={input}
          id={id}
          type="text"
          value={value}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={`${id}-help`}
          onChange={(e) => onChange(e.target.value)}
          className="min-h-11 min-w-0 flex-1 border-0 bg-transparent [font:var(--type-filename)] text-[14px] text-text outline-none focus:outline-none"
        />
        {suffix ? <span className="[font:var(--type-filename)] text-text-muted">{suffix}</span> : null}
      </div>
      <div id={`${id}-help`} className="flex flex-col gap-2">
        <div aria-hidden className="flex min-h-7 flex-wrap items-center gap-1 text-text-muted" data-testid="template-chips">
          {parts.map((p, i) =>
            p.kind === 'token' ? (
              <span key={i} className={CHIP} data-token={p.name}>
                {p.text}
              </span>
            ) : (
              <span key={i} className="[font:var(--type-filename)] whitespace-pre">
                {p.text}
              </span>
            ),
          )}
        </div>
        {error ? (
          <p role="alert" className="m-0 flex flex-col font-ui text-[13px] leading-[18px] text-danger" data-testid="template-error">
            <span>{t('errors.invalid_template', { offset: error.offset })}</span>
            {error.message ? <span>{error.message}</span> : null}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t('entities.categories.tokens')}>
          <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('entities.categories.tokens')}</span>
          {TOKEN_CHIPS.map((token) => (
            <button key={token} type="button" onClick={() => insert(token)} className={`${CHIP} cursor-pointer hover:bg-surface-sunken`} aria-label={t('entities.categories.insert', { token })}>
              {token}
            </button>
          ))}
        </div>
        {hint ? <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{hint}</p> : null}
      </div>
    </div>
  );
}
