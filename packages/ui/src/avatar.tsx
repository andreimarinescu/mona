import { useState } from 'react';
import { Icon } from './icon';
import { ui } from './i18n';
import type { AvatarGroupProps, AvatarProps, MonaAvatarProps } from './types';
import { cx } from './util';

export function MonaAvatar(props: MonaAvatarProps) {
  const size = props.size || 40;
  const state = props.state || 'idle';
  const sw = size <= 24 ? 3.6 : size <= 32 ? 3.1 : 2.8;
  const label = props.label || 'Mona';
  return (
    <span
      className={cx('mona-avatar', 'mona-avatar--' + state, props.className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={state === 'idle' ? label : label + ' · ' + state}
    >
      <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden>
        <path d="M11.5 27.5V17a4.25 4.25 0 0 1 8.5 0v10.5M20 17a4.25 4.25 0 0 1 8.5 0v10.5" fill="none" stroke="currentColor" strokeWidth={sw} />
      </svg>
      {state === 'offline' ? (
        <span className="mona-avatar__badge" aria-hidden>
          <Icon name="moon" size={Math.max(8, Math.round(size * 0.22))} strokeWidth={2.6} />
        </span>
      ) : null}
    </span>
  );
}

const AV_TONES = ['sea', 'olive', 'saffron', 'sand', 'umber'] as const;

function initials(name: string): string {
  const parts = String(name || '')
    .replace(/^(dr\.?|docteur|doctor|doamna|domnul|mme|m\.)\s+/i, '')
    .trim()
    .split(/\s+/);
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '';
  return (first + last).toUpperCase();
}

function hashTone(s: string): (typeof AV_TONES)[number] {
  let x = 0;
  for (let i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) >>> 0;
  return AV_TONES[x % AV_TONES.length] as (typeof AV_TONES)[number];
}

export function Avatar(props: AvatarProps) {
  const size = props.size || 32;
  const [broken, setBroken] = useState(false);
  const tone = props.tone || hashTone(props.name || '');
  return (
    <span
      className={cx('mona-person', 'mona-person--' + tone, props.className)}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      role="img"
      aria-label={props.name}
      title={props.showTitle ? props.name : undefined}
    >
      {props.src && !broken ? <img src={props.src} alt="" onError={() => setBroken(true)} /> : <span aria-hidden>{initials(props.name)}</span>}
    </span>
  );
}

export function AvatarGroup(props: AvatarGroupProps) {
  const people = props.people || [];
  const max = props.max || 4;
  const size = props.size || 32;
  const shown = people.slice(0, max);
  const rest = people.length - shown.length;
  return (
    <span className={cx('mona-avatars', props.className)} role="group" aria-label={props.label}>
      {shown.map((p, i) => (
        <Avatar key={i} name={p.name} src={p.src} size={size} showTitle />
      ))}
      {rest > 0 ? (
        <span
          className="mona-person mona-person--more"
          style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
          role="img"
          aria-label={'+' + rest + ' ' + ui(props.lang, 'more')}
        >
          {'+' + rest}
        </span>
      ) : null}
    </span>
  );
}
