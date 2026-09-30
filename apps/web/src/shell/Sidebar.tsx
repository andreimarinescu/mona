import logoUrl from '@design/mona-handoff/assets/mona-logo.svg';
import { Icon } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { AskMonaButton } from './AskMonaButton';
import { EntityScopeSwitcher } from './EntityScopeSwitcher';
import { NAV_GROUPS } from './nav';
import { ReviewBadge, ReviewCountText } from './ReviewBadge';
import { SystemStatusLine } from './SystemStatusLine';
import { UserMenu } from './UserMenu';

export function Sidebar() {
  const { t } = useTranslation();
  return (
    <aside
      aria-label={t('shell.sidebar')}
      className="sticky top-0 hidden box-border h-screen w-[248px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-border bg-surface px-4 py-5 lg:flex"
    >
      <Link to="/" className="inline-flex w-fit rounded-sm px-1 no-underline" aria-label="Mona">
        <img src={logoUrl} alt="" width={96} height={30} />
      </Link>
      <EntityScopeSwitcher />
      <nav aria-label={t('shell.mainNav')} className="flex flex-col gap-2">
        {NAV_GROUPS.map((group, i) => (
          <ul key={i} className={`m-0 flex list-none flex-col gap-1 p-0 ${i > 0 ? 'border-t border-border pt-2' : ''}`}>
            {group.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  activeOptions={{ exact: item.to === '/' }}
                  className="flex min-h-11 items-center gap-3 rounded-md px-3 no-underline font-ui text-[15px] leading-5 font-medium text-text hover:bg-surface-sunken aria-[current=page]:bg-accent-soft aria-[current=page]:font-semibold aria-[current=page]:text-accent-strong aria-[current=page]:shadow-[inset_3px_0_0_var(--accent)]"
                >
                  <Icon name={item.icon} size={20} />
                  <span className="flex-1">{t(item.label)}</span>
                  {item.badge === 'review' ? (
                    <>
                      <ReviewBadge />
                      <ReviewCountText />
                    </>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-2">
        <AskMonaButton />
        <UserMenu />
        <SystemStatusLine />
      </div>
    </aside>
  );
}
