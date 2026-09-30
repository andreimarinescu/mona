import { Button, Checkbox, Icon, format } from '@mona/ui';
import { useId, useRef, useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { MAX_FILES, MAX_FILE_BYTES } from '../../data/intake';
import { useLang } from '../../shell/useLang';

export interface DropZoneProps {
  disabled?: boolean;
  visitor: boolean;
  onVisitorChange(value: boolean): void;
  onFiles(files: File[]): void;
}

export function DropZone({ disabled, visitor, onVisitorChange, onFiles }: DropZoneProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const input = useRef<HTMLInputElement>(null);
  const hint = useId();
  const [over, setOver] = useState(false);
  const depth = useRef(0);

  function accept(list: FileList | null) {
    const files = list ? Array.from(list) : [];
    if (files.length > 0) onFiles(files);
    if (input.current) input.current.value = '';
  }
  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files');

  return (
    <section
      aria-label={t('intake.drop.region')}
      data-drag-over={over ? '' : undefined}
      className={`flex flex-col gap-4 rounded-xl border-2 border-dashed p-6 transition-colors lg:p-8 ${over ? 'border-accent bg-accent-soft' : 'border-border-strong bg-surface'}`}
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        if (!disabled) accept(e.dataTransfer.files);
      }}
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
        <span aria-hidden className="inline-flex size-[72px] shrink-0 items-center justify-center rounded-t-[36px] rounded-b-lg bg-surface-sunken text-text-muted">
          <Icon name="upload" size={32} />
        </span>
        <div className="flex min-w-[220px] flex-1 flex-col gap-1">
          <h2 className="m-0 text-text [font:var(--type-title)]">{over ? t('intake.drop.over') : t('intake.drop.title')}</h2>
          <p className="m-0 text-text-muted" id={hint}>
            {t('intake.drop.hint', { size: format.fileSize(MAX_FILE_BYTES, lang), count: MAX_FILES, n: format.number(MAX_FILES, lang) })}
          </p>
        </div>
        <Button variant="secondary" disabled={disabled} aria-describedby={hint} onClick={() => input.current?.click()}>
          {t('intake.drop.choose')}
        </Button>
        <input ref={input} type="file" multiple hidden tabIndex={-1} aria-hidden data-testid="file-input" onChange={(e) => accept(e.target.files)} />
      </div>
      <Checkbox label={t('intake.visitor.label')} description={t('intake.visitor.hint')} checked={visitor} onChange={(e) => onVisitorChange(e.target.checked)} />
    </section>
  );
}
