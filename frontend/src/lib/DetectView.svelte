<script lang="ts">
  import { ArrowsLeftRight, Check, Columns, Shuffle, X } from "phosphor-svelte";
  import { api, ApiError } from "./api";
  import { compareState as cs, persistDrafts } from "./compareState.svelte";
  import { toast } from "./toast";

  interface Props {
    onGoExamples: () => void;
  }

  let { onGoExamples }: Props = $props();

  let scoring = $state(false);
  let stale = $state(false);
  let error = $state<{ status: number; message: string } | null>(null);
  let loadingExample = $state(false);

  // "Save as training pair" flow: which text is the human version, and
  // whether the current result has already been saved.
  let saveHuman = $state<"first" | "second">("second");
  let savingPair = $state(false);
  let savedPair = $state(false);

  // Interpretation thresholds (shared with the chart and the verdict copy).
  const TOO_CLOSE = 0.02;
  const CLEAR = 0.1;

  const words = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);
  const w1 = $derived(words(cs.first));
  const w2 = $derived(words(cs.second));
  const wordLabel = (n: number) => (n === 1 ? "1 word" : `${n.toLocaleString()} words`);

  const pair = $derived(cs.mode === "pair");
  const identical = $derived(
    pair && cs.first.trim().length > 0 && cs.first.trim() === cs.second.trim(),
  );

  /**
   * Both markers float freely on a fixed symmetric scale. The domain is the
   * smallest round span that fits every score with headroom, so ticks stay
   * at clean values while large scores never leave the axis.
   */
  const DOMAINS = [0.2, 0.3, 0.4, 0.5, 0.75, 1];

  interface Marker {
    score: number;
    label: string | null;
    tier: "low" | "high";
  }

  const chart = $derived.by(() => {
    let markers: Marker[];
    if (pair) {
      if (!cs.result) return null;
      markers = identical
        ? [{ score: 0, label: null, tier: "low" }]
        : [
            { score: cs.result.first, label: "First", tier: "high" },
            { score: cs.result.second, label: "Second", tier: "low" },
          ];
    } else {
      if (!cs.single) return null;
      markers = [{ score: cs.single.score, label: null, tier: "low" }];
    }
    const maxAbs = Math.max(...markers.map((m) => Math.abs(m.score)));
    const domain = DOMAINS.find((d) => d >= maxAbs * 1.05) ?? DOMAINS[DOMAINS.length - 1];
    const pos = (s: number) => (0.5 + Math.max(-1, Math.min(1, s / domain)) / 2) * 100;
    const side = (s: number) => (Math.abs(s) < TOO_CLOSE ? "" : s > 0 ? "side-human" : "side-ai");
    return {
      ticks: [-domain, -domain / 2, 0, domain / 2, domain],
      markers: markers.map((m) => ({ ...m, pos: pos(m.score), side: side(m.score) })),
    };
  });

  const tickLabel = (v: number) =>
    (v > 0 ? "+" : "") + String(parseFloat(v.toFixed(3)));

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

  // Typing only marks the result stale; scoring runs on Ctrl+Enter or a
  // programmatic trigger (swap, try-example, restored draft). A counter makes
  // sure a slow old answer can never overwrite a newer one.
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

  function onInput() {
    persistDrafts();
    if (!ready()) {
      clearResults();
      return;
    }
    stale = !upToDate();
  }

  function onKeydown(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      queueRun();
    }
  }

  function queueRun() {
    persistDrafts();
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
      cs.result = null;
      cs.single = null;
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

  // Arriving on the tab with unscored text (e.g. "Try in detect" from the
  // examples list, or a restored draft after a reload): score immediately.
  if (
    (cs.mode === "pair" ? cs.first.trim() && cs.second.trim() : cs.first.trim()) &&
    !upToDate()
  ) {
    queueRun();
  }

  function setMode(mode: "single" | "pair") {
    cs.mode = mode;
    error = null;
    queueRun();
  }

  function swap() {
    const a = cs.first;
    cs.first = cs.second;
    cs.second = a;
    if (cs.result && cs.lastScored && cs.lastScored.a === cs.second && cs.lastScored.b === cs.first) {
      // The scores just trade places; no need to re-embed.
      cs.result = {
        first: cs.result.second,
        second: cs.result.first,
        gap: -cs.result.gap,
        summary: cs.result.summary,
      };
      cs.lastScored = { a: cs.first, b: cs.second };
      saveHuman = saveHuman === "first" ? "second" : "first";
    }
    persistDrafts();
    queueRun();
  }

  async function tryExample() {
    loadingExample = true;
    try {
      const pairs = await api.listExamples();
      if (pairs.length === 0) {
        onGoExamples();
        return;
      }
      const p = pairs[Math.floor(Math.random() * pairs.length)];
      const flip = Math.random() < 0.5;
      if (pair) {
        cs.first = flip ? p.ai : p.human;
        cs.second = flip ? p.human : p.ai;
      } else {
        cs.first = flip ? p.ai : p.human;
      }
      queueRun();
    } finally {
      loadingExample = false;
    }
  }

  async function saveAsPair() {
    if (savingPair || !cs.result) return;
    const human = saveHuman === "first" ? cs.first : cs.second;
    const ai = saveHuman === "first" ? cs.second : cs.first;
    savingPair = true;
    try {
      await api.createExample({ ai, human });
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
      <div class="field-head">
        <label class="micro-label" for="det-t1">{pair ? "First text" : "Text"}</label>
        <span class="micro-label words">{wordLabel(w1)}</span>
      </div>
      <textarea
        id="det-t1"
        bind:value={cs.first}
        oninput={onInput}
        onkeydown={onKeydown}
        placeholder="Paste something here."
      ></textarea>
    </div>
    {#if pair}
      <div class="field">
        <div class="field-head">
          <label class="micro-label" for="det-t2">Second text</label>
          <span class="micro-label words">{wordLabel(w2)}</span>
          <button
            class="icon-btn close-second"
            aria-label="Back to a single text"
            title="Back to a single text"
            onclick={() => setMode("single")}
          >
            <X size={14} />
          </button>
        </div>
        <textarea
          id="det-t2"
          bind:value={cs.second}
          oninput={onInput}
          onkeydown={onKeydown}
          placeholder="And something else here."
        ></textarea>
      </div>
    {/if}
  </div>

  <div class="field-actions">
    <div class="actions-left">
      {#if pair}
        <button
          class="btn btn-ghost small"
          onclick={swap}
          disabled={!cs.first.trim() && !cs.second.trim()}
        >
          <ArrowsLeftRight size={14} />
          Swap
        </button>
      {:else}
        <button class="btn btn-ghost small" onclick={() => setMode("pair")}>
          <Columns size={14} />
          Compare two texts
        </button>
      {/if}
    </div>
    <button class="btn btn-ghost small" onclick={tryExample} disabled={loadingExample}>
      {#if loadingExample}<span class="spinner spinner-dark"></span>{:else}<Shuffle size={14} />{/if}
      Try an example
    </button>
  </div>

  {#if stale && !scoring}
    <p class="rescore-hint" aria-live="polite">
      Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to score
    </p>
  {/if}

  <div class="result" class:stale aria-live="polite">
    {#if error}
      <div class="note" role="alert">
        <p class="error-text">{error.message}</p>
        {#if error.status === 409}
          <button class="btn btn-primary small" onclick={onGoExamples}>Add training examples</button>
        {:else}
          <button class="btn small" onclick={() => queueRun()}>Try again</button>
        {/if}
      </div>
    {:else if chart && verdict}
      <p class="verdict">
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

      <div class="chart">
        <div class="plot">
          <div class="baseline"></div>
          {#each chart.ticks as t, i (i)}
            <div class="tick" class:zero={t === 0} style="left: {(i / (chart.ticks.length - 1)) * 100}%">
              <span class="micro-label tick-num">{tickLabel(t)}</span>
            </div>
          {/each}
          {#each chart.markers as m, i (i)}
            <span class="pin {m.side}" style="left: {m.pos}%">
              {#if m.label}
                <span class="micro-label pin-label {m.tier}">{m.label}</span>
              {/if}
            </span>
          {/each}
        </div>
        <div class="axis">
          <span class="micro-label axis-ai">More like AI</span>
          <span class="micro-label axis-human">More human</span>
        </div>
      </div>

      {#if pair && verdict.kind !== "identical"}
        <div class="result-foot">
          {#if savedPair}
            <span class="saved-note"><Check size={14} weight="bold" /> Saved to examples</span>
          {:else}
            <span class="save">
              <span class="save-label">Human:</span>
              <span class="seg-mini" role="group" aria-label="Which text is the human version">
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
      <div class="chart loading-chart"><div class="skeleton"></div></div>
    {:else}
      <div class="note">
        <p>
          {#if pair}
            Paste two pieces of writing and press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to score them.
            The markers show where each one falls between AI and human.
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
    gap: 7px;
  }

  .field-head {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 22px;
  }

  .words {
    margin-left: auto;
    color: var(--ink-faint);
  }

  .close-second {
    width: 22px;
    height: 22px;
    color: var(--ink-secondary);
  }

  .field textarea {
    min-height: 184px;
  }

  .field-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 8px;
  }

  .actions-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .rescore-hint {
    margin: 14px 0 0;
    text-align: center;
    font-size: 12.5px;
    color: var(--ink-faint);
  }

  kbd {
    display: inline-block;
    padding: 1px 5px;
    font-family: inherit;
    font-size: 11.5px;
    font-weight: 500;
    color: var(--ink-secondary);
    background: var(--surface-muted);
    border: 1px solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-xs);
  }

  .result {
    margin-top: 26px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    transition: opacity 200ms var(--ease);
  }

  .result.stale {
    opacity: 0.45;
  }

  .verdict {
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.015em;
  }

  .who.human {
    color: var(--human);
  }

  .who.ai {
    color: var(--ai);
  }

  /* ---------- Chart: a plain scale with ticks ---------- */
  .chart {
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

  .tick {
    position: absolute;
    top: 0;
    width: 1px;
    height: 7px;
    background: var(--border-strong);
    transform: translateX(-0.5px);
  }

  .tick.zero {
    height: 11px;
    background: var(--ink-faint);
  }

  .tick-num {
    position: absolute;
    top: 15px;
    left: 50%;
    transform: translateX(-50%);
    color: var(--ink-faint);
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
    box-shadow: 0 1px 4px hsl(222 47% 11% / 0.25);
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

  .pin-label {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    white-space: nowrap;
    color: var(--ink-2);
  }

  .pin-label.low {
    bottom: calc(100% + 8px);
  }

  .pin-label.high {
    bottom: calc(100% + 24px);
  }

  .axis {
    display: flex;
    justify-content: space-between;
    margin-top: 44px;
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
    justify-content: flex-end;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 20px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }

  .save {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .save-label {
    font-size: 12.5px;
    color: var(--ink-faint);
  }

  .seg-mini {
    display: flex;
    padding: 2px;
    gap: 2px;
    background: var(--surface-muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .seg-mini button {
    appearance: none;
    border: none;
    background: none;
    border-radius: var(--radius-xs);
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 500;
    color: var(--ink-secondary);
    transition:
      color var(--speed) var(--ease),
      background var(--speed) var(--ease);
  }

  .seg-mini button.active {
    background: color-mix(in srgb, var(--brand-soft) 60%, transparent);
    color: hsl(217 91% 45%);
  }

  .seg-mini button:focus-visible {
    outline-offset: 1px;
  }

  .saved-note {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    font-weight: 500;
    color: var(--ink-secondary);
  }

  /* ---------- Notes & states ---------- */
  .note {
    padding: 26px 0 22px;
    text-align: center;
  }

  .note p {
    margin: 0 auto;
    max-width: 46ch;
    color: var(--ink-secondary);
    font-size: 13.5px;
  }

  .note .error-text {
    color: var(--danger);
    margin-bottom: 14px;
  }

  .loading-chart {
    padding-top: 6px;
  }

  .skeleton {
    height: 10px;
    border-radius: 999px;
    margin-top: 24px;
    background: hsl(220 14% 93%);
  }

  @media (prefers-reduced-motion: no-preference) {
    .skeleton {
      animation: pulse 1.3s ease-in-out infinite;
    }
  }

  @keyframes pulse {
    50% {
      opacity: 0.5;
    }
  }

  @media (max-width: 760px) {
    .inputs.pair {
      grid-template-columns: 1fr;
    }
  }
</style>
