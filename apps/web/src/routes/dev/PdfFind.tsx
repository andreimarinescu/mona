import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input } from '../../ds';
import { SAMPLE_PHRASE, dispatchFind, findHash, type PdfViewerApp } from '../../pdfjs/find';

const VIEWER = '/pdfjs/web/viewer.html?file=/dev/sample.pdf';

export function PdfFind() {
  const { t } = useTranslation();
  const frame = useRef<HTMLIFrameElement>(null);
  const [query, setQuery] = useState(SAMPLE_PHRASE);

  const viewerWindow = () =>
    frame.current?.contentWindow as (Window & { PDFViewerApplication?: PdfViewerApp }) | null | undefined;

  const findViaHash = () => {
    const win = viewerWindow();
    if (win) win.location.hash = findHash(query);
  };

  const findViaEventBus = async () => {
    const app = viewerWindow()?.PDFViewerApplication;
    if (app) await dispatchFind(app, query);
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
      <iframe ref={frame} title="pdf.js" src={VIEWER} className="w-full grow border border-border" />
    </main>
  );
}
