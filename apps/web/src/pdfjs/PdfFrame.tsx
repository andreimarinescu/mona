import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { configureViewerPreferences, dispatchFind, labelViewerControls, viewerUrl, type PdfViewerApp } from './find';

export interface PdfFrameHandle {
  find(query: string, page?: number): Promise<void>;
}

export interface PdfFrameProps {
  file: string;
  /** Opened at this page; later page changes go through `find`. Remount (key) to load another file. */
  page?: number;
  /** Sent to pdf.js find once the document has loaded, and again whenever it changes. */
  query?: string;
  title: string;
  handle?: Ref<PdfFrameHandle>;
}

type ViewerWindow = Window & { PDFViewerApplication?: PdfViewerApp };

export function PdfFrame({ file, page, query, title, handle }: PdfFrameProps) {
  const frame = useRef<HTMLIFrameElement>(null);
  const app = useRef<PdfViewerApp | null>(null);
  const stopLabelling = useRef<(() => void) | null>(null);
  const latest = useRef({ page, query });
  useEffect(() => {
    latest.current = { page, query };
  });
  const [src] = useState(() => {
    configureViewerPreferences();
    return viewerUrl(file, page);
  });

  useImperativeHandle(handle, () => ({
    find: async (q, p) => {
      if (app.current) await dispatchFind(app.current, q, p);
    },
  }));

  useEffect(() => {
    if (query && app.current) void dispatchFind(app.current, query, page);
  }, [query, page]);

  useEffect(() => () => stopLabelling.current?.(), []);

  return (
    <iframe
      ref={frame}
      title={title}
      src={src}
      className="block size-full border-0"
      data-testid="pdf-frame"
      onLoad={() => {
        app.current = (frame.current?.contentWindow as ViewerWindow | null)?.PDFViewerApplication ?? null;
        stopLabelling.current?.();
        const viewerDocument = frame.current?.contentDocument;
        stopLabelling.current = viewerDocument ? labelViewerControls(viewerDocument) : null;
        const { page: p, query: q } = latest.current;
        if (q && app.current) void dispatchFind(app.current, q, p);
      }}
    />
  );
}
