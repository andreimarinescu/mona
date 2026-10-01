import { Button, Dialog, Input } from '@mona/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { DocumentDetail } from '../../data/dto';
import { invalidateAfterWrite, toastFailure, useUndoRunner } from '../../data/journal';
import { deleteDocument } from '../../data/review';
import { toasts } from '../../toast/store';

export function DeleteDocumentDialog({ doc, onClose }: { doc: DocumentDetail; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const undo = useUndoRunner();
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const matches = typed === doc.fileName;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!matches || busy) return;
    setBusy(true);
    try {
      const result = await deleteDocument(doc.id, doc.fileName);
      const target = result.undo;
      toasts.push({ key: `deleted-${doc.id}`, message: 'viewer.delete.done', values: { title: doc.title }, undo: target ? () => void undo(target) : undefined });
      onClose();
      void invalidateAfterWrite(qc);
      void navigate({ to: '/archive' });
    } catch (err) {
      toastFailure(err);
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      tone="danger"
      onClose={onClose}
      title={t('viewer.delete.title')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" type="submit" form="delete-document-form" icon="trash" loading={busy} disabled={!matches}>
            {t('viewer.delete.confirm')}
          </Button>
        </>
      }
    >
      <form id="delete-document-form" className="flex flex-col gap-4" onSubmit={(e) => void submit(e)}>
        <p className="m-0 text-text">{t('viewer.delete.body', { title: doc.title })}</p>
        <p className="m-0 text-text">
          {t('viewer.delete.typeName')}{' '}
          <code className="rounded-sm bg-surface-sunken px-1.5 py-0.5 break-all text-text [font:var(--type-filename)]" data-testid="delete-file-name">
            {doc.fileName}
          </code>
        </p>
        <Input label={t('viewer.delete.fileName')} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} autoFocus />
      </form>
    </Dialog>
  );
}
