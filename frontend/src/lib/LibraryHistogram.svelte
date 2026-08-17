<script lang="ts">
  /**
   * A quiet summary of when the library grew: one bar per day (per week or
   * month once "all time" outgrows days), derived from the pairs already on
   * screen. Every date, bucket and scale decision lives in histogram.ts; this
   * file only draws them.
   */
  import {
    bucketReadout,
    buildHistogram,
    histogramCaption,
    RANGES,
    undatedNote,
    type RangeId,
  } from "./histogram";
  import type { Example } from "./types";

  interface Props {
    examples: Example[];
  }

  let { examples }: Props = $props();

  // The range the user chose, if they chose one. Until then the chart offers
  // the tightest window that actually holds something — and once a choice is
  // made, nothing overrides it.
  let picked = $state<RangeId | null>(null);
  const suggested = $derived.by(() => {
    if (buildHistogram(examples, "7d").total > 0) return "7d" as const;
    if (buildHistogram(examples, "30d").total > 0) return "30d" as const;
    return "all" as const;
  });
  const range = $derived(picked ?? suggested);
  const hist = $derived(buildHistogram(examples, range));
  const caption = $derived(histogramCaption(hist, range));

  // Pointer and keyboard each highlight a bucket; whichever was used last
  // wins, so the reading can never disagree with the focus ring.
  let hovered = $state<number | null>(null);
  let focused = $state<number | null>(null);
  const active = $derived(hovered ?? focused);

  // Bars only exist while a range holds something, so a stale index cannot
  // survive a range switch, an import or a delete.
  $effect(() => {
    void hist;
    hovered = null;
    focused = null;
  });

  const readout = $derived(active === null ? caption : bucketReadout(hist.buckets[active]));

  const emptyNote = $derived.by(() => {
    const phrase = RANGES.find((r) => r.id === range)?.phrase ?? "";
    if (hist.latest === null) return "No pairs carry a usable date, so there is nothing to chart.";
    const day = hist.latest.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    return `Nothing added in ${phrase}. The most recent pair was added on ${day}.`;
  });

  /** One tab stop for the whole chart; the arrows walk it from there. */
  const tabStop = $derived(focused ?? 0);

  function moveFocus(from: HTMLElement, to: number) {
    const target = from.parentElement?.children[to];
    if (target instanceof HTMLElement) target.focus();
  }

  function onBarKeydown(e: KeyboardEvent & { currentTarget: HTMLButtonElement }, i: number) {
    const last = hist.buckets.length - 1;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") moveFocus(e.currentTarget, Math.min(last, i + 1));
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") moveFocus(e.currentTarget, Math.max(0, i - 1));
    else if (e.key === "Home") moveFocus(e.currentTarget, 0);
    else if (e.key === "End") moveFocus(e.currentTarget, last);
    else return;
    e.preventDefault();
  }
</script>

<section class="card hist" aria-label="Pairs added over time">
  <header>
    <span class="micro-label">Pairs added</span>
    <div class="seg" role="group" aria-label="Time range">
      {#each RANGES as r (r.id)}
        <button
          class:active={range === r.id}
          aria-pressed={range === r.id}
          onclick={() => (picked = r.id)}
        >
          {r.label}
        </button>
      {/each}
    </div>
  </header>

  {#if hist.total === 0}
    <p class="empty">{emptyNote}</p>
    {#if hist.undated > 0}
      <p class="caption">{undatedNote(hist)}.</p>
    {/if}
  {:else}
    <div class="plot">
      <div class="grid" aria-hidden="true">
        {#each hist.ticks as t (t)}
          <div class="gridline" style="bottom: {(t / hist.yMax) * 100}%">
            <span class="micro-label tick">{t}</span>
          </div>
        {/each}
      </div>
      <!-- Bars tile the plot edge to edge: the space around a bar belongs to
           that bar's bucket, so the pointer never falls through a gap. Each is
           a real button, so hover, focus and touch all reach the same reading
           without a second keyboard path bolted on. -->
      <div class="bars" role="group" aria-label={caption}>
        {#each hist.buckets as b, i (i)}
          <button
            type="button"
            class="slot"
            class:active={active === i}
            aria-label={bucketReadout(b)}
            tabindex={i === tabStop ? 0 : -1}
            onpointerenter={() => (hovered = i)}
            onpointerleave={() => {
              if (hovered === i) hovered = null;
            }}
            onfocus={() => {
              focused = i;
              hovered = null;
            }}
            onblur={() => {
              if (focused === i) focused = null;
            }}
            onclick={() => (focused = i)}
            onkeydown={(e) => onBarKeydown(e, i)}
          >
            <span
              class="bar"
              class:zero={b.count === 0}
              style="height: {(b.count / hist.yMax) * 100}%"
            ></span>
          </button>
        {/each}
      </div>
    </div>
    <div class="axis" aria-hidden="true">
      <span class="micro-label">{hist.buckets[0].axisLabel}</span>
      <span class="micro-label">{hist.buckets[hist.buckets.length - 1].axisLabel}</span>
    </div>
    <p class="caption" aria-live="polite">{readout}</p>
  {/if}
</section>

<style>
  .hist {
    padding: 12px 16px 10px;
    margin-bottom: 18px;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }

  /* The tick numbers live in this gutter, so the plot and the axis labels
     below it share one left edge. */
  .plot {
    position: relative;
    height: 64px;
    padding-left: 22px;
  }

  .grid {
    position: absolute;
    inset: 0 0 0 22px;
  }

  .gridline {
    position: absolute;
    left: 0;
    right: 0;
    border-top: 1px solid var(--border);
  }

  /* The zero line is the chart's baseline, not a gridline. */
  .gridline:first-child {
    border-top-color: var(--border-strong);
  }

  .tick {
    position: absolute;
    right: calc(100% + 6px);
    top: -0.7em;
    color: var(--ink-faint);
  }

  .bars {
    position: relative;
    display: flex;
    align-items: flex-end;
    height: 100%;
  }

  .slot {
    display: flex;
    align-items: flex-end;
    justify-content: center;
    flex: 1;
    height: 100%;
    padding: 0;
    border: none;
    background: transparent;
    border-radius: 2px;
    transition: background var(--speed) var(--ease);
  }

  .slot.active {
    background: hsl(var(--ink-hsl) / 0.05);
  }

  .slot:focus-visible {
    outline: 2px solid var(--ink);
    outline-offset: 1px;
  }

  .bar {
    width: max(2px, calc(100% - 3px));
    min-height: 2px;
    border-radius: 1.5px 1.5px 0 0;
    background: hsl(var(--ink-hsl) / 0.4);
    transition:
      height var(--speed) var(--ease),
      background var(--speed) var(--ease);
  }

  .slot.active .bar {
    background: hsl(var(--ink-hsl) / 0.78);
  }

  /* An empty bucket draws nothing — the baseline already runs under it, and
     its slot still answers to hover and the arrow keys. */
  .bar.zero {
    min-height: 0;
  }

  .axis {
    display: flex;
    justify-content: space-between;
    padding-left: 22px;
    margin-top: 5px;
  }

  .axis .micro-label {
    color: var(--ink-faint);
  }

  .caption,
  .empty {
    margin-top: 6px;
    font-size: var(--text-body);
    color: var(--ink-secondary);
  }

  .empty {
    padding: 10px 0 4px;
    text-align: center;
    text-wrap: balance;
  }

  /* One line, always: the readout swaps in on hover without nudging the list
     below it. */
  .caption {
    min-height: 1.55em;
    font-variant-numeric: tabular-nums;
  }
</style>
