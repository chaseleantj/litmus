<script lang="ts">
  import { ArrowsLeftRight, Check, Shuffle } from "phosphor-svelte";
  import { api, ApiError } from "./api";
  import { compareState as cs } from "./compareState.svelte";
  import { addPair, library, MIN_PAIRS } from "./library.svelte";
  import { fmtScore, pickDomain, scalePos, tickLabel } from "./scale";
  import { toast } from "./toast";

  interface Props {
    onOpenLibrary: () => void;
    /** True while the library sheet is open: global shortcuts stand down. */
    suspended: boolean;
  }

  let { onOpenLibrary, suspended }: Props = $props();

  let scoring = $state(false);
  let stale = $state(false);
  let error = $state<{ status: number; message: string } | null>(null);

  // "Save as training pair" flow: which text is the human version, and
  // whether the current result has already been saved.
  let saveHuman = $state<"first" | "second">("second");
  let savingPair = $state(false);
  let savedPair = $state(false);

  // Interpretation thresholds (shared with the strip and the verdict copy).
  const TOO_CLOSE = 0.02;
  const CLEAR = 0.1;

  const pair = $derived(cs.mode === "pair");
  // Derived from what was scored, not from what is currently typed: everything
  // else in the result is keyed to cs.lastScored, and a result that described
  // one thing while the verdict described another would be worse than stale.
  const identical = $derived(
    pair && cs.lastScored !== null && cs.lastScored.a.trim() === cs.lastScored.b.trim(),
  );

  // Scoring is meaningless below MIN_PAIRS; while the library is still
  // loading (or failed to load) the server stays the judge via its 409.
  const calibrated = $derived(
    library.loading || library.error !== null || library.examples.length >= MIN_PAIRS,
  );

  interface Marker {
    score: number;
    label: string | null;
    tier: "low" | "high";
    /** Identical texts have no measured score to show — only a verdict. */
    showValue: boolean;
  }

  /** Within this much of an end, anchor a label's edge to its pin rather than
   *  its center: it stays attached and cannot hang off the axis. */
  const EDGE_ZONE = 15;

  /** Two pins closer than this (in % of the scale) would hide each other. */
  const PIN_OVERLAP = 3;

  /** Clear space required between two labels sharing a row. */
  const LABEL_GUTTER = 12;

  let scaleEl = $state<HTMLElement>();
  let tiered = $state(false);

  /**
   * Two labels only need two rows when they would actually collide, which
   * depends on their rendered width — so it has to be measured. Positions are
   * recomputed from the marker data rather than read off the DOM, because
   * `left` is mid-transition for 420ms after every change.
   */
  $effect(() => {
    const el = scaleEl;
    const markers = chart?.markers;
    if (!el || !markers || markers.length < 2) {
      tiered = false;
      return;
    }
    const measure = () => {
      const labels = [...el.querySelectorAll<HTMLElement>(".pin-label")];
      if (labels.length < 2) return;
      const scaleWidth = el.clientWidth;
      const extent = (i: number) => {
        const center = (markers[i].pos / 100) * scaleWidth;
        const width = labels[i].getBoundingClientRect().width;
        if (markers[i].anchor === "start") return [center, center + width];
        if (markers[i].anchor === "end") return [center - width, center];
        return [center - width / 2, center + width / 2];
      };
      const [left, right] = [extent(0), extent(1)].sort((a, b) => a[0] - b[0]);
      tiered = left[1] + LABEL_GUTTER > right[0];
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  });

  const chart = $derived.by(() => {
    let markers: Marker[];
    if (pair) {
      if (!cs.result) return null;
      markers = identical
        ? [{ score: 0, label: null, tier: "low", showValue: false }]
        : [
            { score: cs.result.first, label: "First", tier: "high", showValue: true },
            { score: cs.result.second, label: "Second", tier: "low", showValue: true },
          ];
    } else {
      if (!cs.single) return null;
      markers = [{ score: cs.single.score, label: null, tier: "low", showValue: true }];
    }
    const maxAbs = Math.max(...markers.map((m) => Math.abs(m.score)));
    const domain = pickDomain(maxAbs);
    const pos = (s: number) => scalePos(s, domain);
    const side = (s: number) => (Math.abs(s) < TOO_CLOSE ? "" : s > 0 ? "side-human" : "side-ai");
    const positions = markers.map((m) => pos(m.score));
    // Near-identical scores put the pins on top of each other; nudge them off
    // the strip's centerline in opposite directions so both stay visible.
    const overlapping =
      positions.length === 2 && Math.abs(positions[0] - positions[1]) < PIN_OVERLAP;
    return {
      // The band marks scores near zero, which answers the single-text
      // question. In pair mode the verdict is about the gap between two
      // scores, so the same band there would contradict it.
      band: pair ? null : { left: pos(-TOO_CLOSE), width: pos(TOO_CLOSE) - pos(-TOO_CLOSE) },
      ticks: [-domain, -domain / 2, 0, domain / 2, domain],
      markers: markers.map((m, i) => ({
        ...m,
        pos: positions[i],
        anchor:
          positions[i] < EDGE_ZONE ? "start" : positions[i] > 100 - EDGE_ZONE ? "end" : "",
        split: overlapping ? (m.tier === "high" ? "split-up" : "split-down") : "",
        side: side(m.score),
      })),
    };
  });

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

  // Typing only marks the result stale; scoring runs on Ctrl+Enter, paste
  // into an empty box, or a programmatic trigger (swap, mode toggle,
  // try-example). A counter makes sure a slow old answer can never overwrite
  // a newer one.
  let requestId = 0;

  function clearResults() {
    requestId++;
    cs.lastScored = null;
    cs.result = null;
    cs.single = null;
    cs.lastScoredSingle = null;
    error = null;
    stale = false;
    scoring = false;
  }

  function upToDate(): boolean {
    if (pair) {
      return !!cs.lastScored && cs.lastScored.a === cs.first && cs.lastScored.b === cs.second;
    }
    return cs.lastScoredSingle === cs.first;
  }

  function ready(): boolean {
    return !!(pair ? cs.first.trim() && cs.second.trim() : cs.first.trim());
  }

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
    // Without calibration there is no result to be stale against.
    stale = calibrated && !upToDate();
  }

  function queueRun() {
    if (!calibrated) return;
    if (!ready()) {
      clearResults();
      return;
    }
    if (upToDate()) {
      stale = false;
      return;
    }
    stale = true;
    run();
  }

  async function run() {
    const wasPair = pair;
    const a = cs.first,
      b = cs.second;
    const id = ++requestId;
    scoring = true;
    error = null;
    try {
      if (wasPair) {
        const r = await api.compare(a, b);
        if (id !== requestId) return;
        cs.lastScored = { a, b };
        cs.result = r;
        savedPair = false;
        saveHuman = r.gap >= 0 ? "second" : "first";
      } else {
        const r = await api.score(a);
        if (id !== requestId) return;
        cs.lastScoredSingle = a;
        cs.single = r;
      }
    } catch (err) {
      if (id !== requestId) return;
      // The invariant is "lastScored is set iff a result for it exists"; keeping
      // the old bookkeeping here would make upToDate() true with no result, and
      // both Ctrl+Enter and "Try again" would refuse to re-run.
      cs.result = null;
      cs.single = null;
      cs.lastScored = null;
      cs.lastScoredSingle = null;
      error =
        err instanceof ApiError
          ? { status: err.status, message: err.message }
          : { status: 0, message: err instanceof Error ? err.message : "That did not work. Try again." };
    } finally {
      if (id === requestId) {
        scoring = false;
        stale = false;
      }
    }
  }

  // If the component ever remounts with dirty text (e.g. HMR), score again.
  if (ready() && !upToDate()) {
    queueRun();
  }

  function setMode(mode: "single" | "pair") {
    if (cs.mode === mode) return;
    cs.mode = mode;
    error = null;
    queueRun();
  }

  function swap() {
    if (!pair || (!cs.first.trim() && !cs.second.trim())) return;
    const a = cs.first;
    cs.first = cs.second;
    cs.second = a;
    if (cs.result && cs.lastScored && cs.lastScored.a === cs.second && cs.lastScored.b === cs.first) {
      // The scores just trade places; no need to re-embed.
      cs.result = {
        first: cs.result.second,
        second: cs.result.first,
        gap: -cs.result.gap,
      };
      cs.lastScored = { a: cs.first, b: cs.second };
      saveHuman = saveHuman === "first" ? "second" : "first";
    }
    queueRun();
  }

  function toggleMode() {
    setMode(pair ? "single" : "pair");
  }

  // Score, toggle compare, and swap — available anywhere while the library
  // sheet is closed.
  $effect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (suspended) return;
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
      onOpenLibrary();
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

  async function saveAsPair() {
    if (savingPair || !cs.result) return;
    const human = saveHuman === "first" ? cs.first : cs.second;
    const ai = saveHuman === "first" ? cs.second : cs.first;
    savingPair = true;
    try {
      await addPair({ ai, human });
      savedPair = true;
      toast("success", "Saved as a training pair.");
    } catch (err) {
      toast("error", err instanceof Error ? err.message : "Could not save the pair.");
    } finally {
      savingPair = false;
    }
  }
