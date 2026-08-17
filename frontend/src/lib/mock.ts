/**
 * Dev-only in-memory backend, used when /api is unreachable (see api.ts).
 * Never bundled in production: it is only reached via a dynamic import
 * guarded by `import.meta.env.DEV`.
 */
import { ApiError } from "./errors";
import { MIN_PAIRS } from "./library.svelte";
import { SNIPPET_CHARS, type Example, type PairInput } from "./types";

const now = () => new Date().toISOString();
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

/** `addedDaysAgo` backdates the seed row so the library histogram has a real
 *  shape in dev: a couple of recent days, one last month, one further back. */
const seedPairs: (PairInput & { addedDaysAgo: number })[] = [
  {
    addedDaysAgo: 0,
    ai: "Before weighing in let me ground it against what CLAUDE.md actually locks in.",
    human:
      "Before giving you my opinion, let me first read CLAUDE.md to get a better understanding of the project.",
  },
  {
    addedDaysAgo: 1,
    ai: "Retrieval runs as a multi-stage pipeline (src/ranking/pipeline.py). BM25 retrieves a candidate pool of 100 documents. Three further signals rescore that pool: lexical heuristics, dense embedding similarity, and link-graph authority. Combining them produces the top 10. Because BM25 is the only stage that retrieves anything and every later stage merely re-ranks, an unavailable external service costs the pipeline one signal rather than the whole query.",
    human:
      "We retrieve documents based on a multi-stage pipeline. First, BM25 retrieves a pool of 50 candidate documents. Then, these documents are reranked using a weighted average of three other signals: 1) lexical heuristics, 2) semantic similarity with embeddings, and 3) link authority, before being returned.",
  },
  {
    addedDaysAgo: 1,
    ai: "The journey to a gem-quality crystal begins by creating a supersaturated solution, where heat controls the solubility of the salt. You will start by heating approximately 200 mL of distilled water to near-boiling, around 80°C. Gradually stir in the copper sulfate powder—usually around 80 to 100 grams—until no more can dissolve and a few granules begin settling at the bottom.",
    human:
      "To grow a high quality copper sulfate crystal, first you need to create a supersaturated solution. Start by heating 200 mL of distilled water to near-boiling. Then, add 80 grams of copper sulfate powder to the water and keep stirring to make it dissolve faster.",
  },
  {
    addedDaysAgo: 4,
    ai: "I hope this message finds you well. I wanted to reach out to provide a quick update regarding the migration timeline. We have made significant progress on the database layer, and we remain on track to complete the remaining work by Friday. Please do not hesitate to reach out should you have any questions or concerns.",
    human:
      "Quick update on the migration: the database layer is done, and the rest should land by Friday. Ping me if anything looks off.",
  },
  {
    addedDaysAgo: 12,
    ai: "This utility provides a comprehensive solution for parsing configuration files. It seamlessly handles YAML, JSON, and TOML formats, ensuring a robust and flexible experience for developers. To get started, simply install the package and import the parser module.",
    human:
      "Parses config files in YAML, JSON, or TOML. Install the package, import `parser`, and call `parser.load(path)` — it figures out the format from the file extension.",
  },
  {
    addedDaysAgo: 45,
    ai: "Overall, the proposal is well-structured and demonstrates a clear understanding of the problem space. However, there are several areas that could benefit from further refinement. Firstly, the budget section would be strengthened by a detailed breakdown of costs. Additionally, the timeline appears somewhat optimistic given the overall scope.",
    human:
      "The proposal reads well and the problem framing makes sense. Two things to fix: the budget needs an actual cost breakdown, and the timeline feels optimistic for this scope — I'd add two weeks of buffer.",
  },
];

let nextId = 1;
const examples: Example[] = seedPairs.map((p) => ({
  id: nextId++,
  ai: p.ai,
  human: p.human,
  created_at: daysAgo(p.addedDaysAgo),
  updated_at: daysAgo(p.addedDaysAgo),
}));

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

function detailError(status: number, detail: string): never {
  throw new ApiError(status, detail);
}

/** The backend's 409, worded the same way (app/main.py require_calibrated). */
function requireCalibrated(): void {
  if (examples.length < MIN_PAIRS) {
    detailError(409, `Need at least ${MIN_PAIRS} examples`);
  }
}

