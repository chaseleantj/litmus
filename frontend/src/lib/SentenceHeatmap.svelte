<script lang="ts">
  import { compareState as cs } from "./compareState.svelte";
  import type { AnalyzeResult } from "./types";

  interface Props {
    /** The exact text that was analyzed (spans index into it). */
    text: string;
    analysis: AnalyzeResult;
  }

  let { text, analysis }: Props = $props();

  type Approach = "proj" | "match";

  const APPROACHES: Record<Approach, { name: string; caption: string }> = {
    proj: {
      name: "Axis",
      caption:
        "Each sentence projected onto your human–AI axis. Shading ranks sentences within this text.",
    },
    match: {
      name: "Match",
      caption:
        "Each sentence matched against your example sentences. Zero is neutral, so shading is absolute.",
    },
  };

  const split = $derived(cs.analysisView === "split");
  const shown = $derived<Approach[]>(split ? ["proj", "match"] : [cs.analysisView as Approach]);

  const docScore = (a: Approach) => (a === "proj" ? analysis.proj_score : analysis.match_score);

  /** Signed, three decimals — same format as the litmus strip's pins. */
  const fmtScore = (s: number) => (s > 0 ? "+" : "") + s.toFixed(3);

  /** The text as a full-coverage segment list: sentences plus the untinted
   *  gaps between them (separators the splitter consumed). */
  const segments = $derived.by(() => {
    const segs: { text: string; idx: number | null }[] = [];
    let pos = 0;
    analysis.sentences.forEach((s, i) => {
      if (s.start > pos) segs.push({ text: text.slice(pos, s.start), idx: null });
      segs.push({ text: text.slice(s.start, s.end), idx: i });
      pos = s.end;
    });
    if (pos < text.length) segs.push({ text: text.slice(pos), idx: null });
    return segs;
  });

  /** A "match" score this size is a strong pull (the experiment's observed
   *  sentence scores average |0.044| and top out near 0.14). Flooring the
   *  scale here keeps the shading honest: a text whose strongest sentence is
   *  barely off zero tints faintly instead of being amplified to full. */
  const MATCH_FULL_TINT_AT = 0.05;

  /**
   * Display weights in -1 (AI) … +1 (human). "match" scores are zero-centered
   * and absolute, so they are scaled around 0 (floored — see above). "proj"
   * scores share a whole-document offset, so they are centered on the text's
   * own median — a relative ranking, which is what the caption says.
   */
  function weights(approach: Approach): number[] {
    const vals = analysis.sentences.map((s) => s[approach]);
    let center = 0;
    if (approach === "proj") {
      const sorted = [...vals].sort((a, b) => a - b);
      const n = sorted.length;
      center = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
    }
    let scale = Math.max(...vals.map((v) => Math.abs(v - center)));
    if (approach === "match") scale = Math.max(scale, MATCH_FULL_TINT_AT);
    if (scale < 1e-9) return vals.map(() => 0);
    return vals.map((v) => Math.max(-1, Math.min(1, (v - center) / scale)));
  }

  const weightsByApproach = $derived({ proj: weights("proj"), match: weights("match") });

  /** Strongest tint: the pole colour at this share over the card surface.
   *  Held to 40% so --ink stays comfortably readable on top. */
  const MAX_TINT = 40;

  function tint(w: number): string {
    if (Math.abs(w) < 0.05) return "transparent";
    const pole = w > 0 ? "var(--human)" : "var(--ai)";
    return `color-mix(in srgb, ${pole} ${(Math.abs(w) * MAX_TINT).toFixed(1)}%, transparent)`;
  }

  // ---- Hover tooltip: one floating readout showing both exact scores. ----
  let hovered = $state<number | null>(null);
  let tipX = $state(0);
  let tipY = $state(0);

  function onMove(e: MouseEvent) {
    // Keep the tooltip on-screen near the right and bottom edges.
    tipX = Math.min(e.clientX + 14, window.innerWidth - 240);
    tipY = Math.min(e.clientY + 18, window.innerHeight - 88);
  }

  function onEnter(e: MouseEvent, idx: number) {
    // Position first: an enter without a following move (e.g. the page
    // scrolling under a stationary cursor) must not show the tip at 0,0.
    onMove(e);
    hovered = idx;
  }

  /** Exact values get one more decimal than the headline scores: sentence
   *  scores are smaller and often differ only in the fourth place. */
  const fmtExact = (s: number) => (s > 0 ? "+" : "") + s.toFixed(4);
