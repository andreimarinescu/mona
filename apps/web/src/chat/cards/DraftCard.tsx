import { Badge, Button, Icon, Skeleton } from '@mona/ui';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { downloadDraft, useDraft } from '../../data/cards';
import type { Draft } from '../../data/dto';
import { toastFailure } from '../../data/journal';
import { useLang } from '../../shell/useLang';
import { useChatCard } from '../context';
import { CardShell } from './CardShell';

function Bracketed({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\[[^\]\n]+\])/g).map((piece, i) =>
        /^\[[^\]\n]+\]$/.test(piece) ? (
          <mark key={i} className="rounded-xs bg-highlight px-0.5 text-text">
            {piece}
          </mark>
        ) : (
          piece
        ),
      )}
    </>
  );
}

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

/** A reply draft: Copy and Download only. It has no Send action, ever (HANDOFF §4). */
export function DraftCard({ draft: snapshot }: { draft: Draft }) {
  const { t } = useTranslation();
  const lang = useLang();
  const card = useChatCard();
  const draft = useDraft(snapshot).data;
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2_000);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(draft.body ?? '');
      setCopied(true);
    } catch (err) {
      toastFailure(err);
    }
  }

  async function download() {
    setDownloading(true);
    try {
      const { blob, name } = await downloadDraft(draft, card.conversationId());
      save(blob, name);
    } catch (err) {
      toastFailure(err);
    } finally {
      setDownloading(false);
    }
  }

  const ready = draft.status === 'ready' && draft.body !== null;
  return (
    <CardShell kind="draft" id={draft.id} label={draft.title ?? t('chat.draft.title')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="m-0 font-ui text-[18px] leading-[26px] font-semibold text-text">{draft.title ?? t('chat.draft.title')}</h3>
        <Badge tone="warning">{t('chat.draft.badge')}</Badge>
      </div>
      {draft.status === 'generating' ? (
        <div className="flex flex-col gap-3" role="status">
          <p className="m-0 font-ui text-[14px] leading-5 text-text-muted">{t('chat.draft.generating')}</p>
          <Skeleton lines={4} />
        </div>
      ) : null}
      {draft.status === 'failed' ? <p className="m-0 font-ui text-[15px] leading-[22px] text-text-muted">{t('chat.draft.failed')}</p> : null}
      {ready ? (
        <>
          <p className="m-0 font-ui text-[14px] leading-5 text-text-muted">{t('chat.draft.language', { language: t(`language.${draft.lang}`) })}</p>
          <div
            className="rounded-md bg-surface-sunken p-4 font-ui text-[15px] leading-[24px] whitespace-pre-wrap text-text"
            lang={draft.lang !== lang ? draft.lang : undefined}
            data-testid="draft-body"
          >
            <Bracketed text={draft.body!} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" icon={copied ? 'check' : 'copy'} onClick={() => void copy()}>
              {copied ? t('chat.draft.copied') : t('chat.draft.copy')}
            </Button>
            <Button variant="secondary" icon="download" loading={downloading} onClick={() => void download()}>
              {t('chat.draft.download')}
            </Button>
            <span className="inline-flex min-w-0 flex-1 basis-56 items-start gap-2 font-ui text-[13px] leading-[18px] text-text-muted">
              <Icon name="lock" size={16} />
              {t('chat.draft.neverSends')}
            </span>
          </div>
        </>
      ) : null}
    </CardShell>
  );
}
