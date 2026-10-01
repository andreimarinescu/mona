import emptyNoResults from '@design/mona-handoff/assets/illustrations/empty-no-results.svg';
import { Banner, Button, EmptyState, Icon, Skeleton, Spinner, format } from '@mona/ui';
import { useParams, useSearch } from '@tanstack/react-router';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DocStatusPill } from '../../components/DocStatusPill';
import { InternalLink } from '../../components/InternalLink';
import { calendarDate } from '../../data/calendar';
import type { DocumentDetail, ExtractedField, FieldKey } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { ApiError } from '../../data/http';
import { useEntityList } from '../../data/registry';
import { useDocument } from '../../data/review';
import { PdfFrame, type PdfFrameHandle } from '../../pdfjs/PdfFrame';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { PipelineStepper } from '../intake/PipelineStepper';
import { DocumentSidePanel } from './DocumentSidePanel';
import { clampPage, parseDocumentSearch, showOnPage } from './search';

function Frame({ children, title }: { children: React.ReactNode; title?: string }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex max-w-[880px] flex-col gap-6 p-6 lg:p-10">
      <InternalLink href="/archive" className="inline-flex items-center gap-1 text-info underline">
        <Icon name="chevron-left" size={16} />
        {t('nav.archive')}
      </InternalLink>
      <h1 className="m-0 text-text [font:var(--type-title)]">{title ?? t('nav.document')}</h1>
      {children}
    </div>
  );
}

export function DocumentPage() {
  const { t } = useTranslation();
  const { documentId } = useParams({ strict: false }) as { documentId?: string };
  const search = parseDocumentSearch(useSearch({ strict: false }) as Record<string, unknown>);
  const query = useDocument(documentId);

  if (query.isPending) {
    return (
      <Frame>
        <Skeleton lines={6} />
      </Frame>
    );
  }
  if (query.isError || !query.data) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Frame>
        {missing ? (
          <EmptyState art={emptyNoResults} title={t('viewer.notFound.title')}>
            {t('viewer.notFound.body')}
          </EmptyState>
        ) : (
          <Banner tone="danger" actions={<Button variant="secondary" size="sm" onClick={() => void query.refetch()}>{t('common.retry')}</Button>}>
            {t(errorKey(query.error), errorValues(query.error))}
          </Banner>
        )}
      </Frame>
    );
  }
  return <Viewer key={query.data.id} doc={query.data} search={search} />;
}

export function Viewer({ doc, search }: { doc: DocumentDetail; search: ReturnType<typeof parseDocumentSearch> }) {
  const { t } = useTranslation();
  const lang = useLang();
  const { openChat } = useAppState();
  const entityList = useEntityList().data;
  const frame = useRef<PdfFrameHandle>(null);
  const [active, setActive] = useState<FieldKey | null>(search.field && doc.fields.some((f) => f.key === search.field) ? search.field : null);
  const quoteLang = entityList?.items.find((e) => e.id === doc.entityId)?.filingLanguage ?? 'fr';
  const page = clampPage(search.page, doc.pageCount);

  function show(field: ExtractedField) {
    const { query, page: at } = showOnPage(field);
    setActive(field.key);
    void frame.current?.find(query, at);
  }

  const meta = [
    doc.entityName,
    doc.date ? format.date(calendarDate(doc.date), lang) : null,
    doc.pageCount ? t('viewer.pages', { count: doc.pageCount, n: format.number(doc.pageCount, lang) }) : null,
  ].filter(Boolean);

  return (
    <div className="flex min-h-screen flex-col lg:h-screen" data-testid="document-viewer" data-document-id={doc.id}>
      <header className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-border bg-surface px-5 py-3">
        <InternalLink href="/archive" className="inline-flex items-center gap-1 font-ui text-[15px] leading-[22px] text-info underline">
          <Icon name="chevron-left" size={16} />
          {t('nav.archive')}
        </InternalLink>
        <div className="flex min-w-[200px] flex-1 flex-col gap-0.5">
          <h1 className="m-0 text-text [font:var(--type-heading)]">{doc.title}</h1>
          <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{meta.join(' · ')}</p>
        </div>
        <DocStatusPill doc={doc} />
        <a className="mona-btn mona-btn--secondary mona-btn--sm" href={`/api/documents/${doc.id}/original`} download>
          <Icon name="download" size={16} />
          {t('viewer.download')}
        </a>
        <Button variant="primary" size="sm" icon="send" onClick={() => openChat()}>
          {t('viewer.askMona')}
        </Button>
      </header>
      <div className={`grid min-h-0 flex-1 ${doc.status === 'processing' ? '' : 'lg:grid-cols-[minmax(0,1fr)_440px]'}`}>
        <section aria-label={t('viewer.document')} className="flex h-[70vh] min-h-0 items-stretch justify-center bg-inverse lg:h-auto">
          {doc.status === 'processing' ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 bg-surface-sunken p-8 text-center" role="status" data-testid="viewer-processing">
              <Spinner size={32} label={t('viewer.processing.title')} />
              <p className="m-0 max-w-[420px] text-text [font:var(--type-voice)]">{t('viewer.processing.body')}</p>
              <PipelineStepper doc={doc} />
            </div>
          ) : doc.status === 'unreadable' ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 bg-surface-sunken p-8 text-center" data-testid="viewer-unreadable">
              <Icon name="file-x" size={40} />
              <p className="m-0 max-w-[420px] text-text [font:var(--type-voice)]">{t('viewer.unreadable.body')}</p>
              <InternalLink href={`/review/${doc.id}`} className="mona-btn mona-btn--primary">
                {t('viewer.unreadable.review')}
              </InternalLink>
            </div>
          ) : (
            <PdfFrame file={doc.pdfUrl} page={page} query={search.q} title={t('viewer.frameTitle', { title: doc.title })} handle={frame} />
          )}
        </section>
        {doc.status === 'processing' ? null : (
          <section aria-label={t('viewer.details')} className="min-h-0 overflow-y-auto border-t border-border bg-surface lg:border-t-0 lg:border-l">
            <DocumentSidePanel doc={doc} activeField={active} focusField={search.field} quoteLang={quoteLang} onShow={show} />
          </section>
        )}
      </div>
    </div>
  );
}
