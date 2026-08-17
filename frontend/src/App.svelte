<script lang="ts">
  import { Books } from "phosphor-svelte";
  import { mockActive } from "./lib/api";
  import { compareState } from "./lib/compareState.svelte";
  import DetectView from "./lib/DetectView.svelte";
  import LibrarySheet from "./lib/LibrarySheet.svelte";
  import Toasts from "./lib/Toasts.svelte";
  import { loadLibrary } from "./lib/library.svelte";

  // "#/examples" is the pre-redesign URL for the same place.
  function openFromHash(): boolean {
    return location.hash === "#/library" || location.hash === "#/examples";
  }

  let libraryOpen = $state(openFromHash());
  let opener: HTMLElement | null = null;

  function openLibrary() {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    libraryOpen = true;
    history.replaceState(null, "", "#/library");
  }

  function closeLibrary() {
    libraryOpen = false;
    history.replaceState(null, "", "#/");
    opener?.focus();
    opener = null;
  }

  $effect(() => {
    const onHash = () => (libraryOpen = openFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  loadLibrary();
</script>

<!-- The shell owns the app's column width; comparing two texts needs the
     wider one, so the header rule always spans exactly the work beneath it. -->
<div class="shell" class:wide={compareState.mode === "pair"}>
  <header>
    <div class="brand">
      <h1 class="wordmark serif">Litmus</h1>
      <p class="tagline">A personal test for AI-sounding writing.</p>
    </div>
    <div class="header-side">
      {#if $mockActive}
        <span class="mock-note" role="status">Sample data — changes aren’t saved</span>
      {/if}
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
    <DetectView onOpenLibrary={openLibrary} suspended={libraryOpen} />
  </main>
</div>

<LibrarySheet open={libraryOpen} onClose={closeLibrary} />
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
    transition: max-width var(--speed-slow) var(--ease);
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
  }

  .brand {
    display: flex;
    align-items: baseline;
    gap: 14px;
    min-width: 0;
  }

  .wordmark {
    font-size: var(--text-display);
    font-style: italic;
    line-height: 1.2;
  }

  .tagline {
    font-size: var(--text-body);
    color: var(--ink-secondary);
    white-space: nowrap;
  }

  .header-side {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .mock-note {
    font-size: var(--text-body);
    font-weight: 500;
    color: var(--human);
    white-space: nowrap;
  }

  /* The app's signature in one hairline: the litmus scale itself. */
  .header-rule {
    height: 2px;
    border-radius: 999px;
    background: linear-gradient(
      90deg,
      color-mix(in srgb, var(--ai) 55%, transparent),
      color-mix(in srgb, var(--border-strong) 70%, transparent) 38%,
      color-mix(in srgb, var(--border-strong) 70%, transparent) 62%,
      color-mix(in srgb, var(--human) 55%, transparent)
    );
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
  }

  /* Below this the tagline starts crowding the header pills. */
  @media (max-width: 920px) {
    .tagline {
      display: none;
    }
  }

  @media (max-width: 560px) {
    .shell {
      padding: 0 16px 56px;
    }

    .mock-note {
      display: none;
    }

    main {
      padding-top: 28px;
    }
  }
</style>
