import { Icon, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { useLang } from '../shell/useLang';
import type { Attachment } from './types';

function kind(a: Attachment): string {
  const ext = /\.([a-z0-9]{2,5})$/i.exec(a.name)?.[1];
  return (ext ?? a.type.split('/')[1] ?? '').toUpperCase();
}

/** File icon, name in mono, type · size, and what Intake made of it. */
export function AttachmentChip({ attachment, uploading }: { attachment: Attachment; uploading?: boolean }) {
  const { t } = useTranslation();
  const lang = useLang();
  const status = uploading ? t('chat.attachment.uploading') : attachment.outcome ? t(`chat.attachment.${attachment.outcome}`) : t('chat.attachment.failed');
  return (
    <span className="inline-flex max-w-full items-center gap-3 rounded-md border border-border bg-surface px-3 py-2" data-testid="attachment-chip" data-outcome={attachment.outcome ?? (uploading ? 'uploading' : 'failed')}>
      <span aria-hidden className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm bg-surface-sunken text-text-muted">
        <Icon name={uploading ? 'loader' : 'file'} spin={uploading} size={18} />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate font-code text-[13px] leading-[18px] text-text">{attachment.name}</span>
        <span className="font-ui text-[12px] leading-4 text-text-muted">
          {[kind(attachment), format.fileSize(attachment.sizeBytes, lang), status].filter(Boolean).join(' · ')}
        </span>
      </span>
    </span>
  );
}
