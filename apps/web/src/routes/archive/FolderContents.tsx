import { Banner, Breadcrumbs, Button, Icon, Skeleton, Table, format } from '@mona/ui';
import { useRouter } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import { folderHref, useFolderListing } from '../../data/archive';
import type { DocumentSummary } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { useLang } from '../../shell/useLang';
import { amountLabel, dateLabel } from './labels';
import { DocumentLink } from './ResultsTable';

export interface FolderContentsProps {
  path: string[];
  entityId?: string;
}

export function FolderContents({ path, entityId }: FolderContentsProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const router = useRouter();
  const listing = useFolderListing(path, entityId);
  const [explorer, setExplorer] = useState(false);
  const here = path[path.length - 1];

  const go = (href: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    router.history.push(href);
  };
  const crumbs = [
    { label: t('nav.archive'), href: '/archive', onClick: go('/archive') },
    ...path.map((segment, i) => {
      const href = folderHref(path.slice(0, i + 1));
      return i === path.length - 1 ? { label: segment } : { label: segment, href, onClick: go(href) };
    }),
  ];

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="folder-contents">
      <Breadcrumbs items={crumbs} maxItems={5} lang={lang} label={t('archive.folder.path')} />
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="m-0 text-text [font:var(--type-voice)]">{here ?? t('nav.archive')}</h2>
          <span className="break-all text-text-muted [font:var(--type-filename)]" data-testid="disk-path">
            {path.length > 0 ? path.join(' / ') : t('archive.folder.root')}
          </span>
        </div>
        <Button variant="secondary" size="sm" icon="external" aria-expanded={explorer} onClick={() => setExplorer((v) => !v)}>
          {t('archive.folder.showInExplorer')}
        </Button>
      </div>
      {explorer ? <Banner tone="info">{t('archive.folder.explorerInfo')}</Banner> : null}
      <Banner tone="info" icon="folder">
        {t('archive.folder.mirror')}
      </Banner>
      {listing.isPending ? <Skeleton lines={5} /> : null}
      {listing.isError ? (
        <Banner tone="danger" actions={<Button variant="secondary" size="sm" onClick={() => void listing.refetch()}>{t('common.retry')}</Button>}>
          {t(errorKey(listing.error), errorValues(listing.error))}
        </Banner>
      ) : null}
      {listing.data && listing.data.folders.length > 0 ? (
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label={t('archive.folder.subfolders')}>
          {listing.data.folders.map((f) => (
            <li key={f.name}>
              <InternalLink href={folderHref(f.path)} className="mona-btn mona-btn--secondary mona-btn--sm no-underline">
                <Icon name="folder" size={16} />
                {f.name} · {format.number(f.documentCount, lang)}
              </InternalLink>
            </li>
          ))}
        </ul>
      ) : null}
      {listing.data && listing.data.documents.length > 0 ? (
        <Table
          rowKey="id"
          rows={listing.data.documents}
          columns={[
            {
              key: 'fileName',
              label: t('archive.folder.fileName'),
              render: (d: DocumentSummary) => (
                <span className="flex items-center gap-2">
                  <Icon name="file" size={16} />
                  <DocumentLink doc={{ id: d.id, title: d.fileName }} />
                </span>
              ),
            },
            { key: 'date', label: t('archive.table.date'), render: (d: DocumentSummary) => <span className="whitespace-nowrap">{dateLabel(d.date, lang)}</span> },
            { key: 'amount', label: t('archive.table.amount'), numeric: true, align: 'end', render: (d: DocumentSummary) => amountLabel(d, lang) },
            {
              key: 'filedBy',
              label: t('archive.folder.filedBy'),
              render: (d: DocumentSummary) => (d.filedBy === 'user' ? t('archive.filedBy.user') : d.rule ? t('archive.filedBy.rule', { rule: d.rule.name }) : t('archive.filedBy.mona')),
            },
          ]}
        />
      ) : null}
      {listing.data && listing.data.documents.length === 0 && listing.data.folders.length === 0 ? <p className="m-0 text-text-muted">{t('archive.folder.empty')}</p> : null}
    </div>
  );
}
