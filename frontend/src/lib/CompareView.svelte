<script lang="ts">
  import { ArrowsLeftRight, Check, Shuffle } from "phosphor-svelte";
  import { api, ApiError } from "./api";
  import { compareState as cs, persistDrafts } from "./compareState.svelte";
  import { toast } from "./toast";

  interface Props {
    onGoExamples: () => void;
  }

  let { onGoExamples }: Props = $props();

  let comparing = $state(false);
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

  const identical = $derived(cs.first.trim().length > 0 && cs.first.trim() === cs.second.trim());

  /**
   * The first text is the anchor at the centre; the second is placed by its
   * distance from it, positive to the right (more human). The span widens to
   * keep the marker on the bar for large gaps, and never drops below the
   * "clear" zone so small gaps visibly hug the middle.
   */
  const chart = $derived.by(() => {
    if (!cs.result) return null;
    const d = cs.result.gap;
    const span = Math.max(0.3, Math.abs(d) * 1.18, CLEAR * 2.4);
    const flat = identical || Math.abs(d) < TOO_CLOSE;
    return {
      pos2: identical ? 50 : (0.5 + d / (2 * span)) * 100,
      side: flat ? "" : d > 0 ? "side-human" : "side-ai",
    };
  });

  type Verdict =
    | { kind: "identical" }
    | { kind: "tie" }
    | { kind: "call"; which: "first" | "second"; strength: "clearly" | "a little" };
  const verdict = $derived.by<Verdict | null>(() => {
    if (!cs.result) return null;
    if (identical) return { kind: "identical" };
    const g = cs.result.gap;
    if (Math.abs(g) < TOO_CLOSE) return { kind: "tie" };
    return {
      kind: "call",
      which: g > 0 ? "second" : "first",
      strength: Math.abs(g) >= CLEAR ? "clearly" : "a little",
    };
  });

  // Live scoring: each keystroke resets a short timer; when typing pauses the
  // texts go off for scoring. A counter makes sure a slow old answer can never
  // overwrite a newer one.
  let timer: ReturnType<typeof setTimeout> | undefined;
  let requestId = 0;

  function queueRun(immediate = false) {
    clearTimeout(timer);
    persistDrafts();
    const a = cs.first,
      b = cs.second;
    if (!a.trim() || !b.trim()) {
      requestId++;
      cs.lastScored = null;
      cs.result = null;
      error = null;
      stale = false;
      comparing = false;
      return;
    }
    if (cs.lastScored && cs.lastScored.a === a && cs.lastScored.b === b) return;
    stale = true;
    timer = setTimeout(run, immediate ? 0 : 600);
  }

  async function run() {
    const a = cs.first,
      b = cs.second;
    const id = ++requestId;
    comparing = true;
    error = null;
    try {
      const r = await api.compare(a, b);
      if (id !== requestId) return;
      cs.lastScored = { a, b };
      cs.result = r;
      savedPair = false;
      saveHuman = r.gap >= 0 ? "second" : "first";
    } catch (err) {
      if (id !== requestId) return;
      cs.result = null;
      error =
        err instanceof ApiError
          ? { status: err.status, message: err.message }
          : { status: 0, message: err instanceof Error ? err.message : "That did not work. Try again." };
    } finally {
      if (id === requestId) {
        comparing = false;
        stale = false;
      }
    }
  }

  // Arriving on the tab with unscored texts (e.g. "Try in compare" from the
  // examples list, or a restored draft after a reload): score immediately.
  if (
    cs.first.trim() &&
    cs.second.trim() &&
    !(cs.lastScored && cs.lastScored.a === cs.first && cs.lastScored.b === cs.second)
  ) {
    queueRun(true);
  }

  function swap() {
    clearTimeout(timer);
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
    queueRun(true);
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
      cs.first = flip ? p.ai : p.human;
      cs.second = flip ? p.human : p.ai;
      queueRun(true);
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

  const fmt = (v: number) => v.toFixed(3);
</script>

<section aria-label="Compare texts">
  <div class="inputs">
    <div class="field">
      <div class="field-head">
        <label for="cmp-t1">First text</label>
        <span class="words">{w1 === 1 ? "1 word" : `${w1.toLocaleString()} words`}</span>
      </div>
      <textarea
        id="cmp-t1"
        bind:value={cs.first}
        oninput={() => queueRun()}
        placeholder="Paste something here."
      ></textarea>
    </div>
    <div class="field">
      <div class="field-head">
        <label for="cmp-t2">Second text</label>
        <span class="words">{w2 === 1 ? "1 word" : `${w2.toLocaleString()} words`}</span>
      </div>
      <textarea
        id="cmp-t2"
        bind:value={cs.second}
        oninput={() => queueRun()}
        placeholder="And something else here."
      ></textarea>
    </div>
  </div>

  <div class="field-actions">
    <button
      class="btn btn-ghost small"
      onclick={swap}
      disabled={!cs.first.trim() && !cs.second.trim()}
    >
      <ArrowsLeftRight size={14} />
      Swap
    </button>
    <button class="btn btn-ghost small" onclick={tryExample} disabled={loadingExample}>
      {#if loadingExample}<span class="spinner spinner-dark"></span>{:else}<Shuffle size={14} />{/if}
      Try an example
    </button>
  </div>

  <div class="result" class:stale aria-live="polite">
    {#if error}
      <div class="note" role="alert">
        <p class="error-text">{error.message}</p>
        {#if error.status === 409}
          <button class="btn btn-primary small" onclick={onGoExamples}>Add training examples</button>
        {:else}
          <button class="btn small" onclick={() => queueRun(true)}>Try again</button>
        {/if}
      </div>
    {:else if cs.result && chart && verdict}
      <p class="verdict">
        {#if verdict.kind === "identical"}
          You pasted the same text twice.
        {:else if verdict.kind === "tie"}
          Too close to call.
        {:else}
          The <span class="who">{verdict.which}</span> text sounds {verdict.strength} more human.
        {/if}
      </p>
      <div class="chart">
        <div class="track">
          <span class="pin first" style="left: 50%">
            <span class="pin-label above">First</span>
          </span>
          <span class="pin second {chart.side}" style="left: {chart.pos2}%">
            <span class="pin-label below">Second</span>
          </span>
        </div>
        <div class="axis">
          <span class="axis-ai">More like AI</span>
          <span class="axis-human">More human</span>
        </div>
      </div>
      <div class="result-foot">
        <span class="scores">
          first {fmt(cs.result.first)} &middot; second {fmt(cs.result.second)} &middot; gap
          {cs.result.gap > 0 ? "+" : ""}{fmt(cs.result.gap)}
        </span>
        {#if verdict.kind !== "identical"}
          {#if savedPair}
            <span class="saved-note"><Check size={14} weight="bold" /> Saved to examples</span>
          {:else}
            <span class="save">
              <span class="save-label">Human:</span>
              <span class="seg-mini" role="group" aria-label="Which text is the human version">
                <button
                  class:active={saveHuman === "first"}
                  onclick={() => (saveHuman = "first")}>First</button
                >
                <button
                  class:active={saveHuman === "second"}
                  onclick={() => (saveHuman = "second")}>Second</button
                >
              </span>
              <button class="btn btn-primary small" onclick={saveAsPair} disabled={savingPair}>
                {#if savingPair}<span class="spinner"></span>{/if}
                Save as pair
              </button>
            </span>
          {/if}
        {/if}
      </div>
    {:else if comparing}
      <div class="chart loading-chart"><div class="skeleton"></div></div>
    {:else}
      <div class="note">
        <p>
          Paste two pieces of writing and the score appears on its own. The marker shows which one
          sounds more human.
        </p>
      </div>
    {/if}
  </div>
</section>

<style>
  .inputs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .field-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
  }

  .field-head label {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: -0.005em;
  }

  .words {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
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

  .who {
    color: var(--human);
  }

  /* ---------- Chart ---------- */
  .chart {
    margin-top: 8px;
    padding: 30px 8px 0;
  }

  .track {
    position: relative;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(
      to right,
      var(--ai-soft),
      var(--surface-muted) 42% 58%,
      var(--human-soft)
    );
    box-shadow: inset 0 0 0 1px var(--border);
  }

  .pin {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    border-radius: 50%;
  }

  .pin.first {
    width: 13px;
    height: 13px;
    background: var(--surface);
    border: 2px solid var(--ink-secondary);
  }

  .pin.second {
    width: 17px;
    height: 17px;
    background: var(--ink-secondary);
    border: 2.5px solid var(--surface);
    box-shadow: 0 1px 4px rgba(32, 29, 25, 0.3);
    transition:
      left 420ms var(--ease),
      background 200ms var(--ease);
  }

  .pin.second.side-ai {
    background: var(--ai);
  }

  .pin.second.side-human {
    background: var(--human);
  }

  .pin-label {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    white-space: nowrap;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--ink-secondary);
  }

  .pin-label.above {
    bottom: calc(100% + 9px);
  }

  .pin-label.below {
    top: calc(100% + 9px);
  }

  .axis {
    display: flex;
    justify-content: space-between;
    margin-top: 32px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.02em;
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
    margin-top: 20px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }

  .scores {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
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
    border-radius: 999px;
  }

  .seg-mini button {
    appearance: none;
    border: none;
    background: none;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 500;
    color: var(--ink-secondary);
    transition:
      color var(--speed) var(--ease),
      background var(--speed) var(--ease);
  }

  .seg-mini button.active {
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-sm);
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
    background: var(--surface-muted);
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
    .inputs {
      grid-template-columns: 1fr;
    }
  }
</style>
