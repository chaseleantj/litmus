import type { CompareResult } from "./types";

/**
 * Compare-view state lives at module level so it survives tab switches, and
 * the drafts survive a page reload via localStorage.
 */
const KEY = "write-like-me:compare-drafts";

function loadDrafts(): { first: string; second: string } {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (typeof p?.first === "string" && typeof p?.second === "string") {
        return { first: p.first, second: p.second };
      }
    }
  } catch {
    /* private mode or corrupt entry: start empty */
  }
  return { first: "", second: "" };
}

const drafts = loadDrafts();

export const compareState = $state({
  first: drafts.first,
  second: drafts.second,
  result: null as CompareResult | null,
  lastScored: null as { a: string; b: string } | null,
});

export function persistDrafts(): void {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ first: compareState.first, second: compareState.second }),
    );
  } catch {
    /* quota / private mode: drafts just won't survive reload */
  }
}

/** Load a pair into the compare view (ai first so "more human" slides right). */
export function loadPairIntoCompare(ai: string, human: string): void {
  compareState.first = ai;
  compareState.second = human;
  compareState.result = null;
  compareState.lastScored = null;
  persistDrafts();
}
