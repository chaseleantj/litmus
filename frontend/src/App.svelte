<script lang="ts">
  // Legacy reassembly: header, tab bar and shell restored from 745fda9
  // (masthead + tagline, underline tabs, full-width mock banner, 1060px
  // shell), with a third tab for the newer Visualization view.
  import { mockActive } from "./lib/api";
  import DetectView from "./lib/DetectView.svelte";
  import ExamplesView from "./lib/ExamplesView.svelte";
  import MapView from "./lib/MapView.svelte";
  import Toasts from "./lib/Toasts.svelte";
  import { loadLibrary } from "./lib/library.svelte";

  type Tab = "examples" | "compare" | "map";

  function tabFromHash(): Tab {
    if (location.hash === "#/compare") return "compare";
    if (location.hash === "#/map") return "map";
    return "examples";
  }

  let tab = $state<Tab>(tabFromHash());

  function goTo(next: Tab) {
    tab = next;
    const hash = next === "compare" ? "#/compare" : next === "map" ? "#/map" : "#/examples";
    history.replaceState(null, "", hash);
  }

  $effect(() => {
    const onHash = () => (tab = tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });

  loadLibrary();
</script>

<div class="shell">
  <header>
    <div class="masthead">
      <h1>Write like me</h1>
      <p class="tagline">Teach it your voice, then hear which text sounds more human.</p>
    </div>
    <nav aria-label="Views">
      <button
        class:active={tab === "examples"}
        aria-current={tab === "examples" ? "page" : undefined}
        onclick={() => goTo("examples")}
      >
        Training examples
      </button>
      <button
        class:active={tab === "compare"}
        aria-current={tab === "compare" ? "page" : undefined}
        onclick={() => goTo("compare")}
      >
        Compare
      </button>
      <button
        class:active={tab === "map"}
        aria-current={tab === "map" ? "page" : undefined}
        onclick={() => goTo("map")}
      >
        Visualization
      </button>
    </nav>
    {#if $mockActive}
      <div class="mock-banner" role="status">
        Backend unreachable — running on sample data. Changes are not saved.
      </div>
    {/if}
  </header>

  <main>
    {#if tab === "examples"}
      <ExamplesView onGoCompare={() => goTo("compare")} />
    {:else if tab === "compare"}
      <DetectView onGoExamples={() => goTo("examples")} />
    {:else}
      <MapView onOpenLibrary={() => goTo("examples")} />
    {/if}
  </main>
</div>

<Toasts />

<style>
  .shell {
    max-width: 1060px;
    margin: 0 auto;
    padding: 28px 20px 64px;
  }

  .masthead h1 {
    font-size: 23px;
    font-weight: 600;
    letter-spacing: -0.015em;
  }

  .tagline {
    color: var(--ink-secondary);
    margin-top: 2px;
  }

  nav {
    display: flex;
    gap: 4px;
    margin-top: 20px;
    border-bottom: 1px solid var(--border);
  }

  nav button {
    appearance: none;
    border: none;
    background: none;
    padding: 9px 14px;
    font-weight: 500;
    color: var(--ink-secondary);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color var(--speed) var(--ease);
  }

  nav button:hover {
    color: var(--ink);
  }

  nav button.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  nav button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    border-radius: 4px;
  }

  .mock-banner {
    margin-top: 12px;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    background: #fdf3e0;
    border: 1px solid #ecd9ad;
    color: #7a5b17;
    font-size: 13px;
  }

  main {
    margin-top: 24px;
  }

  @media (max-width: 480px) {
    .shell {
      padding: 20px 14px 48px;
    }

    .masthead h1 {
      font-size: 20px;
    }
  }
</style>