</script>

<div class="heatmap" class:split>
  {#each shown as approach (approach)}
    <div class="panel card">
      <div class="panel-head">
        <span class="micro-label">{APPROACHES[approach].name}</span>
        <span
          class="doc-score"
          class:pos={docScore(approach) > 0}
          class:neg={docScore(approach) < 0}
          title="This approach's score for the whole text"
        >
          {fmtScore(docScore(approach))}
        </span>
      </div>
      <div class="passage">
        {#each segments as seg, si (si)}{#if seg.idx === null}{seg.text}{:else}<span
              class="sent"
              class:dim={hovered !== null && hovered !== seg.idx}
              style="background: {tint(weightsByApproach[approach][seg.idx])}"
              onmouseenter={(e) => onEnter(e, seg.idx as number)}
              onmouseleave={() => (hovered = null)}
              onmousemove={onMove}
              role="mark">{seg.text}</span>{/if}{/each}
      </div>
      <p class="caption">
        {#if approach === "proj" && analysis.sentences.length === 1}
          One sentence — a within-text ranking needs more than one, so nothing is shaded.
        {:else}
          {APPROACHES[approach].caption}
        {/if}
      </p>
    </div>
  {/each}
</div>

{#if hovered !== null}
  <div class="tip" style="left: {tipX}px; top: {tipY}px" role="status">
    <span class="tip-row">
      <span class="micro-label">Axis</span>
      <span class="tip-val">{fmtExact(analysis.sentences[hovered].proj)}</span>
    </span>
    <span class="tip-row">
      <span class="micro-label">Match</span>
      <span class="tip-val">{fmtExact(analysis.sentences[hovered].match)}</span>
    </span>
  </div>
{/if}

<style>
  .heatmap {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .heatmap.split {
    grid-template-columns: 1fr 1fr;
  }

  .panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 14px 16px 12px;
  }

  .panel-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
  }

  .doc-score {
    font-size: var(--text-body);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--ink-secondary);
  }

  .doc-score.pos {
    color: var(--human);
  }

  .doc-score.neg {
    color: var(--ai);
  }

  .passage {
    font-size: var(--text-content);
    line-height: 1.75;
    white-space: pre-wrap;
    overflow-wrap: break-word;
    /* Long pastes scroll inside the card instead of stretching the page. */
    max-height: 340px;
    overflow-y: auto;
  }

  .sent {
    border-radius: 3px;
    padding: 1.5px 0;
    /* Each wrapped line keeps its own rounded tint. */
    -webkit-box-decoration-break: clone;
    box-decoration-break: clone;
    transition: opacity var(--speed) var(--ease);
  }

  /* Hovering one sentence quiets the rest, so its tint reads in isolation. */
  .sent.dim {
    opacity: 0.45;
  }

  .caption {
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    font-size: var(--text-micro);
    line-height: 1.5;
    color: var(--ink-faint);
  }

  .tip {
    position: fixed;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 132px;
    padding: 8px 11px;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-toast);
    pointer-events: none;
  }

  .tip-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 14px;
  }

  .tip-val {
    font-size: var(--text-body);
    font-variant-numeric: tabular-nums;
    color: var(--ink);
  }

  @media (max-width: 760px) {
    .heatmap.split {
      grid-template-columns: 1fr;
    }
  }
</style>
