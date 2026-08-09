import type { CompareResult, ScoreResult } from "./types";

/**
 * Detect-view state lives at module level so it survives tab switches, and
 * the drafts survive a page reload via localStorage.
 */
const KEY = "personal-ai-detector:compare-drafts";

type Mode = "single" | "pair";

function loadDrafts(): { first: string; second: string; mode: Mode } {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (typeof p?.first === "string" && typeof p?.second === "string") {
        return {
          first: p.first,
          second: p.second,
          mode: p.mode === "pair" ? "pair" : "single",
        };
      }
    }
  } catch {
    /* private mode or corrupt entry: start empty */
  }
  return { first: "", second: "", mode: "single" };
}

const drafts = loadDrafts();

export const compareState = $state({
  mode: drafts.mode,
  first: drafts.first,
  second: drafts.second,
  result: null as CompareResult | null,
  lastScored: null as { a: string; b: string } | null,
  single: null as ScoreResult | null,
  lastScoredSingle: null as string | null,
});

export function persistDrafts(): void {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({
        first: compareState.first,
        second: compareState.second,
        mode: compareState.mode,
      }),
    );
  } catch {
    /* quota / private mode: drafts just won't survive reload */
  }
}

/** Load a pair into the detect view (ai first so "more human" slides right). */
export function loadPairIntoCompare(ai: string, human: string): void {
  compareState.mode = "pair";
  compareState.first = ai;
  compareState.second = human;
  compareState.result = null;
  compareState.lastScored = null;
  persistDrafts();
}
