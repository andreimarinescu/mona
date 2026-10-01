import type { ReactNode } from 'react';

export interface CardShellProps {
  kind: string;
  id: string;
  label?: string;
  children: ReactNode;
  className?: string;
}

/** The chat cards' frame; `data-card`/`data-id` name the C3 part. */
export function CardShell({ kind, id, label, children, className = '' }: CardShellProps) {
  return (
    <article
      data-card={kind}
      data-id={id}
      aria-label={label}
      className={`flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-1 ${className}`}
    >
      {children}
    </article>
  );
}

export function Overline({ children }: { children: ReactNode }) {
  return <span className="font-ui text-[12px] leading-4 font-semibold tracking-[0.12em] text-text-muted uppercase">{children}</span>;
}