/**
 * The backend's ExampleIn rules (app/main.py: valid_text, versions_differ),
 * reported the way api.ts words a real 422 — otherwise the editor's error
 * path only ever gets exercised against the live server.
 */
function validatePair(body: unknown): PairInput {
  const { ai, human } = (body ?? {}) as Partial<PairInput>;
  if (typeof ai !== "string" || !ai.trim()) {
    detailError(422, 'The "ai" field must be a non-empty text.');
  }
  if (typeof human !== "string" || !human.trim()) {
    detailError(422, 'The "human" field must be a non-empty text.');
  }
  if (ai.trim() === human.trim()) {
    detailError(422, "The AI version and your version must differ.");
  }
  return { ai, human };
}

/** Deterministic pseudo "human-likeness" score in roughly -0.2…+0.2, matching
 * the real backend's signed, near-zero scale. */
function score(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return (h % 4000) / 10000 - 0.2;
}

export async function handle(method: string, path: string, body: unknown): Promise<unknown> {
  await delay(250);
  const key = `${method} ${path}`;

  if (key === "GET /api/examples") return examples.map((e) => ({ ...e }));

  if (key === "POST /api/examples") {
    const p = validatePair(body);
    const row: Example = { id: nextId++, ai: p.ai, human: p.human, created_at: now(), updated_at: now() };
    examples.push(row);
    return { ...row };
  }

  if (key === "POST /api/examples/import") {
    // Mirrors the backend: exact duplicates are skipped, and `total` is the
    // resulting library size — not the size of the request.
    const seen = new Set(examples.map((e) => `${e.ai}\u0000${e.human}`));
    let imported = 0;
    for (const item of body as unknown[]) {
      const p = item as Partial<PairInput>;
      if (typeof p?.ai !== "string" || typeof p?.human !== "string") continue;
      if (!p.ai.trim() || !p.human.trim()) continue;
      const dedupeKey = `${p.ai}\u0000${p.human}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      examples.push({ id: nextId++, ai: p.ai, human: p.human, created_at: now(), updated_at: now() });
      imported++;
    }
    return { imported, total: examples.length };
  }

  if (key === "GET /api/map") {
    requireCalibrated();
    await delay(1200); // emulate the embedding call
    // Deterministic pseudo layout: AI texts drift left, human texts right,
    // with hash-based scatter — enough structure to exercise the map UI.
    const points = examples.flatMap((e) => {
      return (["ai", "human"] as const).map((role) => {
        const text = e[role];
        const s = score(text);
        let h = 0;
        for (let i = 0; i < text.length; i++) h = (h * 33 + text.charCodeAt(i)) >>> 0;
        const jx = ((h % 1000) / 1000 - 0.5) * 0.45;
        const jy = (((h >> 10) % 1000) / 1000 - 0.5) * 0.9;
        return {
          pair_id: e.id,
          role,
          snippet: text.slice(0, SNIPPET_CHARS),
          truncated: text.length > SNIPPET_CHARS,
          score: role === "ai" ? -Math.abs(s) - 0.02 : Math.abs(s) + 0.02,
          x: Math.min(1, Math.max(0, (role === "ai" ? 0.28 : 0.72) + jx)),
          y: Math.min(1, Math.max(0, 0.5 + jy)),
        };
      });
    });
    return { points, method: "pca", pairs: examples.length };
  }

  if (key === "POST /api/compare") {
    requireCalibrated();
    await delay(1500); // emulate the embedding call
    const { first, second } = body as { first: string; second: string };
    if (first.trim() === second.trim()) return { first: 0, second: 0, gap: 0 };
    const a = score(first);
    const b = score(second);
    return { first: a, second: b, gap: b - a };
  }

  if (key === "POST /api/score") {
    requireCalibrated();
    await delay(1500); // emulate the embedding call
    return { score: score((body as { text: string }).text) };
  }

  const putMatch = path.match(/^\/api\/examples\/(\d+)$/);
  if (putMatch) {
    const id = Number(putMatch[1]);
    const idx = examples.findIndex((e) => e.id === id);
    if (idx === -1) detailError(404, "Example not found.");
    if (method === "PUT") {
      const p = validatePair(body);
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
