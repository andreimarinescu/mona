import type { IconName } from '@mona/ui';

export type NavTarget =
  | '/'
  | '/chat'
  | '/intake'
  | '/review'
  | '/archive'
  | '/rules'
  | '/entities'
  | '/activity'
  | '/settings';

export interface NavItem {
  to: NavTarget;
  icon: IconName;
  label: string;
  badge?: 'review';
}

export const NAV_GROUPS: NavItem[][] = [
  [
    { to: '/', icon: 'house', label: 'nav.home' },
    { to: '/chat', icon: 'message-square', label: 'nav.chat' },
    { to: '/intake', icon: 'inbox', label: 'nav.intake' },
    { to: '/review', icon: 'list-checks', label: 'nav.review', badge: 'review' },
    { to: '/archive', icon: 'archive', label: 'nav.archive' },
  ],
  [
    { to: '/rules', icon: 'route', label: 'nav.rules' },
    { to: '/entities', icon: 'building-2', label: 'nav.entities' },
  ],
  [
    { to: '/activity', icon: 'history', label: 'nav.activity' },
    { to: '/settings', icon: 'settings', label: 'nav.settings' },
  ],
];

export const TAB_ITEMS: NavItem[] = [
  { to: '/', icon: 'house', label: 'nav.home' },
  { to: '/review', icon: 'list-checks', label: 'shell.tabs.review', badge: 'review' },
  { to: '/chat', icon: 'message-square', label: 'nav.chat' },
  { to: '/archive', icon: 'archive', label: 'nav.archive' },
];

export const MORE_ITEMS: NavItem[] = [
  { to: '/rules', icon: 'route', label: 'nav.rules' },
  { to: '/entities', icon: 'building-2', label: 'nav.entities' },
  { to: '/activity', icon: 'history', label: 'nav.activity' },
  { to: '/settings', icon: 'settings', label: 'nav.settings' },
];

export function isActive(to: NavTarget, pathname: string): boolean {
  return to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`);
}
