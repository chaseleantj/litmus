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
