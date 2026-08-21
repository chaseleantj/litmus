<script lang="ts">
  import { CheckCircle, WarningCircle, X } from "phosphor-svelte";
  import { dismissToast, toasts } from "./toast";
</script>

<div class="toasts" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div class="toast {t.kind}">
      {#if t.kind === "success"}
        <CheckCircle size={16} weight="fill" />
      {:else}
        <WarningCircle size={16} weight="fill" />
      {/if}
      <span>{t.message}</span>
      <button aria-label="Dismiss notification" onclick={() => dismissToast(t.id)}>
        <X size={13} weight="bold" />
      </button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 100;
    width: min(400px, calc(100vw - 32px));
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 10px 14px;
    border-radius: var(--radius-ctl);
    box-shadow: var(--shadow-float);
    font-size: var(--text-body);
    animation: toast-rise 0.35s var(--ease-out);
  }

  .toast > span {
    flex: 1;
    min-width: 0;
  }

  .toast.success {
    background: var(--ink);
    color: var(--bg);
  }

  .toast.error {
    background: var(--danger);
    color: var(--bg);
  }

  .toast button {
    appearance: none;
    /* WCAG 2.2 minimum target — it is the only way to dismiss early. */
    width: 24px;
    height: 24px;
    flex-shrink: 0;
    border: none;
    background: none;
    color: inherit;
    opacity: 0.65;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-xs);
  }

  .toast button:hover {
    opacity: 1;
  }

  .toast button:focus-visible {
    outline-color: var(--bg);
  }

  @keyframes toast-rise {
    from {
      opacity: 0;
      transform: translateY(8px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }
</style>
