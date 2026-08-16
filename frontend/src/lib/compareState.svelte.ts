import type { CompareResult, ScoreResult } from "./types";

/**
 * Detect-view state lives at module level so it survives tab switches.
 * Page reloads start fresh (blank, single mode) — no localStorage drafts.
 */

export const compareState = $state({
  mode: "single" as "single" | "pair",
  first: "",
  second: "",
  result: null as CompareResult | null,
  lastScored: null as { a: string; b: string } | null,
  single: null as ScoreResult | null,
  lastScoredSingle: null as string | null,
});
