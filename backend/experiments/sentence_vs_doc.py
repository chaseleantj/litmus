"""How much does a sentence's score tell you about its text's score?

sentence_scoring.py showed that aggregating per-sentence scores never beats
scoring the whole text. This asks the diagnostic question behind that result:
are sentence scores and document scores even measuring the same thing?

For every text, held out in turn (leave-one-pair-out, axis learned from the
other 15 pairs' whole-text embeddings exactly as production learns it), we
record the text's own document score and the score of each of its sentences
projected onto that same axis. Nothing from a held-out pair enters its fit.

Reported:
  - Pearson r and Spearman rho over all sentences (each sentence paired with
    its parent text's document score). The headline "does a sentence predict
    its document" number.
  - The same at text level: mean-of-sentences vs document score (n = 32).
  - A variance split: how much of the total spread in sentence scores sits
    BETWEEN texts versus WITHIN a text (an ICC). Low between-text share
    means sentence scores are mostly local noise around their text.
  - Sign agreement: how often a sentence lands on the same side of zero as
    its text, and how often a text's sentences are unanimous.
  - Correlation of sentence score with sentence length, to check the axis is
    not partly reading length.

Outputs a two-panel SVG scatter (sentence-level and text-level) next to this
script, written by hand so the experiment stays dependency-free.

Usage: python backend/experiments/sentence_vs_doc.py
Needs OPENROUTER_API_KEY (env var or repo .env); embeddings come from
embedding_cache.json, so a rerun after sentence_scoring.py makes no API
calls. Numbers saved to sentence_vs_doc_results.json.
"""

from __future__ import annotations

import json
import math

from embedding_dims import (
    CACHE_PATH,
    EXPERIMENTS_DIR,
    embed_at_dim,
    learn_direction_from_vectors,
    scoring,
)
from granular_detection import DIM, MODEL, split_sentences
from sentence_scoring import load_pairs, project

RESULTS_PATH = EXPERIMENTS_DIR / "sentence_vs_doc_results.json"
PLOT_PATH = EXPERIMENTS_DIR / "sentence_vs_doc.svg"


# -------------------------------------------------------------------- stats

def mean(xs):
    return sum(xs) / len(xs)


