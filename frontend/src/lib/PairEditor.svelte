<script lang="ts">
  import type { PairInput } from "./types";

  interface Props {
    /** Initial values; empty strings for a new pair. */
    initial: PairInput;
    heading: string;
    saveLabel: string;
    saving: boolean;
    onSave: (pair: PairInput) => void;
    onCancel: () => void;
  }

  let { initial, heading, saveLabel, saving, onSave, onCancel }: Props = $props();

  // Deliberately captures the initial value: the editor owns its draft, and
  // each add/edit session mounts a fresh instance.
  // svelte-ignore state_referenced_locally
  let ai = $state(initial.ai);
  // svelte-ignore state_referenced_locally
  let human = $state(initial.human);

  const valid = $derived(ai.trim().length > 0 && human.trim().length > 0);
  const dirty = $derived(ai !== initial.ai || human !== initial.human);

  function submit(e: SubmitEvent) {
    e.preventDefault();
    if (valid && !saving) onSave({ ai: ai.trim(), human: human.trim() });
  }
</script>

<form class="card editor" onsubmit={submit}>
  <h3>{heading}</h3>
  <div class="fields">
    <label>
      <span class="tag tag-ai">AI version</span>
      <textarea
        bind:value={ai}
        rows="7"
        placeholder="Paste the AI-written version of the text…"
        disabled={saving}
      ></textarea>
    </label>
    <label>
      <span class="tag tag-human">Human version</span>
      <textarea
        bind:value={human}
        rows="7"
        placeholder="Paste your own version of the same content…"
        disabled={saving}
      ></textarea>
    </label>
  </div>
  <div class="actions">
    <span class="hint" aria-live="polite">
      {#if !valid}Both versions are required.{/if}
    </span>
    <button type="button" class="btn btn-ghost" onclick={onCancel} disabled={saving}>
      Cancel
    </button>
    <button
      type="submit"
      class="btn btn-primary"
      disabled={!valid || saving || !dirty}
      title={!valid ? "Fill in both versions first" : !dirty ? "No changes to save" : undefined}
    >
      {#if saving}<span class="spinner"></span>{/if}
      {saveLabel}
    </button>
  </div>
</form>

<style>
  .editor {
    padding: 20px;
  }

  h3 {
    font-family: var(--font-serif);
    font-size: 18px;
    margin-bottom: 14px;
  }

  .fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  label {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  label textarea {
    align-self: stretch;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 14px;
  }

  .hint {
    margin-right: auto;
    font-size: 13px;
    color: var(--ink-faint);
  }

  @media (max-width: 720px) {
    .fields {
      grid-template-columns: 1fr;
    }
  }
</style>
