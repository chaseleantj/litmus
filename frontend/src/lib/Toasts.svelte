<script lang="ts">
  import { dismissToast, toasts } from "./toast";
</script>

<div class="toasts" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div class="toast {t.kind}">
      <span>{t.message}</span>
      <button aria-label="Dismiss notification" onclick={() => dismissToast(t.id)}>×</button>
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
    width: min(420px, calc(100vw - 32px));
  }

  .toast {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow);
    font-size: 14px;
    animation: rise 180ms var(--ease);
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
    opacity: 0.7;
    font-size: 16px;
    line-height: 1;
    padding: 2px;
  }

  .toast button:hover {
    opacity: 1;
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
