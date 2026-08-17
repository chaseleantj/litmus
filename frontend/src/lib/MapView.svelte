<script lang="ts">
  import { library, MIN_PAIRS } from "./library.svelte";
  import { librarySignature, loadMap, mapState } from "./mapState.svelte";
  import { fmtScore, pickDomain, scalePos, tickLabel } from "./scale";
  import type { MapPoint } from "./types";

  interface Props {
    onOpenLibrary: () => void;
  }

  let { onOpenLibrary }: Props = $props();

  // ---- Geometry & motion constants -----------------------------------------
  const DOT_R = 6.5;
  const HOVER_SCALE = 1.45;
  const HOVER_MS = 140;
  /** Per-point travel time between layouts, plus the stagger sweep on top. */
  const TRANSITION_MS = 620;
  const STAGGER_MS = 220;
  const HIT_RADIUS = 22;
  const MAP_PAD = 30;
  /** Beeswarm rows must clear the tick numbers below the strip. */
  const AXIS_PAD_Y = 48;

  // ---- Data -----------------------------------------------------------------
  const points = $derived<MapPoint[]>(mapState.data?.points ?? []);
  const axisView = $derived(mapState.view === "axis");
  const domain = $derived(pickDomain(Math.max(0, ...points.map((p) => Math.abs(p.score)))));
  const ticks = $derived([-domain, -domain / 2, 0, domain / 2, domain]);

  // Scoring is meaningless below MIN_PAIRS; while the library is still
  // loading (or failed to load) the server stays the judge via its 409.
  const calibrated = $derived(
    library.loading || library.error !== null || library.examples.length >= MIN_PAIRS,
  );

  // The picture on screen was computed for an older library: keep showing it
  // (dimmed, with a pill) while the fresh one is embedding.
  const refreshing = $derived(mapState.loading && mapState.data !== null);

  // Fetch whenever the map is missing or was built for a different library.
  // A failed attempt is not retried until the library changes or the user
  // asks (loadMap from the error panel).
  $effect(() => {
    if (library.loading || !calibrated || mapState.loading) return;
    const signature = librarySignature();
    if (mapState.erroredFor === signature) return;
    if (mapState.data !== null && mapState.loadedFor === signature) return;
    loadMap();
  });

  // ---- Canvas ---------------------------------------------------------------
  let host = $state<HTMLDivElement>();
  let canvas = $state<HTMLCanvasElement>();
  let ctx: CanvasRenderingContext2D | null = null;
  let cssWidth = $state(0);
  let cssHeight = $state(0);
  let dpr = $state(1);

  /** Side gutters of the axis view; the AI / Human pole labels live in them
   *  ("HUMAN" needs ~46px plus breathing room at every width). One value
   *  drives both the canvas math and the DOM chrome (inline styles below),
   *  so the strip and the dots can never disagree. */
  const axisPadX = 64;
  const poleInset = $derived(cssWidth < 520 ? 10 : 18);

  // Theme colors resolved once — canvas cannot read CSS variables itself.
  let colors = { ai: "#5a4bbf", human: "#b45016", surface: "#fffdf8", ink: "#211b12" };

  $effect(() => {
    if (!host || !canvas) return;
    ctx = canvas.getContext("2d");
    dpr = window.devicePixelRatio || 1;
    const style = getComputedStyle(document.documentElement);
    colors = {
      ai: style.getPropertyValue("--ai").trim(),
      human: style.getPropertyValue("--human").trim(),
      surface: style.getPropertyValue("--surface").trim(),
      ink: style.getPropertyValue("--ink").trim(),
    };
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      cssWidth = Math.floor(rect.width);
      cssHeight = Math.floor(rect.height);
    });
    observer.observe(host);
    return () => observer.disconnect();
  });

  $effect(() => {
    if (!canvas || cssWidth === 0 || cssHeight === 0) return;
    canvas.width = Math.max(1, Math.round(cssWidth * dpr));
    canvas.height = Math.max(1, Math.round(cssHeight * dpr));
  });

  // ---- Layouts ----------------------------------------------------------------
  // Both layouts are pure functions of (points, size), recomputed on demand —
  // resizing mid-transition just interpolates toward fresh targets.

  function mapTargets(w: number, h: number): { x: number; y: number }[] {
    const innerW = Math.max(1, w - 2 * MAP_PAD);
    const innerH = Math.max(1, h - 2 * MAP_PAD);
    return points.map((p) => ({ x: MAP_PAD + p.x * innerW, y: MAP_PAD + p.y * innerH }));
  }

  function axisTargets(w: number, h: number): { x: number; y: number }[] {
    const x0 = axisPadX;
    const axisW = Math.max(1, w - 2 * axisPadX);
    const cy = h / 2;
    const gap = DOT_R * 2 + 2.5;
    const xs = points.map((p) => x0 + (scalePos(p.score, domain) / 100) * axisW);
    // Beeswarm: place in x order; each dot takes the row (0, -1, +1, -2, …)
    // nearest the strip where it doesn't collide with an earlier dot.
    // Upward rows (-) are tried first: the tick numbers live below the strip.
    const order = points.map((_, i) => i).sort((a, b) => xs[a] - xs[b]);
    const rows = new Map<number, number[]>();
    const maxRow = Math.max(1, Math.floor((h / 2 - AXIS_PAD_Y) / gap));
    const ys = new Array<number>(points.length);
    for (const i of order) {
      let row = 0;
      for (let k = 0; ; k++) {
        row = k % 2 === 1 ? -(k + 1) / 2 : k / 2;
        if (Math.abs(row) > maxRow) {
          row = 0; // out of vertical room (extreme N): accept overlap at center
          break;
        }
        const placed = rows.get(row);
        if (!placed || placed.every((px) => Math.abs(px - xs[i]) >= gap)) break;
      }
      const placed = rows.get(row);
      if (placed) placed.push(xs[i]);
      else rows.set(row, [xs[i]]);
      ys[i] = cy + row * gap;
    }
    return points.map((_, i) => ({ x: xs[i], y: ys[i] }));
  }

  function currentTargets(w: number, h: number): { x: number; y: number }[] {
    return axisView ? axisTargets(w, h) : mapTargets(w, h);
  }

  // ---- View transition ----------------------------------------------------
  // On toggle, every dot travels from where it is drawn right now to its
  // place in the other layout, eased, with a small left-to-right stagger.
  // "From" is kept as a fraction of the canvas so a resize mid-flight stays
  // proportionate rather than aiming at stale pixels.
  type Transition = { start: number; fromFx: number[]; fromFy: number[]; delays: number[] };
  let transition: Transition | null = null;
  let drawnX: number[] = [];
  let drawnY: number[] = [];
  let rafHandle: number | null = null;

  const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
  const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

  function setView(view: "map" | "axis") {
    if (mapState.view === view) return;
    setHovered(null);
    if (!reducedMotion() && cssWidth > 0 && drawnX.length === points.length) {
      // Stagger sweeps along the axis so the swarm reads as forming/unforming.
      const ranked = points.map((_, i) => i).sort((a, b) => points[a].score - points[b].score);
      const delays = new Array<number>(points.length);
      ranked.forEach((idx, rank) => {
        delays[idx] = (rank / Math.max(1, points.length - 1)) * STAGGER_MS;
      });
      transition = {
        start: performance.now(),
        fromFx: drawnX.map((x) => x / cssWidth),
        fromFy: drawnY.map((y) => y / cssHeight),
        delays,
      };
    } else {
      transition = null;
    }
    mapState.view = view;
    requestRaf();
  }

  // ---- Hover ----------------------------------------------------------------
  let hovered = $state<number | null>(null);
  type HoverAnim = { i: number; from: number; to: number; start: number };
  let entering: HoverAnim | null = null;
  let leaving: HoverAnim | null = null;

  // Non-hovered dots recede while something is hovered. Animated with the
  // same duration as the hover scale so the two arrive together.
  const DIM_ALPHA = 0.35;
  const BASE_ALPHA = 0.85;
  let dimAnim: { from: number; to: number; start: number } = {
    from: BASE_ALPHA,
    to: BASE_ALPHA,
    start: 0,
  };

  function hoverScaleOf(anim: HoverAnim, now: number): number {
    const t = clamp01((now - anim.start) / HOVER_MS);
    return anim.from + (anim.to - anim.from) * easeOut(t);
  }

  function dimAlphaAt(now: number): number {
    const t = clamp01((now - dimAnim.start) / HOVER_MS);
    return dimAnim.from + (dimAnim.to - dimAnim.from) * easeOut(t);
  }

  function setHovered(i: number | null) {
    if (hovered === i) return;
    // With reduced motion, animations land instantly (start in the past).
    const now = performance.now();
    const start = reducedMotion() ? now - HOVER_MS : now;
    if (entering) leaving = { i: entering.i, from: hoverScaleOf(entering, now), to: 1, start };
    entering =
      i === null
        ? null
        : { i, from: leaving?.i === i ? hoverScaleOf(leaving, now) : 1, to: HOVER_SCALE, start };
    if (entering && leaving?.i === entering.i) leaving = null;
    const dimTarget = i === null ? BASE_ALPHA : DIM_ALPHA;
    if (dimTarget !== dimAnim.to) {
      dimAnim = { from: dimAlphaAt(now), to: dimTarget, start };
    }
    hovered = i;
    requestRaf();
  }

  /** The other half of the hovered point's training pair. */
  const siblingOf = (i: number): number =>
    points.findIndex((p, j) => j !== i && p.pair_id === points[i].pair_id);

  // ---- Drawing --------------------------------------------------------------
  function requestRaf() {
    if (rafHandle !== null) return;
    rafHandle = requestAnimationFrame(() => {
      rafHandle = null;
      draw();
    });
  }

  // Redraw on any reactive change.
  $effect(() => {
    void points;
    void axisView;
    void cssWidth;
    void cssHeight;
    void dpr;
    void hovered;
    draw();
  });

  // New data invalidates positions computed for the old points. Runs as a
  // pre-effect so the reset lands before the DOM re-renders against the new
  // point set. Plain assignments only: calling setHovered here would read
  // `hovered` and make this effect re-run on every hover, wiping it out.
  $effect.pre(() => {
    void mapState.data;
    transition = null;
    entering = null;
    leaving = null;
    hovered = null;
  });

  function draw() {
    if (!ctx || !canvas || cssWidth === 0 || cssHeight === 0) return;
    const c = ctx;
    const w = cssWidth;
    const h = cssHeight;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, w, h);
    if (points.length === 0) return;

    const targets = currentTargets(w, h);
    const now = performance.now();
    let animating = false;

    if (drawnX.length !== points.length) {
      drawnX = new Array(points.length);
      drawnY = new Array(points.length);
    }
    for (let i = 0; i < points.length; i++) {
      let x = targets[i].x;
      let y = targets[i].y;
      if (transition) {
        const t = clamp01((now - transition.start - transition.delays[i]) / TRANSITION_MS);
        if (t < 1) animating = true;
        const e = easeInOut(t);
        x = transition.fromFx[i] * w + (x - transition.fromFx[i] * w) * e;
        y = transition.fromFy[i] * h + (y - transition.fromFy[i] * h) * e;
      }
      drawnX[i] = x;
      drawnY[i] = y;
    }
    if (!animating) transition = null;

    // Expired hover animations settle.
    if (leaving && now - leaving.start >= HOVER_MS) leaving = null;
    const hoverAnimating =
      (entering !== null && now - entering.start < HOVER_MS) ||
      leaving !== null ||
      now - dimAnim.start < HOVER_MS;

    const sibling = hovered !== null ? siblingOf(hovered) : -1;

    // Pair link first, underneath the dots: a gentle bow so it reads as a
    // deliberate connection in both layouts.
    if (hovered !== null && sibling >= 0 && !animating) {
      const x1 = drawnX[hovered];
      const y1 = drawnY[hovered];
      const x2 = drawnX[sibling];
      const y2 = drawnY[sibling];
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.hypot(dx, dy) || 1;
      const bow = Math.min(26, len * 0.18);
      c.globalAlpha = 0.45;
      c.strokeStyle = colors.ink;
      c.lineWidth = 1;
      c.setLineDash([4, 4]);
      c.beginPath();
      c.moveTo(x1, y1);
      c.quadraticCurveTo(mx - (dy / len) * bow, my + (dx / len) * bow, x2, y2);
      c.stroke();
      c.setLineDash([]);
      c.globalAlpha = 1;
    }

    // Dots. The hovered dot and its sibling draw last so they sit on top.
    const restAlpha = animating ? BASE_ALPHA : dimAlphaAt(now);
    const late: number[] = [];
    for (let i = 0; i < points.length; i++) {
      if (i === hovered || i === sibling || i === leaving?.i) {
        late.push(i);
        continue;
      }
      drawDot(c, i, 1, restAlpha, false);
    }
    for (const i of late) {
      const isHover = entering?.i === i;
      const scale = isHover
        ? hoverScaleOf(entering!, now)
        : leaving?.i === i
          ? hoverScaleOf(leaving, now)
          : 1;
      drawDot(c, i, scale, 1, i === sibling && i !== hovered);
    }

    if (animating || hoverAnimating) requestRaf();
  }

  function drawDot(
    c: CanvasRenderingContext2D,
    i: number,
    scale: number,
    alpha: number,
    ring: boolean,
  ) {
    c.globalAlpha = alpha;
    c.beginPath();
    c.arc(drawnX[i], drawnY[i], DOT_R * scale, 0, Math.PI * 2);
    c.fillStyle = points[i].role === "ai" ? colors.ai : colors.human;
    c.fill();
    if (scale > 1 || ring) {
      c.lineWidth = ring ? 2 : 1.5;
      c.strokeStyle = colors.surface;
      c.stroke();
    }
    c.globalAlpha = 1;
  }

  // ---- Pointer & keyboard ---------------------------------------------------
  function nearestPoint(sx: number, sy: number): number | null {
    let best = -1;
    let bestDist = HIT_RADIUS;
    for (let i = 0; i < drawnX.length; i++) {
      const d = Math.hypot(drawnX[i] - sx, drawnY[i] - sy);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    }
    return best >= 0 ? best : null;
  }

  function localXY(e: PointerEvent): [number, number] {
    const rect = canvas!.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  function onPointerMove(e: PointerEvent) {
    if (transition) return; // positions are in flight; hover would mislead
    const [sx, sy] = localXY(e);
    setHovered(nearestPoint(sx, sy));
  }

  function onPointerLeave() {
    setHovered(null);
  }

  // Keyboard reach: focus the canvas, then arrows walk the points in score
  // order (the order the axis view draws them in), Home/End jump, Esc clears.
  const scoreOrder = $derived(
    points.map((_, i) => i).sort((a, b) => points[a].score - points[b].score),
  );

  function onKeydown(e: KeyboardEvent) {
    if (points.length === 0) return;
    const order = scoreOrder;
    const pos = hovered === null ? -1 : order.indexOf(hovered);
    let next: number | null | undefined;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      next = order[Math.min(order.length - 1, pos + 1)];
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      next = order[pos <= 0 ? 0 : pos - 1];
    } else if (e.key === "Home") {
      next = order[0];
    } else if (e.key === "End") {
      next = order[order.length - 1];
    } else if (e.key === "Escape") {
      next = null;
    } else {
      return;
    }
    e.preventDefault();
    setHovered(next ?? null);
  }

  // ---- Tooltip ---------------------------------------------------------------
  // Anchored to the hovered dot, flipping sides near the canvas edges so it
  // never clips. Positions come from the drawn arrays, which are stable while
  // hovering (hover is suppressed mid-transition).
  const TOOLTIP_W = 264;
  /** Rendered tooltip height never exceeds this (head + five clamped lines);
   *  an above-placement needs at least this much room over the dot. */
  const TOOLTIP_MAX_H = 170;
  const tooltip = $derived.by(() => {
    if (hovered === null || cssWidth === 0) return null;
    // Belt over the reset pre-effect: never index past a freshly-shrunk set.
    if (hovered >= points.length || hovered >= drawnX.length) return null;
    const p = points[hovered];
    const x = drawnX[hovered];
    const y = drawnY[hovered];
    const alignRight = x + 14 + TOOLTIP_W > cssWidth;
    const below = y < TOOLTIP_MAX_H + 12;
    return { p, x, y, alignRight, below };
  });

  function tooltipStyle(t: NonNullable<typeof tooltip>): string {
    const x = t.alignRight ? `left: ${t.x - 14}px; transform: translateX(-100%)` : `left: ${t.x + 14}px`;
    const y = t.below ? `top: ${t.y + 12}px` : `top: ${t.y - 12}px; translate: 0 -100%`;
    return `${x}; ${y};`;
  }

  const roleLabel = (p: MapPoint) => (p.role === "ai" ? "AI version" : "Your version");

  const caption = $derived(
    axisView
      ? "The same texts on the axis Litmus scores against — your writing lands right of zero, AI drafts left."
      : `Each dot is one text from your library, placed by similarity (${(mapState.data?.method ?? "").toUpperCase()} projection). Hover a dot — its pair partner lights up.`,
  );

  const canvasLabel = $derived(
    `${axisView ? "Axis" : "Map"} of ${points.length} library texts. ` +
      "Focus the chart and use the arrow keys to walk through the points.",
  );
