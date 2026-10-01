export const CITATION = /\[(\d{1,2})\]/g;

/** `[n]` markers that point at the message's n-th document card. */
export function citedNumbers(text: string, docs: number): number[] {
  return [...text.matchAll(CITATION)].map((m) => Number(m[1])).filter((n) => n >= 1 && n <= docs);
}
