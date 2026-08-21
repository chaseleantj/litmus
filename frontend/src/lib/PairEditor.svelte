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
  <!-- The library's column headers sit directly above this editor and label
       both columns, so the fields only name themselves once they stack. -->
  <div class="pair-cols">
    <div class="field">
      <span class="micro-label ai stacked-only">AI version</span>
      <textarea
        bind:value={ai}
        rows="7"
        aria-label="AI version"
        placeholder="Paste the AI-written version of the text…"
        disabled={saving}
      ></textarea>
    </div>
    <div class="field">
      <span class="micro-label human stacked-only">Your version</span>
      <textarea
        bind:value={human}
        rows="7"
        aria-label="Your version"
        placeholder="Paste your own version of the same content…"
        disabled={saving}
      ></textarea>
    </div>
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
    padding: 18px 18px 16px;
  }

  h3 {
    font-size: var(--text-title);
    margin-bottom: 14px;
  }

  .field {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    min-width: 0;
  }

  .field textarea {
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
    font-size: var(--text-body);
    color: var(--faint);
  }
</style>
