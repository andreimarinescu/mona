const ALPHABET = '0123456789abcdefghjkmnpqrstvwxyz';

/** A C1 §1.2 id: prefix plus 26 Crockford base32 characters, derived from a counter so runs are reproducible. */
export function makeId(prefix: string, n: number): string {
  let rest = n;
  let out = '';
  for (let i = 0; i < 26; i++) {
    out = ALPHABET[rest % 32]! + out;
    rest = Math.floor(rest / 32);
  }
  return `${prefix}_${out}`;
}
