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

export interface ScoreResult {
  score: number;
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
  first: number;
  second: number;
  gap: number;
}