</script>

<section aria-label="Map of your training library">
  {#if !calibrated}
    <div class="panel-note">
      <h3 class="serif">Teach it your voice first</h3>
      <p>
        The map draws every text in your library — AI drafts beside your versions. Add
        {library.examples.length === 1 ? "one more pair" : "two pairs"} and the picture appears.
      </p>
      <button class="btn btn-primary" onclick={onOpenLibrary}>
        {library.examples.length === 1 ? "Add one more pair" : "Open the library"}
      </button>
    </div>
  {:else if mapState.error}
    <div class="panel-note" role="alert">
      <h3 class="serif">Couldn’t draw the map</h3>
      <p class="error-text">{mapState.error.message}</p>
      {#if mapState.error.status === 409}
        <button class="btn btn-primary" onclick={onOpenLibrary}>Add training pairs</button>
      {:else}
        <button class="btn" onclick={() => loadMap()}>Try again</button>
      {/if}
    </div>
  {:else if !mapState.data}
    <div class="map-shell">
      <div class="map-head" aria-hidden="true">
        <div class="head-ghost skeleton"></div>
      </div>
      <div class="card map-card loading" aria-live="polite">
        <span class="spinner spinner-dark"></span>
        <p>Embedding your library…</p>
      </div>
    </div>
  {:else}
    <div class="map-shell">
      <div class="map-head">
        <div class="seg" role="group" aria-label="Map layout">
          <button
            class:active={!axisView}
            aria-pressed={!axisView}
            title="Lay the texts out by overall similarity"
            onclick={() => setView("map")}
          >
            Map
          </button>
          <button
            class:active={axisView}
            aria-pressed={axisView}
            title="Line the texts up on the AI–human scoring axis"
            onclick={() => setView("axis")}
          >
            Axis
          </button>
        </div>
        <span class="count">{mapState.data.pairs} pairs</span>
      </div>

      <div class="card map-card" class:refreshing>
        <div class="map-host" bind:this={host}>
          <!-- Axis chrome fades in under the dots when the swarm forms. -->
          <div class="axis-chrome" class:visible={axisView} aria-hidden="true">
            <span class="micro-label pole pole-ai" style="left: {poleInset}px">AI</span>
            <span class="micro-label pole pole-human" style="right: {poleInset}px">Human</span>
            <div class="zero-line"></div>
            <div class="axis-scale" style="left: {axisPadX}px; right: {axisPadX}px">
              <div class="litmus-strip"></div>
              {#each ticks as t, i (i)}
                <div class="tick" class:zero={t === 0} style="left: {(i / (ticks.length - 1)) * 100}%">
                  <span class="micro-label tick-num">{tickLabel(t)}</span>
                </div>
              {/each}
            </div>
          </div>
          <canvas
            bind:this={canvas}
            tabindex="0"
            aria-label={canvasLabel}
            onpointermove={onPointerMove}
            onpointerdown={onPointerMove}
            onpointerleave={onPointerLeave}
            onkeydown={onKeydown}
            onblur={onPointerLeave}
          ></canvas>
          {#if tooltip}
            <div class="tooltip" style={tooltipStyle(tooltip)} role="presentation">
              <div class="tooltip-head">
                <span class="micro-label dot-marker {tooltip.p.role}">{roleLabel(tooltip.p)}</span>
                <span
                  class="tooltip-score"
                  class:ai={tooltip.p.score < 0}
                  class:human={tooltip.p.score > 0}>{fmtScore(tooltip.p.score)}</span
                >
              </div>
              <p class="tooltip-text">{tooltip.p.snippet}{tooltip.p.truncated ? "…" : ""}</p>
            </div>
          {/if}
          <!-- Announce the walked-to point for screen readers. -->
          <span class="sr-only" aria-live="polite">
            {#if hovered !== null && points[hovered]}
              {roleLabel(points[hovered])}, score {fmtScore(points[hovered].score)}:
              {points[hovered].snippet}
            {/if}
          </span>
        </div>
        {#if refreshing}
          <span class="updating-pill" role="status">
            <span class="spinner spinner-dark"></span>
            Updating…
          </span>
        {/if}
      </div>

      <p class="caption">{caption}</p>
    </div>
  {/if}
</section>

<style>
  .map-shell {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .map-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    min-height: 28px;
  }

  .head-ghost {
    width: 132px;
    height: 28px;
    border-radius: var(--radius-sm);
  }

  .count {
    font-size: var(--text-body);
    color: var(--ink-secondary);
  }

  .map-card {
    position: relative;
  }

  /* Dim the stale picture, not the pill that says it's being replaced. */
  .map-host {
    transition: opacity 200ms var(--ease);
  }

  .map-card.refreshing .map-host {
    opacity: 0.55;
  }

  .map-card.loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    height: clamp(340px, 52vh, 540px);
    color: var(--ink-secondary);
  }

  .map-host {
    position: relative;
    height: clamp(340px, 52vh, 540px);
  }

  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
    border-radius: var(--radius);
    touch-action: none;
  }

  canvas:focus-visible {
    outline: 2px solid var(--ink);
    outline-offset: -2px;
  }

  /* ---------- Axis chrome ---------- */
  .axis-chrome {
    position: absolute;
    inset: 0;
    opacity: 0;
    transition: opacity var(--speed-slow) var(--ease);
    pointer-events: none;
  }

  .axis-chrome.visible {
    opacity: 1;
  }

  .pole {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
  }

  /* Horizontal insets of the poles and the scale are set inline from the
     component's layout constants. */
  .pole-ai {
    color: var(--ai);
  }

  .pole-human {
    color: var(--human);
  }

  .axis-scale {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    height: 12px;
  }

  .litmus-strip {
    position: absolute;
    inset: 0;
  }

  .zero-line {
    position: absolute;
    left: 50%;
    top: 14%;
    bottom: 14%;
    border-left: 1px dashed var(--border-strong);
  }

  .tick {
    position: absolute;
    top: 18px;
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

  /* ---------- Tooltip ---------- */
  .tooltip {
    position: absolute;
    width: max-content;
    max-width: 264px; /* = TOOLTIP_W */
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-toast);
    padding: 9px 11px 10px;
    pointer-events: none;
    z-index: 2;
  }

  .tooltip-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 14px;
    margin-bottom: 5px;
  }

  .tooltip-score {
    font-size: var(--text-micro);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--ink-2);
  }

  .tooltip-score.ai {
    color: var(--ai);
  }

  .tooltip-score.human {
    color: var(--human);
  }

  .tooltip-text {
    font-size: var(--text-body);
    line-height: 1.5;
    color: var(--ink);
    display: -webkit-box;
    -webkit-line-clamp: 5;
    line-clamp: 5;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: break-word;
  }

  /* ---------- States ---------- */
  .updating-pill {
    position: absolute;
    top: 12px;
    right: 12px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 4px 10px;
    font-size: var(--text-body);
    font-weight: 500;
    color: var(--ink-secondary);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 999px;
  }

  .caption {
    text-align: center;
    font-size: var(--text-body);
    color: var(--ink-secondary);
    text-wrap: balance;
  }

  @media (max-width: 560px) {
    .map-host,
    .map-card.loading {
      height: clamp(300px, 48vh, 420px);
    }
  }
</style>