def pearson(xs, ys):
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def ranks(xs):
    """Average ranks, so ties do not distort Spearman."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs, ys):
    return pearson(ranks(xs), ranks(ys))


def fisher_ci(r: float, n: int) -> tuple[float, float]:
    """95% CI via Fisher z. Sentences within a text are not independent, so at
    sentence level this interval is narrower than the truth — read it as a
    best case."""
    if n < 4 or abs(r) >= 1:
        return (r, r)
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    lo, hi = z - 1.96 * se, z + 1.96 * se
    return (math.tanh(lo), math.tanh(hi))


# ----------------------------------------------------------------- plotting
# A hand-written SVG: two panels sharing a style, no plotting library.

W, H = 980, 460
PAD_L, PAD_R, PAD_T, PAD_B = 62, 20, 46, 52
PANEL_W = (W - 40) // 2
HUMAN, AI = "#2f7d64", "#b4552d"


def scatter_panel(
    x0: int,
    points: list[tuple[float, float, str]],
    xlabel: str,
    ylabel: str,
    title: str,
    subtitle: str,
    show_identity: bool,
) -> str:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    lo = min(min(xs), min(ys))
    hi = max(max(xs), max(ys))
    span = (hi - lo) or 1.0
    lo, hi = lo - 0.08 * span, hi + 0.08 * span
    px0, py0 = x0 + PAD_L, PAD_T
    pw, ph = PANEL_W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def sx(v):
        return px0 + (v - lo) / (hi - lo) * pw

    def sy(v):
        return py0 + ph - (v - lo) / (hi - lo) * ph

    out = [
        f'<text x="{x0 + PAD_L}" y="20" class="t">{title}</text>',
        f'<text x="{x0 + PAD_L}" y="36" class="s">{subtitle}</text>',
        f'<rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" class="frame"/>',
    ]
    # Zero lines are the decision boundary in both directions.
    if lo < 0 < hi:
        out.append(f'<line x1="{sx(0):.1f}" y1="{py0}" x2="{sx(0):.1f}" '
                   f'y2="{py0 + ph}" class="zero"/>')
        out.append(f'<line x1="{px0}" y1="{sy(0):.1f}" x2="{px0 + pw}" '
                   f'y2="{sy(0):.1f}" class="zero"/>')
    if show_identity:
        out.append(f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" '
                   f'x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" class="ident"/>')

    # Least-squares fit, drawn across the panel.
    mx, my = mean(xs), mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom:
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        icpt = my - slope * mx
        ya, yb = icpt + slope * lo, icpt + slope * hi
        out.append(f'<line x1="{sx(lo):.1f}" y1="{sy(ya):.1f}" '
                   f'x2="{sx(hi):.1f}" y2="{sy(yb):.1f}" class="fit"/>')

    for vx, vy, cls in points:
        colour = HUMAN if cls == "human" else AI
        out.append(f'<circle cx="{sx(vx):.1f}" cy="{sy(vy):.1f}" r="3.4" '
                   f'fill="{colour}" fill-opacity="0.62"/>')

    # Ticks at a readable step for the data's range.
    step = 0.05 if (hi - lo) < 0.45 else 0.1
    t = math.ceil(lo / step) * step

    def tick(v):  # keeps a rounding-artefact zero from printing as "-0.00"
        return f"{0.0 if abs(v) < 1e-9 else v:+.2f}"
    while t <= hi:
        out.append(f'<line x1="{sx(t):.1f}" y1="{py0 + ph}" x2="{sx(t):.1f}" '
                   f'y2="{py0 + ph + 4}" class="frame"/>')
        out.append(f'<text x="{sx(t):.1f}" y="{py0 + ph + 17}" '
                   f'class="ax mid">{tick(t)}</text>')
        out.append(f'<line x1="{px0 - 4}" y1="{sy(t):.1f}" x2="{px0}" '
                   f'y2="{sy(t):.1f}" class="frame"/>')
        out.append(f'<text x="{px0 - 8}" y="{sy(t):.1f}" '
                   f'class="ax end" dy="3.5">{tick(t)}</text>')
        t += step

    out.append(f'<text x="{px0 + pw / 2:.0f}" y="{H - 8}" '
               f'class="ax mid lab">{xlabel}</text>')
    out.append(f'<text x="0" y="0" class="ax mid lab" transform="translate('
               f'{px0 - 44},{py0 + ph / 2:.0f}) rotate(-90)">{ylabel}</text>')
    return "\n".join(out)


def write_svg(sentence_points, text_points, stats) -> None:
    css = """
      .t { font: 600 13px -apple-system, system-ui, sans-serif; fill: #1c1c1e; }
      .s { font: 400 11px -apple-system, system-ui, sans-serif; fill: #6b6b70; }
      .ax { font: 400 10px -apple-system, system-ui, sans-serif; fill: #8a8a8f; }
      .lab { font-size: 11px; fill: #4a4a4f; }
      .mid { text-anchor: middle; }
      .end { text-anchor: end; }
      .frame { fill: none; stroke: #d8d8dc; stroke-width: 1; }
      .zero { stroke: #c3c3c8; stroke-width: 1; stroke-dasharray: 3 3; }
      .ident { stroke: #b9b9be; stroke-width: 1; stroke-dasharray: 5 4; }
      .fit { stroke: #3a6ea5; stroke-width: 1.6; }
    """
    legend = (
        f'<circle cx="{W - 210}" cy="16" r="3.6" fill="{HUMAN}"/>'
        f'<text x="{W - 202}" y="20" class="s">human version</text>'
        f'<circle cx="{W - 116}" cy="16" r="3.6" fill="{AI}"/>'
        f'<text x="{W - 108}" y="20" class="s">AI version</text>'
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>{css}</style>
<rect width="{W}" height="{H}" fill="#ffffff"/>
{legend}
{scatter_panel(0, sentence_points,
               "document score (whole-text embedding)",
               "sentence score",
               "Every sentence vs its own text",
               f"n = {len(sentence_points)} sentences   "
               f"r = {stats['sentence_level']['pearson_r']:.2f}   "
               f"rho = {stats['sentence_level']['spearman_rho']:.2f}",
               True)}
{scatter_panel(W // 2 + 20, text_points,
               "document score (whole-text embedding)",
               "mean of that text's sentence scores",
               "Text vs the average of its sentences",
               f"n = {len(text_points)} texts   "
               f"r = {stats['text_level']['pearson_r']:.2f}   "
               f"rho = {stats['text_level']['spearman_rho']:.2f}",
               True)}
</svg>
"""
    PLOT_PATH.write_text(svg)


# ------------------------------------------------------------------ pipeline

def main() -> None:
    pairs, source = load_pairs()
    n = len(pairs)
    api_key = scoring.load_api_key()
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

    def embed(texts):
        return embed_at_dim(texts, DIM, api_key, cache, model=MODEL)

    sents = [(split_sentences(ai), split_sentences(h)) for ai, h in pairs]
    docs = embed([t for ai, h in pairs for t in (ai, h)])
    ai_docs, h_docs = docs[0::2], docs[1::2]
    flat = embed([s for pair in sents for text in pair for s in text])
    cursor = 0
    sent_vecs = []
    for ai_s, h_s in sents:
        a = flat[cursor:cursor + len(ai_s)]
        cursor += len(ai_s)
        h = flat[cursor:cursor + len(h_s)]
        cursor += len(h_s)
        sent_vecs.append((a, h))

    # texts[i] = one held-out text: its doc score and its sentences' scores,
    # all read off the fold's leakage-free axis.
    texts = []
    for i in range(n):
        train = [j for j in range(n) if j != i]
        unit, bias = learn_direction_from_vectors(
            [h_docs[j] for j in train], [ai_docs[j] for j in train]
        )
        for cls, doc_vec, s_vecs, s_texts in (
            ("human", h_docs[i], sent_vecs[i][1], sents[i][1]),
            ("ai", ai_docs[i], sent_vecs[i][0], sents[i][0]),
        ):
            texts.append({
                "pair": i,
                "class": cls,
                "doc_score": scoring.dot(doc_vec, unit) - bias,
                "sentence_scores": project(s_vecs, unit, bias),
                "sentence_lengths": [len(s) for s in s_texts],
            })

    sent_points = [
        (t["doc_score"], s, t["class"]) for t in texts for s in t["sentence_scores"]
    ]
    text_points = [
        (t["doc_score"], mean(t["sentence_scores"]), t["class"]) for t in texts
    ]

    sx = [p[0] for p in sent_points]
    sy = [p[1] for p in sent_points]
    tx = [p[0] for p in text_points]
    ty = [p[1] for p in text_points]

    # Variance split: between-text (each text's sentence mean) against
    # within-text (each sentence's deviation from its text's mean).
    grand = mean(sy)
    between = sum(
        len(t["sentence_scores"]) * (mean(t["sentence_scores"]) - grand) ** 2
        for t in texts
    )
    within = sum(
        (s - mean(t["sentence_scores"])) ** 2
        for t in texts
        for s in t["sentence_scores"]
    )

    sign_match = sum(
        (s > 0) == (t["doc_score"] > 0)
        for t in texts
        for s in t["sentence_scores"]
    )
    multi = [t for t in texts if len(t["sentence_scores"]) > 1]
    unanimous = sum(
        len({s > 0 for s in t["sentence_scores"]}) == 1 for t in multi
    )

    lengths = [l for t in texts for l in t["sentence_lengths"]]

    r_s, rho_s = pearson(sx, sy), spearman(sx, sy)
    r_t, rho_t = pearson(tx, ty), spearman(tx, ty)
    stats = {
        "source": source,
        "model": MODEL,
        "dim": DIM,
        "n_pairs": n,
        "n_texts": len(texts),
        "n_sentences": len(sent_points),
        "sentence_level": {
            "pearson_r": r_s,
            "pearson_ci95": list(fisher_ci(r_s, len(sx))),
            "spearman_rho": rho_s,
            "r_squared": r_s**2,
        },
        "text_level": {
            "pearson_r": r_t,
            "pearson_ci95": list(fisher_ci(r_t, len(tx))),
            "spearman_rho": rho_t,
            "r_squared": r_t**2,
        },
        "variance": {
            "between_text_share": between / (between + within),
            "within_text_share": within / (between + within),
            "mean_within_text_sd": mean([
                math.sqrt(
                    sum(
                        (s - mean(t["sentence_scores"])) ** 2
                        for s in t["sentence_scores"]
                    ) / (len(t["sentence_scores"]) - 1)
                )
                for t in multi
            ]),
        },
        "sign_agreement": sign_match / len(sent_points),
        "unanimous_texts": f"{unanimous}/{len(multi)}",
        "sentence_score_vs_length_r": pearson(lengths, sy),
    }

    print(f"Dataset: {n} pairs / {len(texts)} texts / {len(sent_points)} "
          f"sentences from {source}")
    print("Axis: production whole-text direction, leave-one-pair-out\n")
    print(f"Sentence vs its document score:  r = {r_s:+.3f}  "
          f"(95% CI {stats['sentence_level']['pearson_ci95'][0]:+.2f} to "
          f"{stats['sentence_level']['pearson_ci95'][1]:+.2f}), "
          f"rho = {rho_s:+.3f}, R^2 = {r_s ** 2:.2f}")
    print(f"Text mean-of-sentences vs doc:   r = {r_t:+.3f}  "
          f"(95% CI {stats['text_level']['pearson_ci95'][0]:+.2f} to "
          f"{stats['text_level']['pearson_ci95'][1]:+.2f}), "
          f"rho = {rho_t:+.3f}, R^2 = {r_t ** 2:.2f}")
    print(f"\nSentence-score variance: {stats['variance']['between_text_share']:.0%} "
          f"between texts, {stats['variance']['within_text_share']:.0%} within")
    print(f"Mean within-text SD of sentence scores: "
          f"{stats['variance']['mean_within_text_sd']:.3f}")
    print(f"Sentence agrees with its text's sign: {stats['sign_agreement']:.0%}")
    print(f"Texts whose sentences all agree on sign: {stats['unanimous_texts']}")
    print(f"Sentence score vs sentence length: r = "
          f"{stats['sentence_score_vs_length_r']:+.3f}")

    write_svg(sent_points, text_points, stats)
    RESULTS_PATH.write_text(json.dumps(
        {**stats, "texts": texts}, indent=2
    ))
    print(f"\nPlot:    {PLOT_PATH}")
    print(f"Numbers: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
