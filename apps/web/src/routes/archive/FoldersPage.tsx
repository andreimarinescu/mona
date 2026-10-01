import { useParams } from '@tanstack/react-router';
import { splatToPath } from '../../data/archive';
import { useAppState } from '../../state/context';
import { ArchiveHeader } from './ArchiveHeader';
import { FolderContents } from './FolderContents';
import { FolderTree } from './FolderTree';

export function FoldersPage() {
  const { _splat } = useParams({ strict: false }) as { _splat?: string };
  const { scope } = useAppState();
  const path = splatToPath(_splat);
  const entityId = scope === 'all' ? undefined : scope;
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 p-6 lg:p-10">
      <ArchiveHeader view="folders" />
      <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="rounded-xl border border-border bg-surface shadow-1">
          <FolderTree selected={path} entityId={entityId} />
        </div>
        <FolderContents path={path} entityId={entityId} />
      </div>
    </div>
  );
}
