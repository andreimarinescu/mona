import { useRouter } from '@tanstack/react-router';
import type { AnchorHTMLAttributes } from 'react';

/** An anchor that navigates inside the SPA for a plain click, for targets built as strings (deep links with a query). */
export function InternalLink({ href, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  const router = useRouter();
  return (
    <a
      {...rest}
      href={href}
      onClick={(e) => {
        onClick?.(e);
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        router.history.push(href);
      }}
    />
  );
}
