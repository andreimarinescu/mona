import type { ReactNode } from 'react';

export interface SettingsSectionProps {
  id: string;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}

/** One anchored card of the Settings page. */
export function SettingsSection({ id, title, children, actions }: SettingsSectionProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="flex scroll-mt-6 flex-col gap-5 rounded-lg border border-border bg-surface p-6 shadow-1" data-testid={`settings-${id}`}>
      <header className="flex items-center justify-between gap-3">
        <h2 id={`${id}-title`} className="m-0 text-text [font:var(--type-heading)]">
          {title}
        </h2>
        {actions}
      </header>
      {children}
    </section>
  );
}
