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
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-lg);
    font-size: 13.5px;
    animation: rise 180ms var(--ease);
  }

  .toast > span {
    flex: 1;
    min-width: 0;
  }

  .toast.success {
    background: var(--ink);
    color: #fff;
  }

  .toast.error {
    background: var(--danger);
    color: #fff;
  }

  .toast button {
    appearance: none;
    border: none;
    background: none;
    color: inherit;
    opacity: 0.65;
    padding: 3px;
    display: inline-flex;
    border-radius: 5px;
  }

  .toast button:hover {
    opacity: 1;
  }

  .toast button:focus-visible {
    outline-color: #fff;
  }

  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>
