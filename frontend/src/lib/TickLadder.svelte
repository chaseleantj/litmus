<script lang="ts">
  /**
   * The labelled ticks under a litmus strip. Both scales — the Detect result
   * chart and the map's axis view — draw the same ladder from the same domain
   * (scale.ticksFor), so the marks, their spacing and their labels live here
   * once. Positions are evenly spaced across the strip's width, which is what
   * makes them line up with it; the look is the shared .tick / .tick-num in
   * app.css. The parent supplies a positioning context.
   */
  import { tickLabel } from "./scale";

  interface Props {
    ticks: number[];
    /** True where the whole scale is already announced some other way and the
     *  ladder would only repeat it. */
    ariaHidden?: boolean;
  }

  let { ticks, ariaHidden = false }: Props = $props();
</script>

{#each ticks as t, i (i)}
  <div
    class="tick"
    class:zero={t === 0}
    style="left: {(i / (ticks.length - 1)) * 100}%"
    aria-hidden={ariaHidden ? "true" : undefined}
  >
    <span class="micro-label tick-num">{tickLabel(t)}</span>
  </div>
{/each}
