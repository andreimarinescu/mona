import { useRef, useState } from 'react';
import { useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { Button, Input } from '@mona/ui';
import { SAMPLE_PHRASE, dispatchFind, findHash, viewerUrl, type PdfViewerApp } from '../../pdfjs/find';

export function PdfFind() {
  const { t } = useTranslation();
  const search = useSearch({ from: '/dev/pdf' });
  const frame = useRef<HTMLIFrameElement>(null);
  const [query, setQuery] = useState(search.q ?? SAMPLE_PHRASE);

  const viewerWindow = () =>
    frame.current?.contentWindow as (Window & { PDFViewerApplication?: PdfViewerApp }) | null | undefined;

  const findViaHash = () => {
    const win = viewerWindow();
    if (win) win.location.hash = findHash(query, search.page);
  };

  const findViaEventBus = async () => {
    const app = viewerWindow()?.PDFViewerApplication;
    if (app) await dispatchFind(app, query, search.page);
  };

  return (
    <main className="flex h-screen flex-col gap-3 p-4">
      <h1 className="font-voice text-text">{t('dev.pdf.title')}</h1>
      <div className="flex flex-wrap items-end gap-3">
        <Input label={t('dev.pdf.query')} value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button variant="secondary" onClick={findViaHash}>
          {t('dev.pdf.findHash')}
        </Button>
        <Button variant="secondary" onClick={() => void findViaEventBus()}>
          {t('dev.pdf.findEvent')}
        </Button>
      </div>
      <iframe ref={frame} title="pdf.js" src={viewerUrl(search.file)} className="w-full grow border border-border" />
    </main>
  );
}
