<script lang="ts">
  /**
   * The "not calibrated yet" panel, shared by every scoring surface. Both
   * Detect and the map have to say the same thing about the same shortfall —
   * the same heading, the same count of pairs still needed, the same way out —
   * so the heading, the shortfall wording and the button live here, and each
   * surface supplies only the sentence that describes what *it* would show.
   *
   * The shortfall is a phrase rather than a number because the copy reads it
   * two ways ("Add one more pair", "Add two pairs"); the sentence receives it
   * so a surface can place it mid-clause.
   */
  import type { Snippet } from "svelte";
  import { library } from "./library.svelte";

  interface Props {
    /** The surface's own sentence, given the shortfall phrase to embed. */
    body: Snippet<[string]>;
    onOpenLibrary: () => void;
  }

  let { body, onOpenLibrary }: Props = $props();

  /** How many pairs are still missing, worded for mid-sentence use. An empty
   *  library needs both; one pair in, only the second. */
  const shortfall = $derived(
    library.examples.length === 1 ? "one more pair" : "two pairs",
  );

  /** The button says what the click does; one pair short, it can be specific. */
  const action = $derived(
    library.examples.length === 1 ? "Add one more pair" : "Open the library",
  );
</script>

<div class="panel-note">
  <h3>Teach it your voice first</h3>
  <p>{@render body(shortfall)}</p>
  <button class="btn btn-primary" onclick={onOpenLibrary}>{action}</button>
</div>
