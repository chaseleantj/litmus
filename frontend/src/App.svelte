<script lang="ts">
  import { mockActive } from "./lib/api";
  import DetectView from "./lib/DetectView.svelte";
  import ExamplesView from "./lib/ExamplesView.svelte";
  import Toasts from "./lib/Toasts.svelte";

  type Tab = "detect" | "examples";

  function tabFromHash(): Tab {
    return location.hash === "#/examples" ? "examples" : "detect";
  }

  let tab = $state<Tab>(tabFromHash());

  function goTo(next: Tab) {
    tab = next;
    history.replaceState(null, "", next === "examples" ? "#/examples" : "#/detect");
  }

  $effect(() => {
    const onHash = () => (tab = tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });
</script>

<div class="shell">
  <header>
    <div class="brand">
      <h1 class="wordmark">Personal AI Detector</h1>
      {#if $mockActive}
        <span class="mock-pill" role="status">Sample data — changes aren’t saved</span>
      {/if}
    </div>
  </header>

  <nav class="tabs" aria-label="Views">
    <button
      class:active={tab === "detect"}
      aria-current={tab === "detect" ? "page" : undefined}
      onclick={() => goTo("detect")}
    >
      Detect
    </button>
    <button
      class:active={tab === "examples"}
      aria-current={tab === "examples" ? "page" : undefined}
      onclick={() => goTo("examples")}
    >
      Examples
    </button>
  </nav>

  <main>
    {#if tab === "examples"}
      <ExamplesView onGoDetect={() => goTo("detect")} />
    {:else}
      <DetectView onGoExamples={() => goTo("examples")} />
    {/if}
  </main>
</div>

<Toasts />

<style>
  .shell {
    max-width: 980px;
    margin: 0 auto;
    padding: 0 24px 72px;
  }

  header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
    padding: 24px 0 8px;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  .wordmark {
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.3;
  }

  .mock-pill {
    font-size: 12px;
    font-weight: 500;
    color: var(--human);
    background: var(--human-soft);
    border: 1px solid color-mix(in srgb, var(--human) 15%, transparent);
    border-radius: 999px;
    padding: 2px 8px;
    white-space: nowrap;
  }

  .tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }

  .tabs button {
    appearance: none;
    border: none;
    background: none;
    margin-bottom: -1px;
    padding: 8px 14px;
    font-size: 13.5px;
    font-weight: 500;
    color: var(--ink-secondary);
    border-bottom: 2px solid transparent;
    transition:
      color var(--speed) var(--ease),
      border-color var(--speed) var(--ease);
  }

  .tabs button:hover:not(.active) {
    color: var(--ink-2);
  }

  .tabs button.active {
    color: var(--ink);
    border-bottom-color: var(--ink);
  }

  .tabs button:focus-visible {
    outline-offset: -2px;
  }

  main {
    margin-top: 24px;
  }

  @media (max-width: 560px) {
    .shell {
      padding: 0 16px 56px;
    }

    .mock-pill {
      display: none;
    }
  }
</style>
