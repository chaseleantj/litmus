// Local tool: compares the writing style of two texts. Node 18 or newer, no packages needed.
//   node server.mjs      then open http://localhost:8000
//
// A tiny server rather than a plain HTML file, only because the API key has to
// live somewhere the browser cannot read it.

import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const MODEL = "openai/text-embedding-3-large";
const PORT = 8000;

// How far apart two texts must be before the difference is worth reporting.
// Grounded in measurement: the ten calibration pairs land between 0.09 and 0.49,
// while pairs the tool genuinely cannot separate land under 0.02.
const TOO_CLOSE = 0.02;
const CLEAR = 0.1;

const env = readFileSync(".env", "utf8");
const API_KEY = env.match(/OPENROUTER_API_KEY\s*=\s*(\S+)/)?.[1];
if (!API_KEY) throw new Error("No OPENROUTER_API_KEY found in .env");

const examples = JSON.parse(readFileSync("examples.json", "utf8"));
const page = () => readFileSync("index.html");

async function embed(texts) {
  const res = await fetch("https://openrouter.ai/api/v1/embeddings", {
    method: "POST",
    headers: { Authorization: `Bearer ${API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: MODEL, input: texts }),
  });
  const body = await res.json();
  if (!res.ok) {
    const message = JSON.stringify(body);
    if (/maximum input length|too long|context length/i.test(message)) {
      throw new Error("TOO_LONG");
    }
    throw new Error(body?.error?.message ?? `The scoring service returned ${res.status}.`);
  }
  return body.data.sort((x, y) => x.index - y.index).map(d => d.embedding);
}

const dot = (u, v) => u.reduce((sum, x, i) => sum + x * v[i], 0);

// Learn the direction that separates the known human texts from the known AI ones:
// the average step from an AI text to its human counterpart, scaled to unit length.
// It points toward human, so a higher score means more human sounding.
async function learnDirection() {
  const vectors = await embed(examples.flatMap(p => [p.human, p.ai]));
  const human = vectors.filter((_, i) => i % 2 === 0);
  const ai = vectors.filter((_, i) => i % 2 === 1);

  const direction = human[0].map((_, d) =>
    human.reduce((sum, v, p) => sum + v[d] - ai[p][d], 0) / human.length);
  const length = Math.hypot(...direction);
  const unit = direction.map(x => x / length);

  const spreads = human.map((h, i) => dot(h, unit) - dot(ai[i], unit));
  return {
    unit,
    reference: {
      pairs: examples.length,
      typical: +(spreads.reduce((a, b) => a + b) / spreads.length).toFixed(4),
      tooClose: TOO_CLOSE,
      clear: CLEAR,
    },
  };
}

const { unit, reference } = await learnDirection();

async function compare(first, second) {
  const [u, v] = await embed([first, second]);
  return {
    first: { score: dot(u, unit), words: countWords(first) },
    second: { score: dot(v, unit), words: countWords(second) },
    identical: first.trim() === second.trim(),
    reference,
  };
}

const countWords = t => (t.trim() ? t.trim().split(/\s+/).length : 0);

const send = (res, code, body, type) => {
  res.writeHead(code, { "Content-Type": type, "Content-Length": Buffer.byteLength(body) });
  res.end(body);
};
const sendJson = (res, code, value) =>
  send(res, code, JSON.stringify(value), "application/json");

createServer(async (req, res) => {
  if (req.method === "GET" && (req.url === "/" || req.url === "/index.html")) {
    return send(res, 200, page(), "text/html; charset=utf-8");
  }
  if (req.method === "GET" && req.url === "/examples") {
    return sendJson(res, 200, examples);
  }
  if (req.method === "POST" && req.url === "/compare") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let payload;
    try {
      payload = JSON.parse(Buffer.concat(chunks).toString());
    } catch {
      return sendJson(res, 400, { error: "Could not read the request." });
    }
    const { first = "", second = "" } = payload;
    if (!first.trim() || !second.trim()) {
      return sendJson(res, 400, { error: "Both boxes need something in them." });
    }
    try {
      return sendJson(res, 200, await compare(first, second));
    } catch (err) {
      if (err.message === "TOO_LONG") {
        return sendJson(res, 400, {
          error: "That is too long to score. Keep each box under roughly 6,000 words.",
        });
      }
      return sendJson(res, 502, { error: err.message });
    }
  }
  send(res, 404, "Not found", "text/plain");
}).listen(PORT, () => {
  console.log(`Read ${reference.pairs} example pairs. `
    + `An obvious one comes out about ${reference.typical} apart.`);
  console.log(`Open http://localhost:${PORT}`);
});
