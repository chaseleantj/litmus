<script lang="ts">
  import { tick } from "svelte";
  import { Books } from "phosphor-svelte";
  import { mockActive } from "./lib/api";
  import { compareState, loadPair } from "./lib/compareState.svelte";
  import DetectView from "./lib/DetectView.svelte";
  import LibrarySheet from "./lib/LibrarySheet.svelte";
  import MapView from "./lib/MapView.svelte";
  import Toasts from "./lib/Toasts.svelte";
  import { loadLibrary } from "./lib/library.svelte";
  import type { Example } from "./lib/types";

  type View = "detect" | "map";

  // "#/examples" is the pre-redesign URL for the library.
  function libraryFromHash(): boolean {
    return location.hash === "#/library" || location.hash === "#/examples";
  }

  function viewFromHash(): View | null {
    if (location.hash === "#/map") return "map";
    if (location.hash === "" || location.hash === "#/" || location.hash === "#") return "detect";
    return null; // library hashes say nothing about the view underneath
  }

  let view = $state<View>(viewFromHash() ?? "detect");
  let libraryOpen = $state(libraryFromHash());
  let opener: HTMLElement | null = null;
  let detect = $state<ReturnType<typeof DetectView>>();

  const viewHash = () => (view === "map" ? "#/map" : "#/");

  function setView(next: View) {
    if (view === next) return;
    view = next;
    history.replaceState(null, "", viewHash());
  }

  function openLibrary() {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    libraryOpen = true;
    history.replaceState(null, "", "#/library");
  }

  function closeLibrary() {
    libraryOpen = false;
    history.replaceState(null, "", viewHash());
    opener?.focus();
    opener = null;
  }

  /**
   * A pair from the library, opened in the detector: the sheet closes, Detect
   * comes forward if the map was showing, and the two texts land in compare
   * mode already scoring. Focus goes to the first box rather than back to the
   * opener — the boxes are what the user was just sent to.
   */
  async function tryPair(pair: Example) {
    setView("detect");
    opener = null;
    closeLibrary();
    loadPair(pair.ai, pair.human, true);
    // Coming from the map, DetectView mounts with this change — wait for it
    // rather than reaching for a box that is not on the page yet.
    await tick();
    detect?.focusFirstText();
  }

  $effect(() => {
    const onHash = () => {
      libraryOpen = libraryFromHash();
      const next = viewFromHash();
      if (next !== null) view = next;
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  loadLibrary();
</script>

<!-- The shell owns the app's column width; comparing two texts needs the
     wider one, so the header rule always spans exactly the work beneath it. -->
<div class="shell" class:wide={view === "map" || compareState.mode === "pair"}>
  <header>
    <div class="brand">
      <h1 class="wordmark">Litmus</h1>
      <p class="tagline">A personal test for AI-sounding writing.</p>
    </div>
    <div class="header-side">
      {#if $mockActive}
        <span class="mock-note" role="status">Sample data — changes aren’t saved</span>
      {/if}
      <nav class="seg" aria-label="View">
        <button
          class:active={view === "detect"}
          aria-current={view === "detect" ? "page" : undefined}
          title="Score a text against your voice"
          onclick={() => setView("detect")}
        >
          Detect
        </button>
        <button
          class:active={view === "map"}
          aria-current={view === "map" ? "page" : undefined}
          title="See your whole library as a map"
          onclick={() => setView("map")}
        >
          Visualization
        </button>
      </nav>
      <button
        class="btn"
        onclick={openLibrary}
        title="Open the training library — the pairs Litmus measures against"
      >
        <Books size={15} />
        Calibrate
      </button>
    </div>
  </header>
  <div class="header-rule" aria-hidden="true"></div>

  <main>
    {#if view === "detect"}
      <DetectView bind:this={detect} onOpenLibrary={openLibrary} suspended={libraryOpen} />
    {:else}
      <MapView onOpenLibrary={openLibrary} />
    {/if}
  </main>
</div>

<LibrarySheet open={libraryOpen} onClose={closeLibrary} onTryPair={tryPair} />
<Toasts />

<style>
  .shell {
    --column: 700px;
    --gutter: 24px;
    max-width: calc(var(--column) + var(--gutter) * 2);
    min-height: 100dvh;
    margin: 0 auto;
    padding: 0 var(--gutter) 48px;
    display: flex;
    flex-direction: column;
    transition: max-width var(--speed-slow) var(--ease-out);
  }

  .shell.wide {
    --column: 920px;
  }

  /* The header travels with the work rather than pinning to the window, so
     the wordmark, its rule and the text box read as one block. The auto
     margins here and on main centre that block together. */
  header {
    margin-top: auto;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    padding: 26px 0 14px;
    animation: rise 0.55s var(--ease-out);
  }

  .brand {
    display: flex;
    align-items: baseline;
    gap: 14px;
    min-width: 0;
  }

  .wordmark {
    font-size: var(--text-display);
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.2;
  }

  .tagline {
    font-size: var(--text-body);
    color: var(--muted);
    white-space: nowrap;
    /* The row's flexible item: when the header runs out of room the tagline
       gives way with an ellipsis instead of overflowing under its neighbours. */
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .header-side {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .mock-note {
    font-size: var(--text-body);
    font-weight: 600;
    color: var(--human);
    white-space: nowrap;
  }

  /* The app's signature in one hairline: the litmus scale itself. */
  .header-rule {
    height: 2px;
    border-radius: var(--radius-pill);
    background: linear-gradient(
      90deg,
      color-mix(in srgb, var(--ai) 55%, transparent),
      color-mix(in srgb, var(--hairline-strong) 70%, transparent) 38%,
      color-mix(in srgb, var(--hairline-strong) 70%, transparent) 62%,
      color-mix(in srgb, var(--human) 55%, transparent)
    );
    animation: rise 0.55s var(--ease-out);
  }

  /* The work sits in the middle of whatever room is left under the header,
     so a page with no result yet reads as a composition rather than as
     content stranded at the top of an empty window. Auto margins rather than
     justify-content: a tall result then overflows downward, never upward. */
  main {
    margin-bottom: auto;
    padding-top: 40px;
    /* Biases the block upward: sitting on the true centre line reads low. */
    padding-bottom: 6vh;
    animation: rise 0.55s var(--ease-out) 0.06s backwards;
  }

  /* Beside the wordmark the tagline crowds the pills; under it, it doesn't. */
  @media (max-width: 920px) {
    header {
      align-items: flex-start;
    }

    .brand {
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;
    }

    .tagline {
      white-space: normal;
    }
  }

  @media (max-width: 560px) {
    .shell {
      padding: 0 16px 56px;
    }

    /* Brand takes the first row so the tagline can use the full width
       instead of wrapping into the leftover beside the pills. */
    header {
      flex-wrap: wrap;
    }

    .brand {
      flex: 1 0 100%;
    }

    .header-side {
      margin-left: auto;
    }

    .mock-note {
      display: none;
    }

    main {
      padding-top: 28px;
    }
  }
</style>
