/**
 * The one symmetric score scale, shared by the Detect litmus strip and the
 * map's axis view: the smallest round span that fits every score with a
 * little headroom, so ticks stay at clean values while large scores never
 * leave the axis.
 */
const DOMAINS = [0.2, 0.3, 0.4, 0.5, 0.75, 1];

/** How the scale is read, in one place: inside TOO_CLOSE of zero a score is
 *  not a call at all, and at CLEAR it is a confident one. The verdict copy, the
 *  strip's tie band and the sentence tint all interpret scores through these. */
export const TOO_CLOSE = 0.02;
export const CLEAR = 0.1;

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

/** How dark a sentence's wash may get: faint enough to read through at full
 *  strength, visible enough to catch at a glance. */
const MAX_TINT_ALPHA = 0.22;

/**
 * The wash behind one sentence, or null for no wash — which is the honest
 * answer inside the tie band, where the sentence is not a call either way.
 * Intensity ramps from the band edge to a clear call, so a tint means the same
 * thing as a pin position on the strip.
 */
export function sentenceTint(score: number): string | null {
  const strength = (Math.abs(score) - TOO_CLOSE) / (CLEAR - TOO_CLOSE);
  if (strength <= 0) return null;
  const alpha = Math.min(1, strength) * MAX_TINT_ALPHA;
  return `hsl(var(${score > 0 ? "--human-hsl" : "--ai-hsl"}) / ${alpha.toFixed(3)})`;
}
