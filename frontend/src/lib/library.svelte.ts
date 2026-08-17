import { api } from "./api";
import type { Example, PairInput } from "./types";

/**
 * Single owner of the training-pair collection. The Detect surface reads it
 * (calibration gating, "try an example"); the Library sheet renders and
 * mutates it. Loaded once at startup, then kept in sync by every mutation,
 * so the calibration status in the header can never disagree with the list.
 */
export const library = $state({
  examples: [] as Example[],
  loading: true,
  error: null as string | null,
});

/**
 * Scoring needs at least this many pairs. The server is the authority and
 * answers 409 below it (MIN_EXAMPLES in backend/app/main.py); this copy exists
 * only so the UI can gate itself without a round-trip. Keep them in step.
 */
export const MIN_PAIRS = 2;

export async function loadLibrary(): Promise<void> {
  library.loading = true;
  library.error = null;
  try {
    library.examples = await api.listExamples();
  } catch (err) {
    library.error = err instanceof Error ? err.message : "Something went wrong.";
  } finally {
    library.loading = false;
  }
}

export async function addPair(pair: PairInput): Promise<Example> {
  const row = await api.createExample(pair);
  library.examples = [...library.examples, row];
  return row;
}

export async function updatePair(id: number, pair: PairInput): Promise<Example> {
  const row = await api.updateExample(id, pair);
  library.examples = library.examples.map((e) => (e.id === id ? row : e));
  return row;
}

export async function deletePair(id: number): Promise<void> {
  await api.deleteExample(id);
  library.examples = library.examples.filter((e) => e.id !== id);
}

/**
 * Import pairs and re-fetch the list (the server skips duplicates, so the
 * authoritative result lives there). Returns how many of the *sent* pairs
 * were actually added.
 */
export async function importPairs(pairs: PairInput[]): Promise<number> {
  const result = await api.importExamples(pairs);
  const fresh = await api.listExamples();
  library.examples = fresh;
  library.error = null;
  return result.imported;
}
