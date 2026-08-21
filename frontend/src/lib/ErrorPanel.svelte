<script lang="ts">
  import type { ErrorState } from "./errors";

  interface Props {
    /** What failed, in the surface's own words ("Couldn't draw the map"). */
    heading: string;
    error: ErrorState;
    /** 409 means the library is the problem, so the way out is the library. */
    onOpenLibrary: () => void;
    onRetry: () => void;
  }

  let { heading, error, onOpenLibrary, onRetry }: Props = $props();
</script>

<div class="panel-note" role="alert">
  <h3>{heading}</h3>
  <p class="error-text">{error.message}</p>
  {#if error.status === 409}
    <button class="btn btn-primary" onclick={onOpenLibrary}>Add training pairs</button>
  {:else}
    <button class="btn" onclick={onRetry}>Try again</button>
  {/if}
</div>
