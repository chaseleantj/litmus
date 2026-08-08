<script lang="ts">
  import { mockActive } from "./lib/api";
  import CompareView from "./lib/CompareView.svelte";
  import ExamplesView from "./lib/ExamplesView.svelte";
  import Toasts from "./lib/Toasts.svelte";

  type Tab = "examples" | "compare";

  function tabFromHash(): Tab {
    return location.hash === "#/compare" ? "compare" : "examples";
  }

  let tab = $state<Tab>(tabFromHash());

  function goTo(next: Tab) {
    tab = next;
    history.replaceState(null, "", next === "compare" ? "#/compare" : "#/examples");
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
      <span class="wordmark">Write like me</span>
      {#if $mockActive}
        <span class="mock-pill" role="status">Sample data — changes aren’t saved</span>
      {/if}
    </div>
    <nav class="seg" aria-label="Views">
      <button
        class:active={tab === "examples"}
        aria-current={tab === "examples" ? "page" : undefined}
        onclick={() => goTo("examples")}
      >
        Examples
      </button>
      <button
        class:active={tab === "compare"}
        aria-current={tab === "compare" ? "page" : undefined}
        onclick={() => goTo("compare")}
      >
        Compare
      </button>
    </nav>
  </header>

  <main>
    {#if tab === "examples"}
      <ExamplesView onGoCompare={() => goTo("compare")} />
    {:else}
      <CompareView onGoExamples={() => goTo("examples")} />
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
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 0;
    border-bottom: 1px solid var(--border);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .wordmark {
    font-size: 14.5px;
    font-weight: 600;
    letter-spacing: -0.015em;
  }

  .mock-pill {
    font-size: 11.5px;
    font-weight: 500;
    color: #8a6d1f;
    background: #fbf3e0;
    border: 1px solid #eee0ba;
    border-radius: 999px;
    padding: 3px 10px;
    white-space: nowrap;
  }

  .seg {
    display: flex;
    padding: 3px;
    gap: 2px;
    background: var(--surface-muted);
    border: 1px solid var(--border);
    border-radius: 999px;
  }

  .seg button {
    appearance: none;
    border: none;
    background: none;
    border-radius: 999px;
    padding: 5px 15px;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: -0.005em;
    color: var(--ink-secondary);
    transition:
      color var(--speed) var(--ease),
      background var(--speed) var(--ease),
      box-shadow var(--speed) var(--ease);
  }

  .seg button:hover:not(.active) {
    color: var(--ink);
  }

  .seg button.active {
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-sm);
  }

  .seg button:focus-visible {
    outline-offset: 1px;
  }

  main {
    margin-top: 28px;
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
