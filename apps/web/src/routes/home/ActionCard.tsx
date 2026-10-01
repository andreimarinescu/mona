import { Badge } from '@mona/ui';
import type { ReactNode } from 'react';
import { InternalLink } from '../../components/InternalLink';

export interface ActionCardProps {
  id: string;
  title: string;
  count?: number;
  seeAll?: { label: string; href: string };
  footer?: ReactNode;
  children: ReactNode;
}

/** A card with a heading, an optional count, a "see all" link and its rows. */
export function ActionCard({ id, title, count, seeAll, footer, children }: ActionCardProps) {
  return (
    <section aria-labelledby={`${id}-title`} data-testid={id} className="flex min-w-0 flex-col gap-4 rounded-lg border border-border bg-surface p-5 shadow-1">
      <header className="flex items-center gap-3">
        <h2 id={`${id}-title`} className="m-0 text-text [font:var(--type-heading)]">
          {title}
        </h2>
        {count !== undefined ? <Badge count={count} tone="accent" /> : null}
        {seeAll ? (
          <InternalLink href={seeAll.href} className="ml-auto font-ui text-[14px] leading-5 font-semibold text-info underline underline-offset-2">
            {seeAll.label}
          </InternalLink>
        ) : null}
      </header>
      {children}
      {footer}
    </section>
  );
}
