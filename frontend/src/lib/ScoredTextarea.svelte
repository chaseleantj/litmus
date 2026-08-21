<script module lang="ts">
  import type { SentenceScore } from "./types";

  /**
   * Whether a box is painting a wash: there are sentences, and they still
   * describe the text in the box. Spans are offsets, so offsets into edited
   * text would paint the wrong words — the wash goes the moment the two
   * diverge. Exported because the note under the boxes has to come and go with
   * the wash it explains.
   */
  export function isTinted(
    sentences: SentenceScore[],
    scoredText: string | null,
    value: string,
  ): boolean {
    return sentences.length > 0 && scoredText === value;
  }
</script>

<script lang="ts">
  import { sentenceTint } from "./scale";

  interface Props {
    id: string;
    /** Rendered above the box. Omitted when the box is the only one on screen
     *  and needs no visible name — `ariaLabel` names it instead. */
    label?: string;
    ariaLabel?: string;
    value: string;
    placeholder: string;
    /** The sentence reading, and the exact text it was taken from (isTinted). */
    sentences: SentenceScore[];
    scoredText: string | null;
    oninput: () => void;
    onpaste: (e: ClipboardEvent) => void;
  }

  let {
    id,
    label,
    ariaLabel,
    value = $bindable(),
    placeholder,
    sentences,
    scoredText,
    oninput,
    onpaste,
  }: Props = $props();

  /** Whitespace-separated tokens; empty and blank strings are 0. */
  function wordCount(text: string): number {
    const trimmed = text.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  }

  const words = $derived(wordCount(value) === 1 ? "1 word" : `${wordCount(value)} words`);

  /** The text cut into painted sentences and the plain whitespace between them.
   *  Every character of `value` appears exactly once, in order, so the mirror
   *  wraps its lines where the textarea wraps its own. */
  const parts = $derived.by(() => {
    if (!isTinted(sentences, scoredText, value)) return null;
    const out: { text: string; tint: string | null }[] = [];
    let at = 0;
    for (const s of sentences) {
      if (s.start > at) out.push({ text: value.slice(at, s.start), tint: null });
      out.push({ text: value.slice(s.start, s.end), tint: sentenceTint(s.score) });
      at = s.end;
    }
    if (at < value.length) out.push({ text: value.slice(at), tint: null });
    return out;
  });

  let box = $state<HTMLTextAreaElement>();

  /** The textarea never scrolls itself: it grows to hold everything, and the
   *  .box around it scrolls both it and the wash in one layer — which is what
   *  keeps the wash glued to the glyphs. scrollHeight excludes the border, so
   *  the border's share of the border-box height is added back. */
  function grow() {
    const el = box;
    if (!el) return;
    // Collapsing to 0 for the measurement momentarily shrinks the .box's
    // content, and the browser clamps/re-anchors the box's scroll — which
    // reads as the view snapping around while typing. Pin it across the
    // measurement.
    const scroller = el.parentElement;
    const scrollTop = scroller?.scrollTop ?? 0;
    el.style.height = "0";
    el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
    if (scroller) scroller.scrollTop = scrollTop;
  }

  $effect(() => {
    value;
    grow();
  });

  /**
   * Put the caret in this box and read it from the top. The .box is the
   * scroller, not the textarea (see grow), so plain focus() on a box that was
   * just filled leaves the caret at the end and the view parked down there.
   */
  export function focusFromTop() {
    const el = box;
    if (!el) return;
    el.setSelectionRange(0, 0);
    el.focus();
    const scroller = el.parentElement;
    if (scroller) scroller.scrollTop = 0;
  }

  // A width change (mode toggle, window resize, dragging the box's handle)
  // rewraps the lines, which changes the height the text needs.
  $effect(() => {
    const el = box;
    if (!el) return;
    const observer = new ResizeObserver(grow);
    observer.observe(el);
    return () => observer.disconnect();
  });
</script>

<div class="field">
  <div class="field-head">
    {#if label}<label class="micro-label" for={id}>{label}</label>{/if}
    <span class="micro-label">{words}</span>
  </div>
  <div class="box">
    {#if parts}<div
        class="text-mirror tint"
        aria-hidden="true"
      >{#each parts as part, i (i)}<span style:background={part.tint}>{part.text}</span>{/each}</div>{/if}
    <textarea
      {id}
      {placeholder}
      aria-label={label ? undefined : ariaLabel}
      bind:this={box}
      bind:value
      {oninput}
      {onpaste}
    ></textarea>
  </div>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .field-head {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  .field-head .micro-label:last-child {
    margin-left: auto;
  }

  /* The box owns the paper, the border, and — crucially — the scrolling. The
     textarea grows to hold its whole text and never scrolls itself, so the
     wash behind it lives in the same scroll layer and can never trail the
     glyphs. (A separately-scrolled mirror synced from scroll events lags: the
     textarea scrolls on the compositor thread, the sync runs on the main one.) */
  .box {
    position: relative;
    height: 200px;
    overflow-y: auto;
    resize: vertical;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    transition:
      border-color var(--speed) var(--ease),
      box-shadow var(--speed) var(--ease);
  }

  .box:focus-within {
    border-color: var(--ink-2);
    box-shadow: 0 0 0 3px hsl(var(--ink-hsl) / 0.08);
  }

  .box textarea {
    /* Fill the box when the text is short; grow() takes over past that. */
    min-height: 100%;
    overflow: hidden;
    resize: none;
    /* The visible border, focus ring and resize handle are the box's now; the
       transparent border stays because the wash's metrics include one too. */
    border-color: transparent;
    background: transparent;
    /* Above the wash: the caret, the selection and every pointer event stay
       the textarea's own. */
    position: relative;
    /* A textarea is inline by default, and the few pixels of baseline gap under
       it would leave .box — and the wash behind it — ending below the box
       the user sees. */
    display: block;
  }

  .box textarea:focus {
    border-color: transparent;
    box-shadow: none;
  }

  /* The sentence wash. Metrics come from the shared textarea block in app.css,
     so this stays glyph-aligned with the text it sits behind; its height is its
     own content's, and it rides along when the box scrolls. */
  .tint {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 0;
    color: transparent;
    white-space: pre-wrap;
    overflow-wrap: break-word;
    pointer-events: none;
    user-select: none;
    animation: tint-in var(--speed) var(--ease);
  }

  .tint span {
    border-radius: 2px;
  }

  /* Arrives with a result, so it fades in rather than snapping on. */
  @keyframes tint-in {
    from {
      opacity: 0;
    }
  }
</style>
