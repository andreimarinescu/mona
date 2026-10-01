import { Button, SegmentedControl } from '@mona/ui';
import { useRouter } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AccountantExportDialog } from './AccountantExportDialog';

export type ArchiveView = 'list' | 'folders';

export function ArchiveHeader({ view }: { view: ArchiveView }) {
  const { t } = useTranslation();
  const router = useRouter();
  const [exporting, setExporting] = useState(false);
  return (
    <header className="flex flex-wrap items-center gap-4">
      <h1 className="m-0 flex-1 text-text [font:var(--type-title)]">{t('nav.archive')}</h1>
      <SegmentedControl
        label={t('archive.view.label')}
        value={view}
        options={[
          { value: 'list', label: t('archive.view.list'), icon: 'filter' },
          { value: 'folders', label: t('archive.view.folders'), icon: 'folder' },
        ]}
        onChange={(v) => router.history.push(v === 'folders' ? '/archive/folders' : '/archive')}
      />
      <Button variant="secondary" onClick={() => setExporting(true)}>
        {t('export.open')}
      </Button>
      <AccountantExportDialog open={exporting} onClose={() => setExporting(false)} />
    </header>
  );
}