</script>

<section aria-label="Detect AI writing">
  <div class="inputs" class:pair>
    <div class="field">
      {#if pair}
        <label class="micro-label" for="det-t1">First text</label>
      {/if}
      <textarea
        id="det-t1"
        aria-label={pair ? undefined : "Text to score"}
        bind:value={cs.first}
        oninput={onInput}
        onpaste={onPaste}
        placeholder="Paste something here."
      ></textarea>
    </div>
    {#if pair}
      <div class="field">
        <label class="micro-label" for="det-t2">Second text</label>
        <textarea
          id="det-t2"
          bind:value={cs.second}
          oninput={onInput}
          onpaste={onPaste}
          placeholder="And something else here."
        ></textarea>
      </div>
    {/if}
  </div>

  <div class="field-actions">
    <div class="actions-left">
      <div class="seg" role="group" aria-label="Number of texts">
        <button
          class:active={!pair}
          aria-pressed={!pair}
          title="Score one text (Ctrl+\ toggles)"
          onclick={() => setMode("single")}
        >
          One text
        </button>
        <button
          class:active={pair}
          aria-pressed={pair}
          title="Compare two texts (Ctrl+\ toggles)"
          onclick={() => setMode("pair")}
        >
          Compare two
        </button>
      </div>
      {#if pair}
        <button
          class="btn btn-ghost small"
          onclick={swap}
          disabled={!cs.first.trim() && !cs.second.trim()}
          title="Swap texts (Ctrl+Shift+\)"
        >
          <ArrowsLeftRight size={14} />
          Swap
        </button>
      {/if}
    </div>
    <button
      class="btn btn-ghost small"
      onclick={tryExample}
      disabled={library.loading}
      title="Fill in a text from your training library"
    >
      <Shuffle size={14} />
      Try an example
    </button>
  </div>

  {#if stale && !scoring && calibrated}
    <p class="rescore-hint" aria-live="polite">
      Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to score
    </p>
  {/if}

  <div class="result" class:stale={stale && calibrated && !error} aria-live="polite">
    {#if !calibrated}
      <div class="panel-note">
        <h3 class="serif">Teach it your voice first</h3>
        <p>
          Litmus scores writing against your own. Add
          {library.examples.length === 1 ? "one more pair" : "two pairs"} — an AI draft and your
          version of the same thing — and scoring unlocks.
        </p>
        <button class="btn btn-primary" onclick={onOpenLibrary}>
          {library.examples.length === 1 ? "Add one more pair" : "Open the library"}
        </button>
      </div>
    {:else if error}
      <div class="panel-note" role="alert">
        <h3 class="serif">Couldn’t score that</h3>
        <p class="error-text">{error.message}</p>
        {#if error.status === 409}
          <button class="btn btn-primary" onclick={onOpenLibrary}>Add training pairs</button>
        {:else}
          <button class="btn" onclick={() => queueRun()}>Try again</button>
        {/if}
      </div>
    {:else if chart && verdict}
      <p class="verdict serif">
        {#if verdict.kind === "identical"}
          You pasted the same text twice.
        {:else if verdict.kind === "tie"}
          {pair ? "Too close to call." : "Right on the line — hard to tell."}
        {:else if verdict.kind === "pair-call"}
          The <span class="who human">{verdict.which}</span> text sounds {verdict.strength} more
          human.
        {:else}
          This text sounds {verdict.strength} more
          <span class="who {verdict.side}">{verdict.side === "human" ? "human" : "like AI"}</span>.
        {/if}
      </p>

      <div class="chart" class:tiered>
        <span class="micro-label pole pole-ai" aria-hidden="true">AI</span>
        <div class="scale" bind:this={scaleEl}>
          <div class="litmus-strip strip">
            {#if chart.band}
              <div
                class="tie-band"
                style="left: {chart.band.left}%; width: {chart.band.width}%"
                title="Scores inside this band are too close to call"
              ></div>
            {/if}
          </div>
          {#each chart.ticks as t, i (i)}
            <div
              class="tick"
              class:zero={t === 0}
              style="left: {(i / (chart.ticks.length - 1)) * 100}%"
              aria-hidden="true"
            >
              <span class="micro-label tick-num">{tickLabel(t)}</span>
            </div>
          {/each}
          {#each chart.markers as m, i (i)}
            <span class="pin {m.side} {m.split}" style="left: {m.pos}%"></span>
            <span
              class="pin-label {tiered && m.tier === 'high' ? 'high' : 'low'} {m.anchor}"
              style="left: {m.pos}%"
            >
              {#if m.label}<span class="micro-label pin-name">{m.label}</span>{/if}
              {#if m.showValue}<span class="pin-value">{fmtScore(m.score)}</span>{/if}
            </span>
          {/each}
        </div>
        <span class="micro-label pole pole-human" aria-hidden="true">Human</span>
      </div>

      {#if pair && verdict.kind !== "identical"}
        <div class="result-foot">
          {#if savedPair}
            <span class="saved-note"><Check size={14} weight="bold" /> Saved to your library</span>
          {:else}
            <span class="save">
              <span class="save-label">Human version:</span>
              <span class="seg" role="group" aria-label="Which text is the human version">
                <button class:active={saveHuman === "first"} onclick={() => (saveHuman = "first")}
                  >First</button
                >
                <button class:active={saveHuman === "second"} onclick={() => (saveHuman = "second")}
                  >Second</button
                >
              </span>
              <button class="btn btn-primary small" onclick={saveAsPair} disabled={savingPair}>
                {#if savingPair}<span class="spinner"></span>{/if}
                Save as pair
              </button>
            </span>
          {/if}
        </div>
      {/if}
    {:else if scoring}
      <div class="loading-strip">
        <span class="sr-only">Scoring…</span>
        <div class="skeleton" aria-hidden="true"></div>
      </div>
    {:else}
      <div class="panel-note">
        <p>
          {#if pair}
            Paste two pieces of writing and press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to see which one
            sounds more like you.
          {:else}
            Paste a piece of writing and press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to see where it
            lands between AI and your voice.
          {/if}
        </p>
      </div>
    {/if}
  </div>
</section>

<style>
  .inputs {
    display: grid;
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .inputs.pair {
    grid-template-columns: 1fr 1fr;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .field textarea {
    min-height: 200px;
  }

  .field-actions {
    display: flex;
    align-items: center;
    /* flex-end + auto margin rather than space-between: when the row wraps on
       narrow screens the trailing button stays right-aligned. */
    justify-content: flex-end;
    gap: 12px;
    margin-top: 10px;
  }

  .actions-left {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-right: auto;
  }

  /* .seg (segmented control) styles are shared — see app.css. */

  .rescore-hint {
    margin: 16px 0 0;
    text-align: center;
    font-size: var(--text-body);
    color: var(--ink-faint);
  }

  .result {
    max-width: 700px;
    margin: 30px auto 0;
    padding-top: 28px;
    border-top: 1px solid var(--border);
    transition: opacity 200ms var(--ease);
  }

  .result.stale {
    opacity: 0.45;
  }

  .verdict {
    font-family: var(--font-serif);
    font-size: var(--text-display);
    font-weight: 500;
    letter-spacing: -0.01em;
    line-height: 1.35;
    text-align: center;
    text-wrap: balance;
  }

  .who.human {
    color: var(--human);
  }

  .who.ai {
    color: var(--ai);
  }

  /* ---------- The litmus strip ---------- */
  .chart {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 32px;
    padding: 0 4px;
    transition: margin-top var(--speed) var(--ease);
  }

  /* Room for the raised row, added only when a label actually uses it. */
  .chart.tiered {
    margin-top: 64px;
  }

  .pole {
    flex-shrink: 0;
    padding-bottom: 26px; /* optically center against strip + tick numbers */
  }

  .pole-ai {
    color: var(--ai);
  }

  .pole-human {
    color: var(--human);
  }

  .scale {
    position: relative;
    flex: 1;
    padding-bottom: 26px;
  }

  /* The strip's look is the shared .litmus-strip (app.css); only the
     tie-band clipping is local. */
  .strip {
    overflow: hidden;
  }

  /* The too-close-to-call zone: neutral paper, dashed edges. */
  .tie-band {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--surface);
    border-left: 1px dashed var(--border-strong);
    border-right: 1px dashed var(--border-strong);
  }

  .tick {
    position: absolute;
    top: 16px;
    width: 1px;
    height: 5px;
    background: var(--border-strong);
    transform: translateX(-0.5px);
  }

  .tick.zero {
    background: var(--ink-faint);
  }

  .tick-num {
    position: absolute;
    top: 7px;
    left: 50%;
    transform: translateX(-50%);
    color: var(--ink-faint);
  }

  .pin {
    position: absolute;
    top: 7px; /* strip center: 12px strip + 1px borders */
    width: 15px;
    height: 15px;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    background: var(--ink-secondary);
    border: 2.5px solid var(--surface);
    box-shadow: 0 1px 4px hsl(var(--ink-hsl) / 0.3);
    transition:
      left var(--speed-slow) var(--ease),
      background 200ms var(--ease);
  }

  .pin.side-ai {
    background: var(--ai);
  }

  .pin.side-human {
    background: var(--human);
  }

  /* Coincident scores: straddle the strip so both dots stay readable. */
  .pin.split-up {
    top: 0;
  }

  .pin.split-down {
    top: 14px;
  }

  .pin-label {
    position: absolute;
    transform: translateX(-50%);
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    white-space: nowrap;
    transition: left var(--speed-slow) var(--ease);
  }

  /* Near an end there is no room to center on the pin, so the label hangs from
     the pin's side instead — still attached, never off the axis. */
  .pin-label.start {
    transform: translateX(0);
  }

  .pin-label.end {
    transform: translateX(-100%);
  }

  .pin-label.low {
    bottom: calc(100% + 12px);
  }

  /* 24px of clearance: the tiers were within a pixel of touching at 18px. */
  .pin-label.high {
    bottom: calc(100% + 36px);
  }

  /* The value is the measurement, the name is scaffolding — so the number
     carries the weight and the label recedes to the axis's own colour. */
  .pin-name {
    font-weight: 500;
    color: var(--ink-faint);
  }

  .pin-value {
    font-size: var(--text-micro);
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }

  /* ---------- Result footer ---------- */
  .result-foot {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    /* Holds the row's height when the save controls become a one-line note. */
    min-height: 28px;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }

  .save {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    flex-wrap: wrap;
  }

  .save-label {
    font-size: var(--text-body);
    color: var(--ink-secondary);
  }

  .saved-note {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-body);
    font-weight: 500;
    color: var(--ink-secondary);
  }

  /* ---------- Notes & states ---------- */
  /* The panel itself is shared (app.css); the result column owns its spacing,
     which is tighter than in a card because the rule above already separates. */
  .result :global(.panel-note) {
    padding: 20px 0 16px;
  }

  .loading-strip {
    padding: 74px 22px 46px;
  }

  /* Stands in for the litmus strip while scoring: same shape, no reading. */
  .skeleton {
    height: 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
  }

  @media (max-width: 760px) {
    .inputs.pair {
      grid-template-columns: 1fr;
    }

    .field-actions {
      flex-wrap: wrap;
    }
  }
</style>
