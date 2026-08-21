/**
 * Counted nouns, in one place. "3 pairs", "1 word", "2 invalid entries" — the
 * number and its noun are one phrase, and every surface that shows a count
 * builds it here rather than spelling out its own `n === 1 ? "" : "s"`.
 *
 * Irregular plurals pass their own form; the default appends an "s".
 */
export function plural(n: number, word: string, plural = `${word}s`): string {
  return `${n} ${n === 1 ? word : plural}`;
}
