<script lang="ts">
  // Legacy reassembly. Feature logic (single/pair modes, calibration gate,
  // shared compareState, Ctrl+Enter scoring, shortcuts) is the current one;
  // the presentation is restored from history:
  //   - intro lede + "Try an example" top button, word counters, hint row,
  //     zone-block pair chart with flag markers and the three-part legend,
  //     result card chrome, verbose save-as-pair sentence: 745fda9.
  //   - single-text baseline chart with dot pin and "More like AI"/"More
  //     human" axis labels, X close on the second field, "Compare two texts"
  //     ghost button: 774fad4^ (pre-library-sheet).
  import {
    clearResults,
    compareState as cs,
    markStale,
    queueRun,
    ready,
    savePair,
    setMode,
    swap,
    toggleMode,
    upToDate,
  } from "./compareState.svelte";
  import { isCalibrated, library, MIN_PAIRS } from "./library.svelte";

  interface Props {
    onGoExamples: () => void;
  }

  let { onGoExamples }: Props = $props();

  // Interpretation thresholds (shared with the chart and the verdict copy).
  const TOO_CLOSE = 0.02;
  const CLEAR = 0.1;

  const pair = $derived(cs.mode === "pair");
  const identical = $derived(
    pair && cs.lastScored !== null && cs.lastScored.a.trim() === cs.lastScored.b.trim(),
  );

  const calibrated = $derived(isCalibrated());

  const words = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
  const w1 = $derived(words(cs.first));
  const w2 = $derived(words(cs.second));
  const wordLabel = (n: number) => (n === 1 ? "1 word" : `${n.toLocaleString()} words`);

  /**
   * Pair chart (745fda9): the first text is the anchor at the centre; the
   * second is placed by its distance from it, positive to the right (more
   * human). The span widens to keep the marker on the bar for large gaps.
   */
  const pairChart = $derived.by(() => {
    if (!pair || !cs.result) return null;
    const d = cs.result.gap;
    const span = Math.max(0.3, Math.abs(d) * 1.18, CLEAR * 2.4);
    const flat = identical || Math.abs(d) < TOO_CLOSE;
    return {
      pos2: identical ? 50 : (0.5 + d / (2 * span)) * 100,
      side: flat ? "" : d > 0 ? "side-human" : "side-ai",
    };
  });

  /**
   * Single chart (774fad4^): one marker floats on a fixed symmetric scale;
   * the domain is the smallest round span that fits the score with headroom.
   */
  const DOMAINS = [0.2, 0.3, 0.4, 0.5, 0.75, 1];

  const singleChart = $derived.by(() => {
    if (pair || !cs.single) return null;
    const s = cs.single.score;
    const domain = DOMAINS.find((d) => d >= Math.abs(s) * 1.05) ?? DOMAINS[DOMAINS.length - 1];
    return {
      ticks: [-domain, -domain / 2, 0, domain / 2, domain],
      pos: (0.5 + Math.max(-1, Math.min(1, s / domain)) / 2) * 100,
      side: Math.abs(s) < TOO_CLOSE ? "" : s > 0 ? "side-human" : "side-ai",
    };
  });

  const tickLabel = (v: number) => (v > 0 ? "+" : "") + String(parseFloat(v.toFixed(3)));

  type Verdict =
    | { kind: "identical" }
    | { kind: "tie" }
    | { kind: "pair-call"; which: "first" | "second"; strength: "clearly" | "a little" }
    | { kind: "single-call"; side: "human" | "ai"; strength: "clearly" | "a little" };
  const verdict = $derived.by<Verdict | null>(() => {
    if (pair) {
      if (!cs.result) return null;
      if (identical) return { kind: "identical" };
      const g = cs.result.gap;
      if (Math.abs(g) < TOO_CLOSE) return { kind: "tie" };
      return {
        kind: "pair-call",
        which: g > 0 ? "second" : "first",
        strength: Math.abs(g) >= CLEAR ? "clearly" : "a little",
      };
    }
    if (!cs.single) return null;
    const s = cs.single.score;
    if (Math.abs(s) < TOO_CLOSE) return { kind: "tie" };
    return {
      kind: "single-call",
      side: s > 0 ? "human" : "ai",
      strength: Math.abs(s) >= CLEAR ? "clearly" : "a little",
    };
  });

  // Set in paste (value still pre-insert), consumed in the following input
  // once bind:value has caught up — microtasks alone race the bind.
  let pasteIntoEmpty = false;

  function onPaste(e: ClipboardEvent) {
    const el = e.currentTarget as HTMLTextAreaElement;
    const pasted = e.clipboardData?.getData("text") ?? "";
    pasteIntoEmpty = !el.value.trim() && !!pasted.trim();
  }

  function onInput() {
    if (!ready()) {
      clearResults();
      pasteIntoEmpty = false;
      return;
    }
    if (pasteIntoEmpty) {
      pasteIntoEmpty = false;
      queueRun();
      return;
    }
    markStale();
  }

  // If the component ever remounts with dirty text (e.g. a tab visit), score again.
  if (ready() && !upToDate()) {
    queueRun();
  }

  // Score, toggle compare, and swap — available anywhere on this tab.
  $effect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key === "Enter") {
        e.preventDefault();
        queueRun();
        return;
      }
      // Backslash (code, not key) so Shift+\ still matches on layouts where
      // the shifted glyph is "|".
      if (e.code === "Backslash") {
        e.preventDefault();
        if (e.shiftKey) swap();
        else toggleMode();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function tryExample() {
    if (library.examples.length < MIN_PAIRS) {
      onGoExamples();
      return;
    }
    const p = library.examples[Math.floor(Math.random() * library.examples.length)];
    const flip = Math.random() < 0.5;
    if (pair) {
      cs.first = flip ? p.ai : p.human;
      cs.second = flip ? p.human : p.ai;
    } else {
      cs.first = flip ? p.ai : p.human;
    }
    queueRun();
  }

  const fmt = (v: number) => v.toFixed(3);
</script>

<section aria-label="Compare texts">
  <div class="intro">
    <p class="lede">
      {#if pair}
        Paste two pieces of writing and this will tell you which one sounds more like a person. It
        compares them against each other, so it can't tell you much about one piece on its own.
      {:else}
        Paste a piece of writing and this will tell you how much it sounds like a person. The score
        comes from comparing it against your own training examples.
      {/if}
    </p>
    <button class="btn" onclick={tryExample} disabled={library.loading}>Try an example</button>
  </div>

  <div class="inputs" class:pair>
    <div class="field">
      <div class="field-head">
        <label for="cmp-t1">
          {#if pair}First text <span class="role">stays put</span>{:else}Text{/if}
        </label>
      </div>
      <textarea
        id="cmp-t1"
        bind:value={cs.first}
        oninput={onInput}
        onpaste={onPaste}
        placeholder="Paste something here."
      ></textarea>
      <div class="meta">{wordLabel(w1)}</div>
    </div>
    {#if pair}
      <div class="field">
        <div class="field-head">
          <label for="cmp-t2">Second text <span class="role">moves</span></label>
          <button
            class="icon-btn close-second"
            aria-label="Back to a single text"
            title="Back to a single text (Ctrl+\)"
            onclick={() => setMode("single")}
          >
            ×
          </button>
        </div>
        <textarea
          id="cmp-t2"
          bind:value={cs.second}
          oninput={onInput}
          onpaste={onPaste}
          placeholder="And something else here."
        ></textarea>
        <div class="meta">{wordLabel(w2)}</div>
      </div>
    {/if}
  </div>

  <div class="hint-row">
    <p class="hint">
      {#if pair}
        Fill both boxes, then press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to score.
      {:else}
        Fill the box, then press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to score.
      {/if}
    </p>
    {#if pair}
      <button
        class="btn btn-ghost small"
        onclick={swap}
        disabled={!cs.first.trim() && !cs.second.trim()}
        title="Swap texts (Ctrl+Shift+\)"
      >
        Swap texts
      </button>
    {:else}
      <button
        class="btn btn-ghost small"
        onclick={() => setMode("pair")}
        title="Compare two texts (Ctrl+\)"
      >
        Compare two texts
      </button>
    {/if}
  </div>

  <div class="result card" class:stale={cs.stale && calibrated && !cs.error} aria-live="polite">
    {#if !calibrated}
      <div class="note" role="status">
        <p>
          The detector needs at least {MIN_PAIRS} training pairs before it can score anything.
          {#if library.examples.length === 1}You have one — add one more.{/if}
        </p>
        <button class="btn" onclick={onGoExamples}>Add training examples</button>
      </div>
    {:else if cs.error}
      <div class="note error-note" role="alert">
        <p>{cs.error.message}</p>
        {#if cs.error.status === 409}
          <button class="btn" onclick={onGoExamples}>Add training examples</button>
        {:else}
          <button class="btn" onclick={() => queueRun()}>Try again</button>
        {/if}
      </div>
    {:else if verdict && (pairChart || singleChart)}
      <p class="verdict">
        {#if verdict.kind === "identical"}
          You have pasted the same text twice.
        {:else if verdict.kind === "tie"}
          {pair ? "Too close to call." : "Right on the line — hard to tell."}
        {:else if verdict.kind === "pair-call"}
          The <span class="side-human-word">{verdict.which}</span> text sounds {verdict.strength} more
          human.
        {:else}
          This text sounds {verdict.strength} more
          <span class="who {verdict.side}">{verdict.side === "human" ? "human" : "like AI"}</span>.
        {/if}
      </p>

      {#if pairChart}
        <div class="chart">
          <div class="frame">
            <div class="zones"></div>
            <div class="marker m1" style="left: 50%"><div class="flag">First</div></div>
            <div class="marker m2 {pairChart.side}" style="left: {pairChart.pos2}%">
              <div class="flag">Second</div>
            </div>
          </div>
          <div class="ends">
            <span class="left">&larr; sounds more like AI<br />than the first</span>
            <span class="mid">anything in the middle<br />is hard to tell apart</span>
            <span class="right">sounds more human<br />than the first &rarr;</span>
          </div>
        </div>
      {:else if singleChart && cs.single}
        <div class="single-chart">
          <div class="plot">
            <div class="baseline"></div>
            {#each singleChart.ticks as t, i (i)}
              <div
                class="ax-tick"
                class:zero={t === 0}
                style="left: {(i / (singleChart.ticks.length - 1)) * 100}%"
              >
                <span class="ax-num">{tickLabel(t)}</span>
              </div>
            {/each}
            <span class="pin {singleChart.side}" style="left: {singleChart.pos}%"></span>
          </div>
          <div class="axis">
            <span class="axis-ai">More like AI</span>
            <span class="axis-human">More human</span>
          </div>
        </div>
      {/if}

      <div class="result-foot">
        <span class="scores num">
          {#if pair && cs.result}
            first {fmt(cs.result.first)} &middot; second {fmt(cs.result.second)} &middot; gap
            {cs.result.gap > 0 ? "+" : ""}{fmt(cs.result.gap)}
          {:else if cs.single}
            score {cs.single.score > 0 ? "+" : ""}{fmt(cs.single.score)}
          {/if}
        </span>
        {#if pair && verdict.kind !== "identical"}
          <span class="save-pair">
            {#if cs.savedPair}
              <span class="saved-note">Saved to training examples.</span>
            {:else}
              <span class="save-note">
                Saves the <span class="side-human-word">{cs.saveHuman}</span> text as the human
                version &middot;
                <button
                  class="linkish"
                  onclick={() => (cs.saveHuman = cs.saveHuman === "first" ? "second" : "first")}
                >
                  switch
                </button>
              </span>
              <button class="btn small" onclick={savePair} disabled={cs.savingPair}>
                {#if cs.savingPair}<span class="spinner spinner-dark"></span>{/if}
                Add as training pair
              </button>
            {/if}
          </span>
        {/if}
      </div>
    {:else if cs.scoring}
      <div class="chart"><div class="zone-skeleton"></div></div>
    {:else}
      <div class="note">
        <p>
          {#if pair}
            The first text stays in the middle. The second one slides right if it sounds more like
            a person, and left if it sounds more like AI.
          {:else}
            Paste a piece of writing and press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to score it. The
            marker shows how human it sounds.
          {/if}
        </p>
      </div>
    {/if}
  </div>
</section>

<style>
  .intro {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    flex-wrap: wrap;
    margin-bottom: 20px;
  }

  .lede {
    max-width: 62ch;
    color: var(--ink-secondary);
  }

  .inputs {
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .inputs.pair {
    grid-template-columns: 1fr 1fr;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-head {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 22px;
  }

  .field-head label {
    font-size: 13px;
    font-weight: 600;
  }

  .field-head label .role {
    font-weight: 400;
    color: var(--ink-faint);
  }

  .close-second {
    margin-left: auto;
    width: 22px;
    height: 22px;
    font-size: 16px;
    line-height: 1;
  }

  .field textarea {
    min-height: 190px;
  }

  .meta {
    font-size: 12px;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
  }

  .hint-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 10px;
  }

  .hint {
    font-size: 12.5px;
    color: var(--ink-faint);
  }

  .result {
    margin-top: 24px;
    padding: 24px 24px 22px;
    transition: opacity 200ms var(--ease);
  }

  .result.stale {
    opacity: 0.45;
  }

  .verdict {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.012em;
  }

  .side-human-word {
    color: var(--human);
  }

  .who.human {
    color: var(--human);
  }

  .who.ai {
    color: var(--ai);
  }

  /* ---------- Pair chart: zone block with flag markers (745fda9) ---------- */
  .chart {
    margin-top: 38px;
  }

  .frame {
    position: relative;
  }

  .zones {
    position: relative;
    height: 46px;
    border-radius: 6px;
    overflow: hidden;
    background: linear-gradient(
      to right,
      var(--ai-soft),
      var(--zone-quiet) 44% 56%,
      var(--human-soft)
    );
  }

  .marker {
    position: absolute;
    top: -14px;
    bottom: -14px;
    width: 2px;
    transform: translateX(-1px);
    background: var(--ink-secondary);
  }

  .marker.m2 {
    transition:
      left 420ms var(--ease),
      background-color 200ms var(--ease);
  }

  .marker.m2.side-ai {
    background: var(--ai);
  }

  .marker.m2.side-human {
    background: var(--human);
  }

  .flag {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    white-space: nowrap;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 5px;
    color: #fff;
    background: var(--ink-secondary);
  }

  .marker.m1 .flag {
    bottom: calc(100% + 5px);
  }

  .marker.m2 .flag {
    top: calc(100% + 5px);
  }

  .marker.m2.side-ai .flag {
    background: var(--ai);
  }

  .marker.m2.side-human .flag {
    background: var(--human);
  }

  /* Clearance below the bar for the Second flag, which hangs under it. */
  .ends {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 16px;
    margin-top: 48px;
    font-size: 12px;
    color: var(--ink-secondary);
  }

  .ends .left {
    color: var(--ai);
  }

  .ends .mid {
    color: var(--ink-faint);
    text-align: center;
  }

  .ends .right {
    text-align: right;
    color: var(--human);
  }

  /* ---------- Single chart: baseline with a dot pin (774fad4^) ---------- */
  .single-chart {
    margin-top: 10px;
    padding: 50px 8px 0;
  }

  .plot {
    position: relative;
    height: 1px;
  }

  .baseline {
    position: absolute;
    inset: 0;
    background: var(--border-strong);
  }

  .ax-tick {
    position: absolute;
    top: 0;
    width: 1px;
    height: 7px;
    background: var(--border-strong);
    transform: translateX(-0.5px);
  }

  .ax-tick.zero {
    height: 11px;
    background: var(--ink-faint);
  }

  .ax-num {
    position: absolute;
    top: 15px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 11px;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
  }

  .pin {
    position: absolute;
    top: 0;
    width: 13px;
    height: 13px;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    background: var(--ink-secondary);
    border: 2px solid var(--surface);
    box-shadow: 0 1px 4px rgba(33, 31, 28, 0.25);
    transition:
      left 420ms var(--ease),
      background 200ms var(--ease);
  }

  .pin.side-ai {
    background: var(--ai);
  }

  .pin.side-human {
    background: var(--human);
  }

  .axis {
    display: flex;
    justify-content: space-between;
    margin-top: 44px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .axis-ai {
    color: var(--ai);
  }

  .axis-human {
    color: var(--human);
  }

  /* ---------- Result footer ---------- */
  .result-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }

  .scores {
    font-size: 12.5px;
    color: var(--ink-faint);
  }

  .num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  .save-pair {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .save-note,
  .saved-note {
    font-size: 12.5px;
    color: var(--ink-faint);
  }

  .linkish {
    appearance: none;
    border: none;
    background: none;
    padding: 0;
    font-size: inherit;
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
    cursor: pointer;
  }

  .note,
  .error-note {
    padding: 30px 0 26px;
    text-align: center;
  }

  .note p,
  .error-note p {
    margin: 0 auto;
    max-width: 48ch;
    color: var(--ink-secondary);
    font-size: 14px;
  }

  .note .btn,
  .error-note .btn {
    margin-top: 14px;
  }

  .error-note p {
    color: var(--human);
  }

  .zone-skeleton {
    height: 46px;
    border-radius: 6px;
    background: var(--zone-quiet);
  }

  @media (prefers-reduced-motion: no-preference) {
    .zone-skeleton {
      animation: pulse 1.3s ease-in-out infinite;
    }
  }

  @keyframes pulse {
    50% {
      opacity: 0.55;
    }
  }

  @media (max-width: 760px) {
    .inputs.pair {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 700px) {
    .ends {
      grid-template-columns: 1fr 1fr;
    }

    .ends .mid {
      display: none;
    }
  }
</style>
