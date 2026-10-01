import { Button, Icon } from '@mona/ui';
import { useLayoutEffect, useRef, type FormEvent, type KeyboardEvent, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { AttachmentChip } from './AttachmentChip';
import type { Attachment } from './types';

export const MAX_MESSAGE = 4_000;
const ACCEPT = 'application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png';

export interface PendingAttachment extends Attachment {
  key: string;
  uploading: boolean;
}

export interface ChatComposerProps {
  value: string;
  onChange(value: string): void;
  onSend(): void;
  onStop(): void;
  onFiles(files: File[]): void;
  attachments: PendingAttachment[];
  sending: boolean;
  offline: boolean;
  dragOver: boolean;
  hint: string;
  size?: 'md' | 'lg';
  inputRef?: RefObject<HTMLTextAreaElement | null>;
  autoFocus?: boolean;
}

/** HANDOFF ChatComposer: idle, typing, drag-over, sending (Stop), disabled while Mona is offline. */
export function ChatComposer({ value, onChange, onSend, onStop, onFiles, attachments, sending, offline, dragOver, hint, size = 'md', inputRef, autoFocus }: ChatComposerProps) {
  const { t } = useTranslation();
  const picker = useRef<HTMLInputElement>(null);
  const own = useRef<HTMLTextAreaElement>(null);
  const field = inputRef ?? own;
  useLayoutEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value, field]);
  const uploading = attachments.some((a) => a.uploading);
  const canSend = !offline && !sending && !uploading && value.trim().length > 0;
  const state = offline ? 'disabled' : dragOver ? 'drag-over' : sending ? 'sending' : value ? 'typing' : 'idle';

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (canSend) onSend();
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2" data-testid="chat-composer" data-state={state}>
      <div
        className={`flex flex-col gap-2 rounded-xl border bg-surface px-4 py-2 shadow-1 ${
          dragOver ? 'border-2 border-dashed border-info bg-info-soft' : offline ? 'border-border bg-surface-sunken' : 'border-border-strong focus-within:border-accent focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-focus'
        }`}
      >
        {attachments.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {attachments.map((a) => (
              <AttachmentChip key={a.key} attachment={a} uploading={a.uploading} />
            ))}
          </div>
        ) : null}
        <div className="flex items-end gap-2">
          {dragOver ? (
            <div className="flex min-h-12 flex-1 items-center gap-3 text-info" role="status">
              <Icon name="file" size={20} />
              <span className="flex flex-col">
                <span className="font-ui text-[16px] leading-6 font-semibold">{t('chat.composer.drop')}</span>
                <span className="font-ui text-[13px] leading-[18px]">{t('chat.composer.dropHint')}</span>
              </span>
            </div>
          ) : (
            <textarea
              ref={field}
              data-chat-composer
              rows={1}
              maxLength={MAX_MESSAGE}
              value={value}
              disabled={offline}
              autoFocus={autoFocus}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={onKey}
              placeholder={t('chat.composer.placeholder')}
              aria-label={t('chat.composer.placeholder')}
              style={{ outline: 'none' }}
              className={`box-border max-h-48 min-h-12 w-0 min-w-0 flex-1 resize-none border-0 bg-transparent py-3 font-ui text-text outline-none placeholder:text-text-muted disabled:cursor-not-allowed ${
                size === 'lg' ? 'text-[18px] leading-7' : 'text-[16px] leading-6'
              }`}
            />
          )}
          <input
            ref={picker}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            tabIndex={-1}
            aria-hidden
            data-testid="composer-file-input"
            onChange={(e) => {
              const files = [...(e.target.files ?? [])];
              e.target.value = '';
              if (files.length > 0) onFiles(files);
            }}
          />
          <Button variant="quiet" iconOnly icon="file" aria-label={t('chat.composer.attach')} disabled={offline} onClick={() => picker.current?.click()} className="mb-1" />
          {sending ? (
            <Button variant="secondary" iconOnly icon="x" aria-label={t('chat.composer.stop')} onClick={onStop} className="mb-1" />
          ) : (
            <Button type="submit" variant="primary" iconOnly icon="send" aria-label={t('chat.composer.send')} disabled={!canSend} className="mb-1" />
          )}
        </div>
      </div>
      <p className="m-0 px-4 font-ui text-[13px] leading-[18px] text-text-muted">{offline ? t('chat.composer.offline') : hint}</p>
    </form>
  );
}
