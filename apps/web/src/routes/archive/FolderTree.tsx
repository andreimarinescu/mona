import { Icon, format } from '@mona/ui';
import { useRouter } from '@tanstack/react-router';
import { useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { folderHref, useFolderListing } from '../../data/archive';
import type { FolderNode } from '../../data/dto';
import { useLang } from '../../shell/useLang';

const keyOf = (path: string[]) => path.join('/');

interface TreeContext {
  selected: string[];
  entityId?: string;
  expanded: Set<string>;
  tabbable: string | null;
  toggle(path: string[], open?: boolean): void;
  select(path: string[]): void;
  setFocus(key: string): void;
}

function Level({ path, level, ctx }: { path: string[]; level: number; ctx: TreeContext }) {
  const listing = useFolderListing(path, ctx.entityId);
  const folders = listing.data?.folders ?? [];
  const content = folders.map((node) => <Node key={keyOf(node.path)} node={node} level={level} ctx={ctx} />);
  return level === 1 ? <>{content}</> : <ul role="group" className="m-0 list-none p-0">{content}</ul>;
}

function Node({ node, level, ctx }: { node: FolderNode; level: number; ctx: TreeContext }) {
  const { t } = useTranslation();
  const lang = useLang();
  const key = keyOf(node.path);
  const expanded = node.hasChildren && ctx.expanded.has(key);
  const selected = keyOf(ctx.selected) === key;
  const li = useRef<HTMLLIElement>(null);

  function onKeyDown(e: KeyboardEvent<HTMLLIElement>) {
    if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey || e.altKey) return;
    const items = [...(li.current?.closest('[role="tree"]')?.querySelectorAll<HTMLElement>('[role="treeitem"]') ?? [])];
    const index = items.indexOf(e.currentTarget);
    const go = (el: HTMLElement | null | undefined) => {
      if (!el) return;
      e.preventDefault();
      el.focus();
    };
    switch (e.key) {
      case 'ArrowDown':
        return go(items[index + 1]);
      case 'ArrowUp':
        return go(items[index - 1]);
      case 'Home':
        return go(items[0]);
      case 'End':
        return go(items[items.length - 1]);
      case 'ArrowRight':
        if (node.hasChildren && !expanded) {
          e.preventDefault();
          ctx.toggle(node.path, true);
        } else if (expanded) go(li.current?.querySelector<HTMLElement>(':scope > ul > [role="treeitem"]'));
        return;
      case 'ArrowLeft':
        if (expanded) {
          e.preventDefault();
          ctx.toggle(node.path, false);
        } else go(li.current?.parentElement?.closest<HTMLElement>('[role="treeitem"]'));
        return;
      case 'Enter':
      case ' ':
        e.preventDefault();
        ctx.select(node.path);
    }
  }

  return (
    <li
      ref={li}
      role="treeitem"
      aria-level={level}
      aria-expanded={node.hasChildren ? expanded : undefined}
      aria-selected={selected}
      aria-label={t('archive.tree.item', { name: node.name, count: node.documentCount, n: format.number(node.documentCount, lang) })}
      tabIndex={ctx.tabbable === key ? 0 : -1}
      data-path={key}
      className="m-0 list-none outline-none"
      onFocus={(e) => {
        if (e.target === e.currentTarget) ctx.setFocus(key);
      }}
      onKeyDown={onKeyDown}
    >
      <div
        className={`flex cursor-pointer items-center gap-2 rounded-md py-2 pr-3 font-ui text-[15px] leading-[22px] ${selected ? 'bg-accent-soft font-semibold text-accent-strong' : 'text-text hover:bg-surface-sunken'}`}
        style={{ paddingLeft: 8 + (level - 1) * 20 }}
        onClick={() => ctx.select(node.path)}
      >
        <span
          aria-hidden
          className="inline-flex size-5 shrink-0 items-center justify-center text-text-muted"
          onClick={(e) => {
            if (!node.hasChildren) return;
            e.stopPropagation();
            ctx.toggle(node.path);
          }}
        >
          {node.hasChildren ? <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={16} /> : null}
        </span>
        <Icon name="folder" size={18} />
        <span className="min-w-0 flex-1 truncate">{node.name}</span>
        <span aria-hidden className="font-ui text-[14px] text-text-muted tabular-nums">
          {format.number(node.documentCount, lang)}
        </span>
      </div>
      {expanded ? <Level path={node.path} level={level + 1} ctx={ctx} /> : null}
    </li>
  );
}

export interface FolderTreeProps {
  selected: string[];
  entityId?: string;
}

export function FolderTree({ selected, entityId }: FolderTreeProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const root = useFolderListing([], entityId);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [seenSelected, setSeenSelected] = useState('');

  const selectedKey = keyOf(selected);
  if (seenSelected !== selectedKey) {
    setSeenSelected(selectedKey);
    const ancestors = selected.slice(0, -1).map((_, i) => keyOf(selected.slice(0, i + 1)));
    if (ancestors.some((a) => !expanded.has(a))) setExpanded(new Set([...expanded, ...ancestors]));
  }

  const first = root.data?.folders[0];
  const ctx: TreeContext = {
    selected,
    entityId,
    expanded,
    tabbable: focusKey ?? (selected.length > 0 ? selectedKey : first ? keyOf(first.path) : null),
    toggle: (path, open) =>
      setExpanded((prev) => {
        const next = new Set(prev);
        const k = keyOf(path);
        if (open ?? !next.has(k)) next.add(k);
        else next.delete(k);
        return next;
      }),
    select: (path) => {
      router.history.push(folderHref(path));
      setExpanded((prev) => new Set(prev).add(keyOf(path)));
    },
    setFocus: setFocusKey,
  };

  if (root.isPending) return <p className="m-0 p-4 text-text-muted">{t('archive.tree.loading')}</p>;
  if ((root.data?.folders.length ?? 0) === 0) return <p className="m-0 p-4 text-text-muted">{t('archive.tree.empty')}</p>;
  return (
    <ul role="tree" aria-label={t('archive.tree.label')} className="m-0 flex list-none flex-col p-2" data-testid="folder-tree">
      <Level path={[]} level={1} ctx={ctx} />
    </ul>
  );
}
