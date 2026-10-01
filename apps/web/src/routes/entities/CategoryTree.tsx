import { CategoryIcon, Icon, format } from '@mona/ui';
import { useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { CategoryDto } from '../../data/dto';
import { useLang } from '../../shell/useLang';

export interface CategoryTreeProps {
  categories: CategoryDto[];
  counts: Record<string, number>;
  selectedId: string | undefined;
  onSelect(categoryId: string): void;
}

function itemsOf(tree: HTMLElement | null): HTMLElement[] {
  return [...(tree?.querySelectorAll<HTMLElement>('[role="treeitem"]') ?? [])];
}

/** ARIA tree: categories with their icons and counts, subcategories beneath the one that is open. */
export function CategoryTree({ categories, counts, selectedId, onSelect }: CategoryTreeProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const tree = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState<Set<string>>(() => new Set(selectedId ? [selectedId] : []));
  const [focusId, setFocusId] = useState<string | null>(null);
  const [seen, setSeen] = useState(selectedId);
  if (seen !== selectedId) {
    setSeen(selectedId);
    if (selectedId && !open.has(selectedId)) setOpen(new Set([...open, selectedId]));
  }
  const tabbable = focusId ?? selectedId ?? categories[0]?.id;

  const toggle = (id: string, to?: boolean) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (to ?? !next.has(id)) next.add(id);
      else next.delete(id);
      return next;
    });

  function onKeyDown(e: KeyboardEvent<HTMLLIElement>, category: CategoryDto, isSub: boolean) {
    if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey || e.altKey) return;
    const items = itemsOf(tree.current);
    const index = items.indexOf(e.currentTarget);
    const go = (el: HTMLElement | undefined) => {
      if (!el) return;
      e.preventDefault();
      el.focus();
    };
    const expanded = open.has(category.id);
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
        if (!isSub && category.subcategories.length > 0 && !expanded) {
          e.preventDefault();
          toggle(category.id, true);
        } else if (!isSub && expanded) go(items[index + 1]);
        return;
      case 'ArrowLeft':
        if (!isSub && expanded) {
          e.preventDefault();
          toggle(category.id, false);
        } else if (isSub) go(e.currentTarget.parentElement?.closest<HTMLElement>('[role="treeitem"]') ?? undefined);
        return;
      case 'Enter':
      case ' ':
        e.preventDefault();
        onSelect(category.id);
    }
  }

  return (
    <ul ref={tree} role="tree" aria-label={t('entities.categories.tree')} className="m-0 flex list-none flex-col p-2" data-testid="category-tree">
      {categories.map((category) => {
        const expanded = open.has(category.id);
        const selected = category.id === selectedId;
        const count = counts[category.id] ?? 0;
        const label = category.labels[lang];
        return (
          <li
            key={category.id}
            role="treeitem"
            aria-level={1}
            aria-selected={selected}
            aria-expanded={category.subcategories.length > 0 ? expanded : undefined}
            aria-label={t('entities.categories.item', { name: label, count, n: format.number(count, lang) })}
            tabIndex={tabbable === category.id ? 0 : -1}
            data-category-id={category.id}
            className="m-0 list-none outline-none"
            onFocus={(e) => {
              if (e.target === e.currentTarget) setFocusId(category.id);
            }}
            onKeyDown={(e) => onKeyDown(e, category, false)}
          >
            <div
              className={`flex cursor-pointer items-center gap-2 rounded-md py-2 pr-3 pl-2 font-ui text-[15px] leading-[22px] ${selected ? 'bg-accent-soft font-semibold text-accent-strong' : 'text-text hover:bg-surface-sunken'}`}
              onClick={() => onSelect(category.id)}
            >
              <span
                aria-hidden
                className="inline-flex size-5 shrink-0 items-center justify-center text-text-muted"
                onClick={(e) => {
                  if (category.subcategories.length === 0) return;
                  e.stopPropagation();
                  toggle(category.id);
                }}
              >
                {category.subcategories.length > 0 ? <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={16} /> : null}
              </span>
              <CategoryIcon category={category.icon} size={24} iconSize={14} />
              <span className="min-w-0 flex-1 truncate">{label}</span>
              <span aria-hidden className="text-[14px] text-text-muted tabular-nums">
                {format.number(count, lang)}
              </span>
            </div>
            {expanded && category.subcategories.length > 0 ? (
              <ul role="group" className="m-0 list-none p-0">
                {category.subcategories.map((sub) => (
                  <li
                    key={sub.key}
                    role="treeitem"
                    aria-level={2}
                    aria-selected={false}
                    tabIndex={-1}
                    data-subcategory-key={sub.key}
                    className="m-0 list-none outline-none"
                    onKeyDown={(e) => onKeyDown(e, category, true)}
                  >
                    <div className="flex cursor-pointer items-center rounded-md py-2 pr-3 pl-[52px] font-ui text-[15px] leading-[22px] text-text hover:bg-surface-sunken" onClick={() => onSelect(category.id)}>
                      <span className="min-w-0 flex-1 truncate">{sub.labels[lang]}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
