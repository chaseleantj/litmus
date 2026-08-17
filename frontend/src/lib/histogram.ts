/**
 * Buckets training pairs by the local calendar day they were added, for the
 * library's "pairs added" histogram.
 *
 * Sole owner of every date, bucket and scale decision behind that chart —
 * LibraryHistogram.svelte only draws what comes out of here. Timestamps
 * arrive as UTC instants (ExampleOut.created_at) and are bucketed by the
 * user's local day, because "added on Tuesday" means their Tuesday.
 */
import type { Example } from "./types";

export type RangeId = "7d" | "30d" | "all";
export type BucketUnit = "day" | "week" | "month";

/** The range switcher, in the order it is rendered. */
export const RANGES = [
  { id: "7d", label: "7 days", phrase: "the past 7 days", days: 7 },
  { id: "30d", label: "30 days", phrase: "the past 30 days", days: 30 },
  { id: "all", label: "All time", phrase: "all time", days: null },
] as const satisfies readonly { id: RangeId; label: string; phrase: string; days: number | null }[];

export interface Bucket {
  /** Local midnight the bucket starts at, and the exclusive end after it. */
  start: Date;
  end: Date;
  count: number;
  /** Full spoken form: "Mon, 12 Aug", "12–18 Aug", "August 2026". */
  label: string;
  /** Terse form for the two axis end labels. */
  axisLabel: string;
}

export interface Histogram {
  buckets: Bucket[];
  unit: BucketUnit;
  /** Pairs falling inside the plotted range (not the whole library). */
  total: number;
  /** Pairs whose created_at could not be parsed — charted nowhere, disclosed. */
  undated: number;
  /** Tallest bucket, before the scale's minimum height is applied. */
  max: number;
  /** Top of the y axis: an integer, never smaller than MIN_Y_MAX. */
  yMax: number;
  /** Integer gridline values, 0 … yMax. */
  ticks: number[];
  /** Most recent dated pair in the whole library, for the empty-range note. */
  latest: Date | null;
}

/**
 * A one-day span would otherwise draw a single bar as wide as the card, and a
 * library of three pairs would draw three full-height ones. Both lie about
 * the shape of the data, so the domain has a floor in each direction.
 */
const MIN_BUCKETS = 7;
const MIN_Y_MAX = 4;
/** At most four gaps between gridlines, whatever the counts. */
const TICK_STEPS = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000];

const DAY_MS = 86_400_000;

/** Local midnight of the day `d` falls in. */
const startOfDay = (d: Date): Date => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/** Calendar arithmetic, not 24h arithmetic — survives DST changes. */
const addDays = (d: Date, n: number): Date =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

const addMonths = (d: Date, n: number): Date => new Date(d.getFullYear(), d.getMonth() + n, 1);

/** Whole days from a to b; rounded so a DST hour cannot shift the count. */
const daysBetween = (a: Date, b: Date): number => Math.round((b.getTime() - a.getTime()) / DAY_MS);

const fmt = (d: Date, opts: Intl.DateTimeFormatOptions) => d.toLocaleDateString(undefined, opts);

function dayBucket(start: Date): Bucket {
  return {
    start,
    end: addDays(start, 1),
    count: 0,
    label: fmt(start, { weekday: "short", day: "numeric", month: "short" }),
    axisLabel: fmt(start, { day: "numeric", month: "short" }),
  };
}

function weekBucket(start: Date): Bucket {
  const last = addDays(start, 6);
  const sameMonth = start.getMonth() === last.getMonth();
  return {
    start,
    end: addDays(start, 7),
    count: 0,
    label: `${fmt(start, sameMonth ? { day: "numeric" } : { day: "numeric", month: "short" })}–${fmt(last, { day: "numeric", month: "short" })}`,
    axisLabel: fmt(start, { day: "numeric", month: "short" }),
  };
}

function monthBucket(start: Date): Bucket {
  return {
    start,
    end: addMonths(start, 1),
    count: 0,
    label: fmt(start, { month: "long", year: "numeric" }),
    // Spelled with the full year: "Aug 26" under a chart of dates would read
    // as the 26th.
    axisLabel: fmt(start, { month: "short", year: "numeric" }),
  };
}

const makeBucket = (unit: BucketUnit, start: Date): Bucket =>
  unit === "day" ? dayBucket(start) : unit === "week" ? weekBucket(start) : monthBucket(start);

