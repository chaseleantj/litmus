/**
 * The one symmetric score scale, shared by the Detect litmus strip and the
 * map's axis view: the smallest round span that fits every score with a
 * little headroom, so ticks stay at clean values while large scores never
 * leave the axis.
 */
const DOMAINS = [0.2, 0.3, 0.4, 0.5, 0.75, 1];

/** The domain half-width to use for scores whose largest |value| is maxAbs. */
export function pickDomain(maxAbs: number): number {
  return DOMAINS.find((d) => d >= maxAbs * 1.05) ?? DOMAINS[DOMAINS.length - 1];
}

/** The five labelled ticks of a domain, ends and midpoints around zero. Both
 *  strips draw the same ladder, so they read as one scale. */
export function ticksFor(domain: number): number[] {
  return [-domain, -domain / 2, 0, domain / 2, domain];
}

/** Position of a score on the strip, 0..100 (%), clamped to the domain. */
export function scalePos(score: number, domain: number): number {
  return (0.5 + Math.max(-1, Math.min(1, score / domain)) / 2) * 100;
}

/** Tick label: "+0.2", "-0.1", "0". */
export const tickLabel = (v: number) => (v > 0 ? "+" : "") + String(parseFloat(v.toFixed(3)));

/** Signed score, three decimals: "+0.041", "-0.113", "0.000". */
export const fmtScore = (s: number) => (s > 0 ? "+" : "") + s.toFixed(3);
