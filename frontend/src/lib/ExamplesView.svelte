<script lang="ts">
  import { DownloadSimple, PencilSimple, Plus, Trash, UploadSimple } from "phosphor-svelte";
  import { api } from "./api";
  import PairEditor from "./PairEditor.svelte";
  import { toast } from "./toast";
  import type { Example, PairInput } from "./types";

  let examples = $state<Example[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);

  let adding = $state(false);
  let editingId = $state<number | null>(null);
  let confirmDeleteId = $state<number | null>(null);
  let saving = $state(false);
  let deletingId = $state<number | null>(null);
  let importing = $state(false);
  let exporting = $state(false);
  let expanded = $state<Set<number>>(new Set());

  let fileInput: HTMLInputElement;

  // A pair is "long" when either side would overflow the collapsed clamp.
  const CLAMP_CHARS = 420;

  async function load() {
    loading = true;
    loadError = null;
    try {
      examples = await api.listExamples();
    } catch (err) {
      loadError = errMessage(err);
    } finally {
      loading = false;
    }
  }

  load();

  function errMessage(err: unknown): string {
    return err instanceof Error ? err.message : "Something went wrong.";
  }

  function startAdd() {
    adding = true;
    editingId = null;
    confirmDeleteId = null;
  }

  function startEdit(id: number) {
    editingId = id;
    adding = false;
    confirmDeleteId = null;
  }

  async function saveNew(pair: PairInput) {
    saving = true;
    try {
      const row = await api.createExample(pair);
      examples = [...examples, row];
      adding = false;
      toast("success", "Training pair added.");
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      saving = false;
    }
  }

  async function saveEdit(id: number, pair: PairInput) {
    saving = true;
    try {
      const row = await api.updateExample(id, pair);
      examples = examples.map((e) => (e.id === id ? row : e));
      editingId = null;
      toast("success", "Training pair updated.");
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      saving = false;
    }
  }

  async function doDelete(id: number) {
    deletingId = id;
    try {
      await api.deleteExample(id);
      examples = examples.filter((e) => e.id !== id);
      toast("success", "Training pair deleted.");
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      deletingId = null;
      confirmDeleteId = null;
    }
  }

  function toggleExpand(id: number) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    expanded = next;
  }

  async function onFilePicked(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ""; // allow re-picking the same file
    if (!file) return;

    let parsed: unknown;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      toast("error", `"${file.name}" is not valid JSON.`);
      return;
    }
    if (!Array.isArray(parsed)) {
      toast("error", 'Import expects a JSON array of {"ai", "human"} objects.');
      return;
    }
    if (parsed.length === 0) {
      toast("error", "The file contains an empty array — nothing to import.");
      return;
    }

    importing = true;
    try {
      const result = await api.importExamples(parsed as PairInput[]);
      const skipped = result.total - result.imported;
      toast(
        "success",
        `Imported ${result.imported} of ${result.total} pair${result.total === 1 ? "" : "s"}` +
          (skipped > 0 ? ` (${skipped} skipped).` : "."),
      );
      await load();
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      importing = false;
    }
  }

  async function doExport() {
    exporting = true;
    try {
      const pairs = await api.exportExamples();
      const blob = new Blob([JSON.stringify(pairs, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "examples.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      exporting = false;
    }
  }

  function formatDate(iso: string): string {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }
</script>

<section aria-label="Training examples">
  <div class="toolbar">
    <p class="count" aria-live="polite">
      {#if loading}
        Loading…
      {:else if loadError}
        &nbsp;
      {:else}
        {examples.length} pair{examples.length === 1 ? "" : "s"}
        {#if examples.length === 1}
          <span class="count-note">— add one more to enable scoring</span>
        {/if}
      {/if}
    </p>
    <div class="toolbar-actions">
      <input
        bind:this={fileInput}
        type="file"
        accept=".json,application/json"
        class="sr-only"
        onchange={onFilePicked}
      />
      <button class="btn" onclick={() => fileInput.click()} disabled={importing || loading}>
        {#if importing}<span class="spinner spinner-dark"></span>{:else}<UploadSimple size={15} />{/if}
        Import
      </button>
      <button
        class="btn"
        onclick={doExport}
        disabled={exporting || loading || examples.length === 0}
        title={examples.length === 0 && !loading ? "No pairs to export yet" : undefined}
      >
        {#if exporting}<span class="spinner spinner-dark"></span>{:else}<DownloadSimple size={15} />{/if}
        Export
      </button>
      <button class="btn btn-primary" onclick={startAdd} disabled={adding || loading}>
        <Plus size={15} weight="bold" />
        Add pair
      </button>
    </div>
  </div>

  {#if adding}
    <div class="editor-slot">
      <PairEditor
        initial={{ ai: "", human: "" }}
        heading="New training pair"
        saveLabel="Add pair"
        {saving}
        onSave={saveNew}
        onCancel={() => (adding = false)}
      />
    </div>
  {/if}

  {#if loading}
    <div class="skeletons" aria-hidden="true">
      {#each [0, 1, 2] as i (i)}
        <div class="card skeleton"></div>
      {/each}
    </div>
  {:else if loadError}
    <div class="card panel-note">
      <h3>Couldn’t load your examples</h3>
      <p>{loadError}</p>
      <button class="btn btn-primary" onclick={load}>Try again</button>
    </div>
  {:else if examples.length === 0 && !adding}
    <div class="card panel-note">
      <h3>No training pairs yet</h3>
      <p>
        Each pair holds an AI-written version and your own version of the same content. From two
        pairs up, the detector learns what your voice sounds like.
      </p>
      <div class="empty-actions">
        <button class="btn btn-primary" onclick={startAdd}>Add your first pair</button>
        <button class="btn" onclick={() => fileInput.click()}>Import JSON</button>
      </div>
    </div>
  {:else}
    <div class="list-head" aria-hidden="true">
      <span class="micro-label col-label ai">AI version</span>
      <span class="micro-label col-label human">Your version</span>
    </div>
    <ul class="pairs">
      {#each examples as ex (ex.id)}
        <li>
          {#if editingId === ex.id}
            <PairEditor
              initial={{ ai: ex.ai, human: ex.human }}
              heading="Edit training pair"
              saveLabel="Save changes"
              {saving}
              onSave={(pair) => saveEdit(ex.id, pair)}
              onCancel={() => (editingId = null)}
            />
          {:else}
            <article class="card pair">
              <div class="pair-body" class:collapsed={!expanded.has(ex.id)}>
                <div class="side">
                  <span class="side-label dot-label ai">AI</span>
                  <p>{ex.ai}</p>
                </div>
                <div class="side">
                  <span class="side-label dot-label human">Human</span>
                  <p>{ex.human}</p>
                </div>
              </div>
              <footer>
                <span class="meta" title={ex.created_at}>{formatDate(ex.created_at)}</span>
                {#if ex.ai.length > CLAMP_CHARS || ex.human.length > CLAMP_CHARS}
                  <button class="show-more" onclick={() => toggleExpand(ex.id)}>
                    {expanded.has(ex.id) ? "Show less" : "Show more"}
                  </button>
                {/if}
                <span class="spacer"></span>
                {#if confirmDeleteId === ex.id}
                  <span class="confirm-label">Delete this pair?</span>
                  <button
                    class="btn btn-danger small"
                    onclick={() => doDelete(ex.id)}
                    disabled={deletingId === ex.id}
                  >
                    {#if deletingId === ex.id}<span class="spinner"></span>{/if}
                    Delete
                  </button>
                  <button
                    class="btn btn-ghost small"
                    onclick={() => (confirmDeleteId = null)}
                    disabled={deletingId === ex.id}
                  >
                    Cancel
                  </button>
                {:else}
                  <div class="row-actions">
                    <button
                      class="icon-btn"
                      aria-label="Edit pair"
                      title="Edit"
                      onclick={() => startEdit(ex.id)}
                    >
                      <PencilSimple size={15} />
                    </button>
                    <button
                      class="icon-btn danger"
                      aria-label="Delete pair"
                      title="Delete"
                      onclick={() => (confirmDeleteId = ex.id)}
                    >
                      <Trash size={15} />
                    </button>
                  </div>
                {/if}
              </footer>
            </article>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }

  .count {
    font-size: 13.5px;
    color: var(--ink-secondary);
    font-weight: 500;
  }

  .count-note {
    font-weight: 400;
    color: var(--ink-faint);
  }

  .toolbar-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }

  .editor-slot {
    margin-bottom: 16px;
  }

  .skeletons {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .skeleton {
    height: 128px;
    background: linear-gradient(90deg, var(--surface) 25%, hsl(220 14% 95%) 50%, var(--surface) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite;
  }

  @keyframes shimmer {
    from {
      background-position: 200% 0;
    }
    to {
      background-position: -200% 0;
    }
  }

  .empty-actions {
    display: flex;
    gap: 8px;
    justify-content: center;
    flex-wrap: wrap;
  }

  /* Column headers for the whole list; card grids align because they share
     the same horizontal padding and column gap. */
  .list-head {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 40px;
    padding: 0 19px;
    margin-bottom: 8px;
  }

  .col-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .col-label::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .col-label.ai::before {
    background: var(--ai);
  }

  .col-label.human::before {
    background: var(--human);
  }

  /* Per-side chips are redundant next to the header row; they only come
     back on mobile where the columns stack. */
  .side-label {
    display: none;
  }

  .pairs {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .pair {
    padding: 15px 18px 9px;
    transition: border-color var(--speed) var(--ease);
  }

  .pair:hover {
    border-color: var(--border-strong);
  }

  .pair-body {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .side {
    min-width: 0;
  }

  .side:first-child {
    padding-right: 20px;
  }

  .side:last-child {
    padding-left: 20px;
    border-left: 1px solid var(--border);
  }

  .side p {
    margin: 0;
    font-size: 13.5px;
    color: var(--ink);
    white-space: pre-wrap;
    overflow-wrap: break-word;
  }

  .pair-body.collapsed .side p {
    display: -webkit-box;
    -webkit-line-clamp: 4;
    line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  footer {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 8px;
    min-height: 28px;
  }

  .meta {
    font-size: 12px;
    color: var(--ink-faint);
  }

  .show-more {
    appearance: none;
    border: none;
    background: none;
    padding: 0;
    font-size: 12px;
    color: var(--ink-faint);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .show-more:hover {
    color: var(--ink);
  }

  .spacer {
    flex: 1;
  }

  .row-actions {
    display: flex;
    align-items: center;
    gap: 4px;
    opacity: 0;
    transition: opacity var(--speed) var(--ease);
  }

  .pair:hover .row-actions,
  .pair:focus-within .row-actions {
    opacity: 1;
  }

  @media (hover: none) {
    .row-actions {
      opacity: 1;
    }
  }

  .icon-btn.danger:hover:not(:disabled) {
    background: var(--danger-soft);
    color: var(--danger);
  }

  .confirm-label {
    font-size: 12.5px;
    color: var(--danger);
    font-weight: 500;
  }

  @media (max-width: 720px) {
    .list-head {
      display: none;
    }

    .pair-body {
      grid-template-columns: 1fr;
      gap: 14px;
    }

    .side:first-child {
      padding-right: 0;
    }

    .side:last-child {
      padding-left: 0;
      border-left: none;
    }

    .side-label {
      display: inline-flex;
      margin-bottom: 7px;
    }
  }
</style>
