import { Avatar, Icon, Menu } from '@mona/ui';
import { useNavigate, useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { lock, unlockHref } from '../data/auth';
import { useSettings } from '../data/hooks';
import { toastFailure } from '../data/journal';

export function UserMenu() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const router = useRouter();
  const name = useSettings().data?.profileName ?? '';
  async function lockScreen() {
    try {
      await lock();
    } catch (err) {
      toastFailure(err);
      return;
    }
    const { pathname, searchStr, hash } = router.state.location;
    void navigate(unlockHref(`${pathname}${searchStr}${hash ? `#${hash}` : ''}`));
  }
  return (
    <Menu
      label={t('shell.user.menu')}
      placement="top-start"
      trigger={
        <button
          type="button"
          className="flex w-full min-h-11 cursor-pointer items-center gap-3 rounded-md border-0 bg-transparent px-3 text-left font-ui text-text hover:bg-surface-sunken"
        >
          <Avatar name={name} size={32} />
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-[14px] leading-5 font-semibold">{name}</span>
            <span className="truncate text-[13px] leading-[18px] text-text-muted">{t('shell.user.caption')}</span>
          </span>
          <Icon name="more" size={18} />
        </button>
      }
      items={[
        { id: 'profile', label: t('shell.user.profile'), icon: 'pencil', onSelect: () => void navigate({ to: '/settings', hash: 'profile' }) },
        { id: 'lock', label: t('shell.user.lock'), icon: 'lock', onSelect: () => void lockScreen() },
      ]}
    />
  );
}
