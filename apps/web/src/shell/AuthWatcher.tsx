import { useRouter } from '@tanstack/react-router';
import { useEffect } from 'react';
import { unlockHref } from '../data/auth';
import { setAuthLostHandler } from '../data/http';

/** C2 §16.3: any call that answers 401 or 423 sends the person to /unlock, and back to this page afterwards. */
export function AuthWatcher() {
  const router = useRouter();
  useEffect(() => {
    setAuthLostHandler(() => {
      const { pathname, searchStr, hash } = router.state.location;
      if (pathname === '/unlock') return;
      void router.navigate({ ...unlockHref(`${pathname}${searchStr}${hash ? `#${hash}` : ''}`), replace: false });
    });
    return () => setAuthLostHandler(null);
  }, [router]);
  return null;
}
