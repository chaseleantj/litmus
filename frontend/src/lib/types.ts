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

export interface CompareResult {
  first: number;
  second: number;
  gap: number;
  summary: string;
}

export interface Health {
  status: string;
  examples: number;
}
