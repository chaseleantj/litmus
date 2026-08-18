<script lang="ts">
  /**
   * A quiet summary of when the library grew: one bar per day (per week or
   * month once "all time" outgrows days), derived from the pairs already on
   * screen. Every date, bucket and scale decision lives in histogram.ts; this
   * file only draws them.
   */
  import {
    bucketCount,
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
  // wins, so the tooltip can never disagree with the focus ring.
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
      <p class="note">{undatedNote(hist)}.</p>
    {/if}
  {:else}
    <div class="plot">
      <!-- Bars tile the plot edge to edge: the space around a bar belongs to
           that bar's bucket, so the pointer never falls through a gap. Each is
           a real button, so hover, focus and touch all reach the same tooltip
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
            {#if active === i}
              <span
                class="tip"
                role="tooltip"
                style="bottom: calc({(b.count === 0 ? 100 : (b.count / hist.yMax) * 100)}% + 6px)"
              >{bucketCount(b)}</span>
            {/if}
            <span class="track" aria-hidden="true"></span>
            {#if b.count > 0}
              <span class="bar" style="height: {(b.count / hist.yMax) * 100}%"></span>
            {/if}
          </button>
        {/each}
      </div>
    </div>
    <div class="axis" aria-hidden="true">
      <span class="micro-label">{hist.buckets[0].axisLabel}</span>
      <span class="micro-label">{hist.buckets[hist.buckets.length - 1].axisLabel}</span>
    </div>
    {#if hist.undated > 0}
      <p class="note">{undatedNote(hist)}.</p>
    {/if}
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

  .plot {
    position: relative;
    height: 64px;
    border-bottom: 1px solid var(--border-strong);
  }

  .bars {
    position: relative;
    display: flex;
    align-items: flex-end;
    height: 100%;
  }

  .slot {
    position: relative;
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

  /* A faint full-height column behind every day, so filled bars sit on the
     same rhythm as empty ones. */
  .track {
    position: absolute;
    left: 50%;
    bottom: 0;
    transform: translateX(-50%);
    width: max(2px, calc(100% - 3px));
    height: 100%;
    border-radius: 1.5px 1.5px 0 0;
    background: hsl(var(--ink-hsl) / 0.03);
    pointer-events: none;
  }

  .slot.active .track {
    background: hsl(var(--ink-hsl) / 0.05);
  }

  .bar {
    position: relative;
    z-index: 1;
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

  .axis {
    display: flex;
    justify-content: space-between;
    margin-top: 5px;
  }

  .axis .micro-label {
    color: var(--ink-faint);
  }

  .tip {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    z-index: 2;
    width: max-content;
    max-width: 180px;
    padding: 5px 8px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-xs);
    background: var(--surface);
    box-shadow: var(--shadow-toast);
    color: var(--ink);
    font-size: var(--text-micro);
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
    pointer-events: none;
    white-space: nowrap;
  }

  .slot:first-child .tip {
    left: 0;
    transform: none;
  }

  .slot:last-child .tip {
    left: auto;
    right: 0;
    transform: none;
  }

  .empty,
  .note {
    margin-top: 6px;
    font-size: var(--text-body);
    color: var(--ink-secondary);
  }

  .empty {
    padding: 10px 0 4px;
    text-align: center;
    text-wrap: balance;
  }
</style>
