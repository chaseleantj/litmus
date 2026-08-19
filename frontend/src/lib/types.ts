/**
 * How much of a text a map point carries. The server is the authority and does
 * the truncating (SNIPPET_CHARS in backend/app/main.py); this copy exists only
 * so the dev mock produces the same payload. Keep them in step.
 */
export const SNIPPET_CHARS = 240;

export interface Example {
  id: number;
  ai: string;
  human: string;
  created_at: string;
  updated_at: string;
}

export interface PairInput {
  ai: string;
  human: string;
}

export interface ImportResult {
  imported: number;
  total: number;
}

/** One sentence of a scored text: where it sits in the text and how it reads on
 *  its own. Offsets are UTF-16 code units, so they slice a JS string directly. */
export interface SentenceScore {
  start: number;
  end: number;
  score: number;
}

/** A scored text. `score` is the whole-text score every verdict is built on;
 *  `sentences` is the reading beside it, empty for a one-sentence text. */
export interface TextScore {
  score: number;
  sentences: SentenceScore[];
}

export interface MapPoint {
  pair_id: number;
  role: "ai" | "human";
  snippet: string;
  truncated: boolean;
  score: number;
  x: number;
  y: number;
}

export interface MapResult {
  points: MapPoint[];
  /** Which projection actually produced the 2D layout. */
  method: "umap" | "pca";
  pairs: number;
}

export interface CompareResult {
  first: TextScore;
  second: TextScore;
  gap: number;
}
