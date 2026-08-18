<script lang="ts">
  // Legacy reassembly: markup and styles restored from 745fda9's
  // ExamplesView (full tab page, "AI version"/"Human version" pills on every
  // row, "Added {date}" footers, "Import JSON"/"Export JSON", always-visible
  // Edit/Delete/"Try in compare" text buttons, "Ready to test?" footer link,
  // 420-character "Show full text" heuristic), wired to the current library
  // store, with the pairs-added histogram in its first version (0b99987).
  import { compareState as cs, queueRun, setMode } from "./compareState.svelte";
  import {
    addPair,
    deletePair,
    importPairs,
    library,
    loadLibrary,
    updatePair,
  } from "./library.svelte";
  import LibraryHistogram from "./LibraryHistogram.svelte";
  import PairEditor from "./PairEditor.svelte";
  import { toast } from "./toast";
  import type { Example, PairInput } from "./types";

  interface Props {
    onGoCompare: () => void;
  }

  let { onGoCompare }: Props = $props();

  let adding = $state(false);
  let editingId = $state<number | null>(null);
  let confirmDeleteId = $state<number | null>(null);
  let saving = $state(false);
  let deletingId = $state<number | null>(null);
  let importing = $state(false);
  let expanded = $state<Set<number>>(new Set());

  let fileInput: HTMLInputElement;

  // A pair is "long" when either side would overflow the collapsed clamp.
  const CLAMP_CHARS = 420;

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
      await addPair(pair);
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
      await updatePair(id, pair);
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
      await deletePair(id);
      toast("success", "Training pair deleted.");
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      deletingId = null;
      confirmDeleteId = null;
    }
  }

  function tryInCompare(ex: Example) {
    setMode("pair");
    cs.first = ex.ai;
    cs.second = ex.human;
    queueRun();
    onGoCompare();
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

    const valid = parsed.filter(
      (item): item is PairInput =>
        typeof (item as PairInput)?.ai === "string" &&
        typeof (item as PairInput)?.human === "string" &&
        !!(item as PairInput).ai.trim() &&
        !!(item as PairInput).human.trim(),
    );
    if (valid.length === 0) {
      toast("error", 'None of the entries have both an "ai" and a "human" text.');
      return;
    }

    importing = true;
    try {
      const imported = await importPairs(valid);
      const skipped = parsed.length - imported;
      toast(
        "success",
        `Imported ${imported} of ${parsed.length} pair${parsed.length === 1 ? "" : "s"}` +
          (skipped > 0 ? ` (${skipped} skipped).` : "."),
      );
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      importing = false;
    }
  }

  function doExport() {
    const pairs = library.examples.map(({ ai, human }) => ({ ai, human }));
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(pairs, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "examples.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
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
      {#if library.loading}
        Loading…
      {:else if library.error}
        &nbsp;
      {:else}
        {library.examples.length} training pair{library.examples.length === 1 ? "" : "s"}
        {#if library.examples.length === 1}
          <span class="count-note">— add one more to enable comparison</span>
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
      <button class="btn" onclick={() => fileInput.click()} disabled={importing || library.loading}>
        {#if importing}<span class="spinner spinner-dark"></span>{/if}
        Import JSON
      </button>
      <button
        class="btn"
        onclick={doExport}
        disabled={library.loading || library.examples.length === 0}
        title={library.examples.length === 0 && !library.loading
          ? "No pairs to export yet"
          : undefined}
      >
        Export JSON
      </button>
      <button class="btn btn-primary" onclick={startAdd} disabled={adding || library.loading}>
        Add pair
      </button>
    </div>
  </div>

  {#if !library.loading && !library.error && library.examples.length > 0}
    <div class="histogram-slot">
      <LibraryHistogram examples={library.examples} />
    </div>
  {/if}

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

  {#if library.loading}
    <div class="skeletons" aria-hidden="true">
      {#each [0, 1, 2] as i (i)}
        <div class="card list-skeleton"></div>
      {/each}
    </div>
  {:else if library.error}
    <div class="card panel-note">
      <h3>Couldn't load your examples</h3>
      <p>{library.error.message}</p>
      <button class="btn btn-primary" onclick={loadLibrary}>Try again</button>
    </div>
  {:else if library.examples.length === 0 && !adding}
    <div class="card panel-note">
      <h3>No training pairs yet</h3>
      <p>
        Each pair holds an AI-written version and your own version of the same content. From at
        least two pairs, the detector learns what your voice sounds like.
      </p>
      <div class="empty-actions">
        <button class="btn btn-primary" onclick={startAdd}>Add your first pair</button>
        <button class="btn" onclick={() => fileInput.click()}>Import JSON</button>
      </div>
    </div>
  {:else}
    <ul class="pairs">
      {#each library.examples as ex (ex.id)}
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
                  <span class="tag tag-ai">AI version</span>
                  <p>{ex.ai}</p>
                </div>
                <div class="side">
                  <span class="tag tag-human">Human version</span>
                  <p>{ex.human}</p>
                </div>
              </div>
              <footer>
                <span class="meta" title={ex.created_at}>Added {formatDate(ex.created_at)}</span>
                {#if ex.ai.length > CLAMP_CHARS || ex.human.length > CLAMP_CHARS}
                  <button class="btn btn-ghost small" onclick={() => toggleExpand(ex.id)}>
                    {expanded.has(ex.id) ? "Show less" : "Show full text"}
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
                  <button class="btn btn-ghost small" onclick={() => tryInCompare(ex)}>
                    Try in compare
                  </button>
                  <button class="btn btn-ghost small" onclick={() => startEdit(ex.id)}>Edit</button>
                  <button class="btn btn-ghost small" onclick={() => (confirmDeleteId = ex.id)}>
                    Delete
                  </button>
                {/if}
              </footer>
            </article>
          {/if}
        </li>
      {/each}
    </ul>
    {#if library.examples.length >= 2}
      <p class="next-step">
        Ready to test? <button class="linkish" onclick={onGoCompare}>Compare two texts →</button>
      </p>
    {/if}
  {/if}
</section>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }

  .count {
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

  .histogram-slot {
    margin-bottom: 16px;
  }

  .editor-slot {
    margin-bottom: 16px;
  }

  .skeletons {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .list-skeleton {
    height: 132px;
    background: linear-gradient(
      90deg,
      var(--surface) 25%,
      var(--surface-muted) 50%,
      var(--surface) 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite;
    border-color: var(--border);
    box-shadow: none;
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

  .pairs {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .pair {
    padding: 16px 18px 10px;
  }

  .pair-body {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
  }

  .side {
    min-width: 0;
  }

  .side p {
    margin-top: 6px;
    color: var(--ink);
    white-space: pre-wrap;
    overflow-wrap: break-word;
  }

  .pair-body.collapsed .side p {
    display: -webkit-box;
    -webkit-line-clamp: 5;
    line-clamp: 5;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
  }

  .meta {
    font-size: 12.5px;
    color: var(--ink-faint);
  }

  .spacer {
    flex: 1;
  }

  .confirm-label {
    font-size: 13px;
    color: var(--danger);
    font-weight: 500;
  }

  .next-step {
    margin-top: 20px;
    text-align: center;
    color: var(--ink-secondary);
  }

  .linkish {
    appearance: none;
    border: none;
    background: none;
    padding: 0;
    color: var(--accent);
    font-weight: 500;
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .linkish:hover {
    color: var(--accent-hover);
  }

  @media (max-width: 720px) {
    .pair-body {
      grid-template-columns: 1fr;
      gap: 12px;
    }
  }
</style>
