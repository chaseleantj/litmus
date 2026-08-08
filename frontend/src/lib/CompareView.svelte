<script lang="ts">
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
  <div class="intro">
    <p class="lede">
      Paste two pieces of writing and this will tell you which one sounds more like a person. It
      compares them against each other, so it can't tell you much about one piece on its own.
    </p>
    <button class="btn" onclick={tryExample} disabled={loadingExample}>Try an example</button>
  </div>

  <div class="inputs">
    <div class="field">
      <label for="cmp-t1">First text <span class="role">stays put</span></label>
      <textarea
        id="cmp-t1"
        bind:value={cs.first}
        oninput={() => queueRun()}
        placeholder="Paste something here."
      ></textarea>
      <div class="meta">{w1 === 1 ? "1 word" : `${w1.toLocaleString()} words`}</div>
    </div>
    <div class="field">
      <label for="cmp-t2">Second text <span class="role">moves</span></label>
      <textarea
        id="cmp-t2"
        bind:value={cs.second}
        oninput={() => queueRun()}
        placeholder="And something else here."
      ></textarea>
      <div class="meta">{w2 === 1 ? "1 word" : `${w2.toLocaleString()} words`}</div>
    </div>
  </div>

  <div class="hint-row">
    <p class="hint">Fill both boxes and the score appears on its own.</p>
    <button
      class="btn btn-ghost small"
      onclick={swap}
      disabled={!cs.first.trim() && !cs.second.trim()}
    >
      Swap texts
    </button>
  </div>

  <div class="result card" class:stale aria-live="polite">
    {#if error}
      <div class="note error-note" role="alert">
        {#if error.status === 409}
          <p>{error.message}</p>
          <button class="btn" onclick={onGoExamples}>Add training examples</button>
        {:else}
          <p>{error.message}</p>
          <button class="btn" onclick={() => queueRun(true)}>Try again</button>
        {/if}
      </div>
    {:else if cs.result && chart && verdict}
      <p class="verdict">
        {#if verdict.kind === "identical"}
          You have pasted the same text twice.
        {:else if verdict.kind === "tie"}
          Too close to call.
        {:else}
          The <span class="side-human-word">{verdict.which}</span> text sounds {verdict.strength} more
          human.
        {/if}
      </p>
      <div class="chart">
        <div class="frame">
          <div class="zones"></div>
          <div class="marker m1" style="left: 50%"><div class="flag">First</div></div>
          <div class="marker m2 {chart.side}" style="left: {chart.pos2}%">
            <div class="flag">Second</div>
          </div>
        </div>
        <div class="ends">
          <span class="left">&larr; sounds more like AI<br />than the first</span>
          <span class="mid">anything in the middle<br />is hard to tell apart</span>
          <span class="right">sounds more human<br />than the first &rarr;</span>
        </div>
      </div>
      <div class="result-foot">
        <span class="scores num">
          first {fmt(cs.result.first)} &middot; second {fmt(cs.result.second)} &middot; gap
          {cs.result.gap > 0 ? "+" : ""}{fmt(cs.result.gap)}
        </span>
        {#if verdict.kind !== "identical"}
          <span class="save-pair">
            {#if savedPair}
              <span class="saved-note">Saved to training examples.</span>
            {:else}
              <span class="save-note">
                Saves the <span class="side-human-word">{saveHuman}</span> text as the human version
                &middot;
                <button
                  class="linkish"
                  onclick={() => (saveHuman = saveHuman === "first" ? "second" : "first")}
                >
                  switch
                </button>
              </span>
              <button class="btn small" onclick={saveAsPair} disabled={savingPair}>
                {#if savingPair}<span class="spinner spinner-dark"></span>{/if}
                Add as training pair
              </button>
            {/if}
          </span>
        {/if}
      </div>
    {:else if comparing}
      <div class="chart"><div class="skeleton"></div></div>
    {:else}
      <div class="note">
        <p>
          The first text stays in the middle. The second one slides right if it sounds more like a
          person, and left if it sounds more like AI.
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
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field label {
    font-size: 13px;
    font-weight: 600;
  }

  .field label .role {
    font-weight: 400;
    color: var(--ink-faint);
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

  .small {
    padding: 4px 10px;
    font-size: 13px;
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

  .error-note p {
    color: var(--human);
    margin-bottom: 14px;
  }

  .skeleton {
    height: 46px;
    border-radius: 6px;
    background: var(--zone-quiet);
  }

  @media (prefers-reduced-motion: no-preference) {
    .skeleton {
      animation: pulse 1.3s ease-in-out infinite;
    }
  }

  @keyframes pulse {
    50% {
      opacity: 0.55;
    }
  }

  @media (max-width: 760px) {
    .inputs {
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
