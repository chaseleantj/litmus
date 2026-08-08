/**
 * Dev-only in-memory backend, used when /api is unreachable (see api.ts).
 * Never bundled in production: it is only reached via a dynamic import
 * guarded by `import.meta.env.DEV`.
 */
import { ApiError } from "./errors";
import type { Example, PairInput } from "./types";

const now = () => new Date().toISOString();

const seedPairs: PairInput[] = [
  {
    ai: "Before weighing in let me ground it against what CLAUDE.md actually locks in.",
    human:
      "Before giving you my opinion, let me first read CLAUDE.md to get a better understanding of the project.",
  },
  {
    ai: "Retrieval runs as a multi-stage pipeline (src/ranking/pipeline.py). BM25 retrieves a candidate pool of 100 documents. Three further signals rescore that pool: lexical heuristics, dense embedding similarity, and link-graph authority. Combining them produces the top 10. Because BM25 is the only stage that retrieves anything and every later stage merely re-ranks, an unavailable external service costs the pipeline one signal rather than the whole query.",
    human:
      "We retrieve documents based on a multi-stage pipeline. First, BM25 retrieves a pool of 50 candidate documents. Then, these documents are reranked using a weighted average of three other signals: 1) lexical heuristics, 2) semantic similarity with embeddings, and 3) link authority, before being returned.",
  },
  {
    ai: "The journey to a gem-quality crystal begins by creating a supersaturated solution, where heat controls the solubility of the salt. You will start by heating approximately 200 mL of distilled water to near-boiling, around 80°C. Gradually stir in the copper sulfate powder—usually around 80 to 100 grams—until no more can dissolve and a few granules begin settling at the bottom.",
    human:
      "To grow a high quality copper sulfate crystal, first you need to create a supersaturated solution. Start by heating 200 mL of distilled water to near-boiling. Then, add 80 grams of copper sulfate powder to the water and keep stirring to make it dissolve faster.",
  },
];

let nextId = 1;
const examples: Example[] = seedPairs.map((p) => ({
  id: nextId++,
  ...p,
  created_at: now(),
  updated_at: now(),
}));

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

function detailError(status: number, detail: string): never {
  throw new ApiError(status, detail);
}

/** Deterministic pseudo "human-likeness" score in roughly 0.55–0.95. */
function score(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return 0.55 + (h % 4000) / 10000;
}

export async function handle(method: string, path: string, body: unknown): Promise<unknown> {
  await delay(250);
  const key = `${method} ${path}`;

  if (key === "GET /api/health") return { status: "ok", examples: examples.length };
  if (key === "GET /api/examples") return examples.map((e) => ({ ...e }));
  if (key === "GET /api/examples/export") return examples.map(({ ai, human }) => ({ ai, human }));

  if (key === "POST /api/examples") {
    const p = body as PairInput;
    const row: Example = { id: nextId++, ai: p.ai, human: p.human, created_at: now(), updated_at: now() };
    examples.push(row);
    return { ...row };
  }

  if (key === "POST /api/examples/import") {
    const items = body as unknown[];
    let imported = 0;
    for (const item of items) {
      const p = item as Partial<PairInput>;
      if (typeof p?.ai === "string" && typeof p?.human === "string" && p.ai.trim() && p.human.trim()) {
        examples.push({ id: nextId++, ai: p.ai, human: p.human, created_at: now(), updated_at: now() });
        imported++;
      }
    }
    return { imported, total: items.length };
  }

  if (key === "POST /api/compare") {
    if (examples.length < 2) detailError(409, "Need at least 2 examples to compare texts.");
    await delay(1500); // emulate the embedding call
    const { first, second } = body as { first: string; second: string };
    const a = score(first);
    const b = score(second);
    const gap = b - a;
    const who = gap > 0 ? "Text 2" : "Text 1";
    const summary =
      Math.abs(gap) < 0.02
        ? "The two texts are too close to call."
        : Math.abs(gap) >= 0.1
          ? `${who} sounds clearly more human.`
          : `${who} sounds slightly more human.`;
    return { first: a, second: b, gap, summary };
  }

  const putMatch = path.match(/^\/api\/examples\/(\d+)$/);
  if (putMatch) {
    const id = Number(putMatch[1]);
    const idx = examples.findIndex((e) => e.id === id);
    if (idx === -1) detailError(404, "Example not found.");
    if (method === "PUT") {
      const p = body as PairInput;
      examples[idx] = { ...examples[idx], ai: p.ai, human: p.human, updated_at: now() };
      return { ...examples[idx] };
    }
    if (method === "DELETE") {
      examples.splice(idx, 1);
      return undefined;
    }
  }

  detailError(404, `Mock: no handler for ${key}`);
}