/** The bucket immediately before `b`, used to pad a too-short domain. */
const bucketBefore = (unit: BucketUnit, b: Bucket): Bucket =>
  makeBucket(
    unit,
    unit === "month" ? addMonths(b.start, -1) : addDays(b.start, unit === "week" ? -7 : -1),
  );

/**
 * Contiguous buckets covering [start, end] inclusive of the day `end`.
 * Day and week buckets are anchored to `end` so the last one always finishes
 * today; month buckets follow the calendar, where months are the anchor.
 */
function makeBuckets(unit: BucketUnit, start: Date, end: Date): Bucket[] {
  const buckets: Bucket[] = [];
  if (unit === "month") {
    for (let d = new Date(start.getFullYear(), start.getMonth(), 1); d <= end; d = addMonths(d, 1)) {
      buckets.push(monthBucket(d));
    }
    return buckets;
  }
  const step = unit === "week" ? 7 : 1;
  for (let d = addDays(end, -(step - 1)); d >= start; d = addDays(d, -step)) {
    buckets.unshift(makeBucket(unit, d));
  }
  return buckets;
}

/** Y axis: integer gridlines, a floor of MIN_Y_MAX, at most four gaps. */
function scaleFor(max: number): { yMax: number; ticks: number[] } {
  const target = Math.max(max, MIN_Y_MAX);
  const step = TICK_STEPS.find((s) => target / s <= 4) ?? Math.ceil(target / 4);
  const yMax = Math.ceil(target / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= yMax; v += step) ticks.push(v);
  return { yMax, ticks };
}

/** How coarse "all time" has to get before the bars stop being readable. */
function unitForSpan(spanDays: number): BucketUnit {
  if (spanDays <= 31) return "day";
  if (spanDays <= 26 * 7) return "week";
  return "month";
}

export function buildHistogram(examples: Example[], range: RangeId, now = new Date()): Histogram {
  const today = startOfDay(now);

  const times: number[] = [];
  let undated = 0;
  for (const ex of examples) {
    const t = new Date(ex.created_at);
    if (isNaN(t.getTime())) undated++;
    else times.push(startOfDay(t).getTime());
  }
  times.sort((a, b) => a - b);
  const earliest = times.length > 0 ? new Date(times[0]) : null;
  const latest = times.length > 0 ? new Date(times[times.length - 1]) : null;

  // The domain ends today, unless a timestamp sits in the future (clock skew
  // between server and browser): extend rather than drop the pair off the edge.
  const end = latest !== null && latest > today ? latest : today;
  const spec = RANGES.find((r) => r.id === range) ?? RANGES[0];
  let start = spec.days === null ? (earliest ?? today) : addDays(today, -(spec.days - 1));
  if (start > end) start = end;

  const unit = spec.days === null ? unitForSpan(daysBetween(start, end) + 1) : "day";
  const buckets = makeBuckets(unit, start, end);
  while (buckets.length < MIN_BUCKETS) buckets.unshift(bucketBefore(unit, buckets[0]));

  // Buckets ascend and times are sorted, so one pass places every pair.
  let bi = 0;
  let total = 0;
  for (const t of times) {
    while (bi < buckets.length && t >= buckets[bi].end.getTime()) bi++;
    if (bi >= buckets.length) break;
    if (t >= buckets[bi].start.getTime()) {
      buckets[bi].count++;
      total++;
    }
  }

  const max = Math.max(0, ...buckets.map((b) => b.count));
  return { buckets, unit, total, undated, max, ...scaleFor(max), latest };
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** "Mon, 12 Aug — 3 pairs": the hover/focus readout and each bar's label. */
export const bucketReadout = (b: Bucket): string => `${b.label} — ${plural(b.count, "pair")}`;

/**
 * The one disclosure for pairs the chart cannot place, worded the same way
 * wherever it appears. Empty when every pair has a usable date.
 */
export const undatedNote = (h: Histogram): string =>
  h.undated === 0
    ? ""
    : `${plural(h.undated, "pair")} with no valid date ${h.undated === 1 ? "is" : "are"} not charted`;

/** The resting caption: what the chart is actually showing, in full. */
export function histogramCaption(h: Histogram, range: RangeId): string {
  const spec = RANGES.find((r) => r.id === range) ?? RANGES[0];
  const body =
    range === "all"
      ? `${plural(h.total, "pair")} in all, one bar per ${h.unit}`
      : `${plural(h.total, "pair")} added in ${spec.phrase}`;
  const note = undatedNote(h);
  return note === "" ? body : `${body} · ${note}`;
}
