import { Avatar, Button, Icon, MonaAvatar, format } from '@mona/ui';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ActivityItem } from '../../data/dto';
import { useGroupEntries } from '../../data/journal';
import { useLang } from '../../shell/useLang';
import { ActivityEntry } from './ActivityEntry';
import type { ActivityContext } from './context';

type GroupItem = Extract<ActivityItem, { kind: 'group' }>;

export function ActivityBatch({ item, ctx }: { item: GroupItem; ctx: ActivityContext }) {
  const { t } = useTranslation();
  const lang = useLang();
  const panel = useId();
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  const { group } = item;
  const full = useGroupEntries(group.id, all);
  const entries = all && full.data ? full.data.entries : item.preview;
  const remaining = item.entriesTotal - entries.length;
  const documents = all && full.data ? { ...ctx.documents, ...full.data.documents } : ctx.documents;
  const childCtx = { ...ctx, documents };
  const rule = group.ruleId ? ctx.rules[group.ruleId]?.name : undefined;
  const title = t(`activity.group.${group.kind}`, { n: format.number(item.entriesTotal, lang), rule: rule ?? t('activity.unknownRule'), context: group.actor });
  const undone = group.undoState === 'undone';
  const canUndo = group.undoState === 'undoable' || group.undoState === 'partial';
  const wholeLabel = group.kind === 'intake_batch' ? t('activity.undoWholeBatch') : t('activity.undoAll');

  return (
    <li className="list-none" data-group-id={group.id} data-undo-state={group.undoState}>
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3">
        <time dateTime={group.at} className="w-[52px] shrink-0 pt-1 font-ui text-[14px] leading-5 text-text-muted">
          {format.time(group.at, lang)}
        </time>
        <span className="shrink-0">{group.actor === 'mona' ? <MonaAvatar size={32} /> : <Avatar name={ctx.profileName || t('activity.you')} size={32} />}</span>
        <div className="flex min-w-[200px] flex-1 flex-col gap-0.5">
          <span className={`font-ui text-[15px] leading-[22px] font-semibold text-text ${undone ? 'line-through' : ''}`}>{title}</span>
          <span className="font-ui text-[13px] leading-[18px] text-text-muted">
            {t('activity.changesCount', { count: item.entriesTotal, n: format.number(item.entriesTotal, lang) })}
            {group.counts.undone > 0 ? ` · ${t('activity.undoneCount', { count: group.counts.undone, n: format.number(group.counts.undone, lang) })}` : ''}
            {group.counts.superseded > 0 ? ` · ${t('activity.supersededCount', { count: group.counts.superseded, n: format.number(group.counts.superseded, lang) })}` : ''}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {canUndo ? (
            <Button variant="secondary" size="sm" icon="undo" disabled={ctx.actions.busy} onClick={() => void ctx.actions.undoGroup(group.id)}>
              {wholeLabel}
            </Button>
          ) : null}
          {undone ? (
            <>
              <span className="rounded-full bg-surface-sunken px-3 py-1 font-ui text-[13px] leading-[18px] text-text">{t('activity.undoState.undone')}</span>
              {item.redoGroupId ? (
                <Button variant="quiet" size="sm" icon="undo" disabled={ctx.actions.busy} onClick={() => void ctx.actions.redoGroup(item.redoGroupId!)}>
                  {t('common.redo')}
                </Button>
              ) : null}
            </>
          ) : null}
          <Button
            variant="quiet"
            size="sm"
            iconOnly
            icon={open ? 'chevron-down' : 'chevron-right'}
            aria-expanded={open}
            aria-controls={panel}
            aria-label={open ? t('activity.collapse') : t('activity.expand')}
            onClick={() => setOpen((o) => !o)}
          />
        </div>
      </div>
      {open ? (
        <div id={panel} className="ml-0 flex flex-col pl-0 lg:ml-[68px]">
          <ul className="m-0 flex list-none flex-col p-0">
            {entries.map((entry) => (
              <ActivityEntry key={entry.id} entry={entry} ctx={childCtx} nested />
            ))}
          </ul>
          {remaining > 0 ? (
            <div className="border-t border-border py-3">
              <button
                type="button"
                className="cursor-pointer border-0 bg-transparent p-0 font-ui text-[14px] leading-5 font-medium text-info underline"
                onClick={() => setAll(true)}
              >
                {full.isFetching ? <Icon name="loader" size={14} spin /> : null}
                {t('activity.showMore', { count: remaining, n: format.number(remaining, lang) })}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
