import { api } from "./api";
import { toErrorState, type ErrorState } from "./errors";
import { addPair, isCalibrated } from "./library.svelte";
import { toast } from "./toast";
import type { CompareResult, TextScore } from "./types";

/**
 * Single owner of the Detect surface, mirroring mapState: the drafts, the
 * result, whether a score is in flight, and the bookkeeping that belongs to
 * the showing result — which side is the human version, and whether it has
 * already been saved.
 *
 * All of it is module-level because all of it has to survive the library sheet
 * opening over Detect or a trip to the map. The bookkeeping in particular has
 * to travel *with* the result: a result that came back paired with a fresh
 * "Human version" default would file the wrong side into the library, and an
 * already-saved pair would offer to save itself again.
 *
 * Page reloads start fresh (blank, single mode) — no localStorage drafts.
 */
export const compareState = $state({
  mode: "single" as "single" | "pair",
  first: "",
  second: "",
  result: null as CompareResult | null,
  lastScored: null as { a: string; b: string } | null,
  single: null as TextScore | null,
  lastScoredSingle: null as string | null,
  scoring: false,
  /** The showing result no longer describes what is typed. */
  stale: false,
  error: null as ErrorState | null,
  /** Which of the two compared texts "Save as pair" files as the human one. */
  saveHuman: "second" as "first" | "second",
  savingPair: false,
  savedPair: false,
});

const isPair = () => compareState.mode === "pair";

/** Enough text to score: both boxes in pair mode, the first one otherwise. */
export function ready(): boolean {
  return !!(isPair()
    ? compareState.first.trim() && compareState.second.trim()
    : compareState.first.trim());
}

/** The showing result describes exactly what is in the boxes. */
export function upToDate(): boolean {
  if (isPair()) {
    const last = compareState.lastScored;
    return !!last && last.a === compareState.first && last.b === compareState.second;
  }
  return compareState.lastScoredSingle === compareState.first;
}

// A counter makes sure a slow old answer can never overwrite a newer one.
let requestId = 0;

export function clearResults(): void {
  requestId++;
  compareState.lastScored = null;
  compareState.result = null;
  compareState.single = null;
  compareState.lastScoredSingle = null;
  compareState.savedPair = false;
  compareState.error = null;
  compareState.stale = false;
  compareState.scoring = false;
}

/** Typing only marks the result stale; scoring runs on Ctrl+Enter, paste into
 *  an empty box, or a programmatic trigger (swap, mode toggle, try-example). */
export function markStale(): void {
  if (!ready()) {
    clearResults();
    return;
  }
  // Without calibration there is no result to be stale against.
  compareState.stale = isCalibrated() && !upToDate();
}

export function queueRun(): void {
  if (!isCalibrated()) return;
  if (!ready()) {
    clearResults();
    return;
  }
  if (upToDate()) {
    compareState.stale = false;
    return;
  }
  compareState.stale = true;
  run();
}

async function run(): Promise<void> {
  const wasPair = isPair();
  const a = compareState.first;
  const b = compareState.second;
  const id = ++requestId;
  compareState.scoring = true;
  compareState.error = null;
  try {
    if (wasPair) {
      const r = await api.compare(a, b);
      if (id !== requestId) return;
      compareState.lastScored = { a, b };
      compareState.result = r;
      compareState.savedPair = false;
      compareState.saveHuman = r.gap >= 0 ? "second" : "first";
    } else {
      const r = await api.score(a);
      if (id !== requestId) return;
      compareState.lastScoredSingle = a;
      compareState.single = r;
    }
  } catch (err) {
    if (id !== requestId) return;
    // The invariant is "lastScored is set iff a result for it exists"; keeping
    // the old bookkeeping here would make upToDate() true with no result, and
    // both Ctrl+Enter and "Try again" would refuse to re-run.
    compareState.result = null;
    compareState.single = null;
    compareState.lastScored = null;
    compareState.lastScoredSingle = null;
    compareState.error = toErrorState(err);
  } finally {
    if (id === requestId) {
      compareState.scoring = false;
      compareState.stale = false;
    }
  }
}

export function setMode(mode: "single" | "pair"): void {
  if (compareState.mode === mode) return;
  compareState.mode = mode;
  compareState.error = null;
  queueRun();
}

export function toggleMode(): void {
  setMode(isPair() ? "single" : "pair");
}

export function swap(): void {
  if (!isPair() || (!compareState.first.trim() && !compareState.second.trim())) return;
  const a = compareState.first;
  compareState.first = compareState.second;
  compareState.second = a;
  const last = compareState.lastScored;
  if (
    compareState.result &&
    last &&
    last.a === compareState.second &&
    last.b === compareState.first
  ) {
    // The scores just trade places; no need to re-embed.
    compareState.result = {
      first: compareState.result.second,
      second: compareState.result.first,
      gap: -compareState.result.gap,
    };
    compareState.lastScored = { a: compareState.first, b: compareState.second };
    compareState.saveHuman = compareState.saveHuman === "first" ? "second" : "first";
  }
  queueRun();
}

/** File the compared texts as a training pair, human side per saveHuman. */
export async function savePair(): Promise<void> {
  if (compareState.savingPair || !compareState.result) return;
  const human = compareState.saveHuman === "first" ? compareState.first : compareState.second;
  const ai = compareState.saveHuman === "first" ? compareState.second : compareState.first;
  compareState.savingPair = true;
  try {
    await addPair({ ai, human });
    compareState.savedPair = true;
    toast("success", "Saved as a training pair.");
  } catch (err) {
    toast("error", toErrorState(err, "Could not save the pair.").message);
  } finally {
    compareState.savingPair = false;
  }
}
