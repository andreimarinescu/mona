import { Badge, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { useShellCounts } from '../data/hooks';
import { useLang } from './useLang';

function useReviewCount() {
  const lang = useLang();
  const count = useShellCounts().data?.reviewCount ?? 0;
  return { count, n: format.number(count, lang) };
}

export function ReviewBadge() {
  const { count, n } = useReviewCount();
  if (count <= 0) return null;
  return (
    <span aria-hidden>
      <Badge tone="accent" className="mona-badge--count">
        {n}
      </Badge>
    </span>
  );
}

export function ReviewCountText() {
  const { t } = useTranslation();
  const { count, n } = useReviewCount();
  if (count <= 0) return null;
  return <span className="mona-sr">{t('nav.reviewCount', { count, n })}</span>;
}
