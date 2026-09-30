import { Icon, Menu } from '@mona/ui';
import { Link, useNavigate, useRouterState } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { MORE_ITEMS, TAB_ITEMS, isActive } from './nav';
import { ReviewBadge, ReviewCountText } from './ReviewBadge';

const TAB = 'flex min-h-14 cursor-pointer border-0 bg-transparent no-underline flex-1 flex-col items-center justify-center gap-1 px-1 font-ui text-[12px] leading-4 font-medium text-text-muted';
const PILL = 'relative inline-flex h-8 w-14 items-center justify-center rounded-full';

export function MobileTabBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const moreActive = MORE_ITEMS.some((i) => isActive(i.to, pathname));
  return (
    <nav aria-label={t('shell.mainNav')} className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
      <ul className="m-0 flex list-none p-0">
        {TAB_ITEMS.map((item) => {
          const active = isActive(item.to, pathname);
          return (
            <li key={item.to} className="flex flex-1">
              <Link to={item.to} activeOptions={{ exact: item.to === '/' }} className={`${TAB} aria-[current=page]:text-accent-strong aria-[current=page]:font-semibold`}>
                <span className={`${PILL} ${active ? 'bg-accent-soft' : ''}`}>
                  <Icon name={item.icon} size={20} />
                  {item.badge === 'review' ? (
                    <span className="absolute -top-1 right-1">
                      <ReviewBadge />
                    </span>
                  ) : null}
                </span>
                <span>{t(item.label)}</span>
                {item.badge === 'review' ? <ReviewCountText /> : null}
              </Link>
            </li>
          );
        })}
        <li className="flex flex-1 [&>.mona-pop]:flex-1">
          <Menu
            label={t('shell.tabs.moreMenu')}
            placement="top-end"
            trigger={
              <button type="button" className={`${TAB} w-full ${moreActive ? 'text-accent-strong font-semibold' : ''}`}>
                <span className={`${PILL} ${moreActive ? 'bg-accent-soft' : ''}`}>
                  <Icon name="menu" size={20} />
                </span>
                <span>{t('shell.tabs.more')}</span>
              </button>
            }
            items={MORE_ITEMS.map((item) => ({
              id: item.to,
              label: t(item.label),
              icon: item.icon,
              onSelect: () => void navigate({ to: item.to }),
            }))}
          />
        </li>
      </ul>
    </nav>
  );
}
