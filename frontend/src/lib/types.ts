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

/** One sentence of an analyzed text: character span into the original text
 *  plus a score from each granular approach. */
export interface SentenceScore {
  start: number;
  end: number;
  /** Projection onto the human–AI axis (relative ranking within the text). */
  proj: number;
  /** Affinity to human example sentences minus AI ones (zero-centered). */
  match: number;
}

export interface AnalyzeResult {
  sentences: SentenceScore[];
  proj_score: number;
  match_score: number;
}

export interface CompareResult {
  first: number;
  second: number;
  gap: number;
}
