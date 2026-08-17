<script lang="ts">
  import { tick } from "svelte";
  import { DownloadSimple, PencilSimple, Plus, Trash, UploadSimple, X } from "phosphor-svelte";
  import {
    addPair,
    deletePair,
    importPairs,
    library,
    loadLibrary,
    MIN_PAIRS,
    updatePair,
  } from "./library.svelte";
  import LibraryHistogram from "./LibraryHistogram.svelte";
  import PairEditor from "./PairEditor.svelte";
  import { toast } from "./toast";
  import type { PairInput } from "./types";

  interface Props {
    open: boolean;
    onClose: () => void;
  }

  let { open, onClose }: Props = $props();

  // The sheet stays mounted while closed, so drafts, scroll position and
  // an in-progress edit survive closing and reopening it.
  let adding = $state(false);
  let editingId = $state<number | null>(null);
  let confirmDeleteId = $state<number | null>(null);
  let saving = $state(false);
  let deletingId = $state<number | null>(null);
  let importing = $state(false);
  let expanded = $state<Set<number>>(new Set());
  let clipped = $state<Set<number>>(new Set());

  let fileInput: HTMLInputElement;
  let sheetEl: HTMLElement | undefined = $state();

  /**
   * "Show more" appears only where the CSS line clamp actually cuts text off,
   * which depends on the rendered width and on hard newlines — measure it
   * rather than guessing from a character count. Only ever measured while
   * collapsed; expanded cards keep the verdict that got them expanded.
   */
  function clampProbe(node: HTMLElement, id: number) {
    // The clamp is on the paragraphs, not on this grid wrapper — the wrapper
    // never overflows, so measuring it would report "never clipped".
    const paragraphs = [...node.querySelectorAll<HTMLElement>(".side p")];
    const measure = () => {
      if (!node.classList.contains("collapsed")) return;
      const isClipped = paragraphs.some((p) => p.scrollHeight > p.clientHeight + 1);
      if (isClipped === clipped.has(id)) return;
      const next = new Set(clipped);
      isClipped ? next.add(id) : next.delete(id);
      clipped = next;
    };
    measure();
    const observer = new ResizeObserver(measure);
    paragraphs.forEach((p) => observer.observe(p));
    return { destroy: () => observer.disconnect() };
  }

  $effect(() => {
    if (open) sheetEl?.focus();
  });

  // Window-level while open: Escape must work even when the focused element
  // was just removed (e.g. right after deleting a pair), and Tab must never
  // escape the dialog.
  $effect(() => {
    if (!open) return;
    const onKeydown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Tab" && sheetEl) {
        const focusables = Array.from(
          sheetEl.querySelectorAll<HTMLElement>(
            'button:not(:disabled), [href], input:not(.sr-only):not(:disabled), textarea:not(:disabled), select, [tabindex]:not([tabindex="-1"])',
          ),
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        if (!(active instanceof HTMLElement) || !sheetEl.contains(active)) {
          e.preventDefault();
          first.focus();
        } else if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  });

  function errMessage(err: unknown): string {
    return err instanceof Error ? err.message : "Something went wrong.";
  }

  /**
   * Each of these swaps out the very control that was clicked, which drops
   * focus to <body> — outside the dialog, so the Tab trap would next send the
   * user to the Close button rather than to what they just opened.
   */
  async function focusAfterSwap(selector: string) {
    await tick();
    sheetEl?.querySelector<HTMLElement>(selector)?.focus();
  }

  function startAdd() {
    adding = true;
    editingId = null;
    confirmDeleteId = null;
    focusAfterSwap(".editor-slot textarea");
  }

  function startEdit(id: number) {
    editingId = id;
    adding = false;
    confirmDeleteId = null;
    focusAfterSwap(`#pair-${id} textarea`);
  }

  function startDelete(id: number) {
    confirmDeleteId = id;
    focusAfterSwap(`#pair-${id} .confirm-delete`);
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

    // The server rejects the whole request on one malformed entry, so filter
    // here and report exactly what was skipped and why.
    const valid = parsed.filter(
      (item): item is PairInput =>
        typeof (item as PairInput)?.ai === "string" &&
        typeof (item as PairInput)?.human === "string" &&
        !!(item as PairInput).ai.trim() &&
        !!(item as PairInput).human.trim(),
    );
    const invalid = parsed.length - valid.length;
    if (valid.length === 0) {
      toast("error", 'None of the entries have both an "ai" and a "human" text.');
      return;
    }

    importing = true;
    try {
      const imported = await importPairs(valid);
      const duplicates = valid.length - imported;
      const skipped = [
        duplicates > 0 ? `${duplicates} duplicate${duplicates === 1 ? "" : "s"}` : null,
        invalid > 0 ? `${invalid} invalid entr${invalid === 1 ? "y" : "ies"}` : null,
      ].filter(Boolean);
      toast(
        "success",
        `Imported ${imported} of ${parsed.length} pair${parsed.length === 1 ? "" : "s"}` +
          (skipped.length > 0 ? ` (${skipped.join(", ")} skipped).` : "."),
      );
    } catch (err) {
      toast("error", errMessage(err));
    } finally {
      importing = false;
    }
  }

  /** The same shape the import accepts, built from the list already on screen. */
  function doExport() {
    const pairs = library.examples.map(({ ai, human }) => ({ ai, human }));
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(pairs, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "examples.json";
    // Firefox and Safari need the anchor in the document, and revoking in the
    // same tick can cancel the download before it starts.
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

  const count = $derived(library.examples.length);
  const countText = $derived.by(() => {
    if (library.loading) return "Loading…";
    if (library.error) return "";
    if (count === 1) return "1 pair — one more unlocks scoring";
    return `${count} pairs`;
  });
</script>

<div class="overlay" class:open inert={!open}>
  <div class="backdrop" onclick={onClose} aria-hidden="true"></div>
  <div
    class="sheet"
    role="dialog"
    aria-modal="true"
    aria-label="Training library"
    tabindex="-1"
    bind:this={sheetEl}
  >
    <header class="sheet-head">
      <div class="sheet-title">
        <h2 class="serif">Training library</h2>
        <p class="sheet-sub">
          Each pair is the same content. The left one is the text written by an AI, and the right one is your version. Together they define what "sounds like you" means.
        </p>
      </div>
      <button
        class="icon-btn close"
        aria-label="Close the library (Esc)"
        title="Close (Esc)"
        onclick={onClose}
      >
        <X size={15} />
      </button>
    </header>

    <div class="sheet-body">
      <div class="toolbar">
        <p class="count" aria-live="polite">{countText}</p>
        <div class="toolbar-actions">
          <input
            bind:this={fileInput}
            type="file"
            accept=".json,application/json"
            class="sr-only"
            tabindex="-1"
            onchange={onFilePicked}
          />
          <button
            class="btn"
            onclick={() => fileInput.click()}
            disabled={importing || library.loading}
          >
            {#if importing}<span class="spinner spinner-dark"></span>{:else}<UploadSimple size={15} />{/if}
            Import
          </button>
          <button
            class="btn"
            onclick={doExport}
            disabled={library.loading || count === 0}
            title={count === 0 && !library.loading ? "No pairs to export yet" : undefined}
          >
            <DownloadSimple size={15} />
            Export
          </button>
          <button
            class="btn btn-primary"
            onclick={startAdd}
            disabled={adding || library.loading}
            title={adding ? "The editor below is already open" : undefined}
          >
            <Plus size={15} weight="bold" />
            Add pair
          </button>
        </div>
      </div>

      {#if !library.loading && !library.error && count > 0}
        <LibraryHistogram examples={library.examples} />
      {/if}

      <!-- Above the editor as well as the list, so it labels both columns
           wherever they appear. -->
      {#if !library.loading && !library.error && (count > 0 || adding)}
        <div class="list-head" aria-hidden="true">
          <span class="micro-label dot-marker ai">AI version</span>
          <span class="micro-label dot-marker human">Your version</span>
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
            <div class="card skeleton"></div>
          {/each}
        </div>
      {:else if library.error}
        <div class="card panel-note">
          <h3>Couldn’t load your examples</h3>
          <p>{library.error}</p>
          <button class="btn btn-primary" onclick={loadLibrary}>Try again</button>
        </div>
      {:else if count === 0 && !adding}
        <div class="card panel-note">
          <h3>No training pairs yet</h3>
          <p>
            Take something an AI wrote for you, and the version you would actually send. From
            {MIN_PAIRS} pairs up, Litmus learns what your voice sounds like.
          </p>
          <div class="panel-actions">
            <button class="btn btn-primary" onclick={startAdd}>Add your first pair</button>
            <button class="btn" onclick={() => fileInput.click()}>Import JSON</button>
          </div>
        </div>
      {:else}
        <ul class="pairs">
          {#each library.examples as ex (ex.id)}
            <li id="pair-{ex.id}">
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
                  <div
                    class="pair-body"
                    class:collapsed={!expanded.has(ex.id)}
                    use:clampProbe={ex.id}
                  >
                    <div class="side">
                      <span class="micro-label dot-marker ai stacked-only side-label">AI version</span>
                      <p>{ex.ai}</p>
                    </div>
                    <div class="side">
                      <span class="micro-label dot-marker human stacked-only side-label">Your version</span>
                      <p>{ex.human}</p>
                    </div>
                  </div>
                  <footer>
                    <span class="meta" title={ex.created_at}>{formatDate(ex.created_at)}</span>
                    {#if clipped.has(ex.id)}
                      <button class="show-more" onclick={() => toggleExpand(ex.id)}>
                        {expanded.has(ex.id) ? "Show less" : "Show more"}
                      </button>
                    {/if}
                    <span class="spacer"></span>
                    {#if confirmDeleteId === ex.id}
                      <span class="confirm-label">Delete this pair?</span>
                      <button
                        class="btn btn-danger small confirm-delete"
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
                          onclick={() => startDelete(ex.id)}
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
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 48px 24px;
    visibility: hidden;
    transition: visibility 0s 200ms;
  }

  .overlay.open {
    visibility: visible;
    transition: visibility 0s;
  }

  .backdrop {
    position: absolute;
    inset: 0;
    background: hsl(var(--ink-hsl) / 0.4);
    opacity: 0;
    transition: opacity 200ms var(--ease);
  }

  .overlay.open .backdrop {
    opacity: 1;
  }

  .sheet {
    position: relative;
    display: flex;
    flex-direction: column;
    width: min(880px, 100%);
    max-height: min(760px, 100%);
    background: var(--paper);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow-sheet);
    opacity: 0;
    transform: translateY(10px);
    transition:
      opacity 200ms var(--ease),
      transform 200ms var(--ease);
  }

  .overlay.open .sheet {
    opacity: 1;
    transform: translateY(0);
  }

  .sheet:focus-visible {
    outline: none;
  }

  .sheet-head {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 22px 24px 16px;
    border-bottom: 1px solid var(--border);
  }

  .sheet-title {
    min-width: 0;
  }

  .sheet-head h2 {
    font-size: var(--text-title);
    letter-spacing: -0.01em;
  }

  .sheet-sub {
    margin-top: 4px;
    font-size: var(--text-body);
    line-height: 1.5;
    color: var(--ink-secondary);
    max-width: 56ch;
  }

  .close {
    margin-left: auto;
    flex-shrink: 0;
  }

  .sheet-body {
    overflow-y: auto;
    padding: 18px 24px 24px;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }

  .count {
    font-size: var(--text-body);
    color: var(--ink-secondary);
    font-weight: 500;
  }

  .toolbar-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
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

  /* The show/hide rule lives with .dot-marker in app.css; only the spacing
     below a stacked label belongs to this list. */
  .side-label {
    margin-bottom: 7px;
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
    font-size: var(--text-body);
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
    font-size: var(--text-body);
    color: var(--ink-faint);
  }

  .show-more {
    appearance: none;
    border: none;
    background: none;
    padding: 0;
    font-size: var(--text-body);
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
    font-size: var(--text-body);
    color: var(--danger);
    font-weight: 500;
  }

  @media (max-width: 720px) {
    .overlay {
      padding: 0;
    }

    .sheet {
      width: 100%;
      max-height: 100%;
      border-radius: 0;
      border: none;
    }

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
  }
</style>
