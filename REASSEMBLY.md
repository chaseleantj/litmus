# Legacy style reassembly

This branch (`legacy-style`) reconstructs the app's **pre-polish visual design** on top of the
**current feature set**. It exists as the "before" half of a real before/after design example:
every design element here was genuinely shipped at some point in this repo's history and later
deliberately removed or refined on `main`. Nothing is invented — when a design existed in several
versions, the oldest one that still fits the current features was used, and each element below
cites the commit it was restored from.

**Design only.** The backend, the data layer (`api.ts`, `library.svelte.ts`,
`compareState.svelte.ts`, `errors.ts`, `scale.ts`), and all current features (single/pair
scoring, calibration gate, Ctrl+Enter scoring, keyboard shortcuts, the Visualization view, the
library histogram, import/export) are unchanged from `main`. Two feature-era designs could not be
restored because they need backend endpoints that no longer exist: the per-sentence heatmap
(removed in `5c7137c`) and the old UMAP layout parameters (`550f5ec` changed `scoring.py`).

Run it: `npm run dev --prefix frontend` (port of your choosing), same backend as `main`.
Screenshots of this build: `docs/screenshots-legacy/`. The polished "after" screenshots live on
`main` in `docs/screenshots/`.

## Provenance

| File | Source |
| --- | --- |
| `frontend/src/app.css` | `745fda9` verbatim (tokens, buttons, tags, cards, panels) + a marked compat section for the kept feature components |
| `frontend/src/App.svelte` | `745fda9` structure and styles, with a third tab for the newer Visualization view |
| `frontend/src/lib/DetectView.svelte` | current logic; presentation fused from `745fda9` (CompareView) and `774fad4^` (pre-library-sheet DetectView) |
| `frontend/src/lib/ExamplesView.svelte` | `745fda9` markup/styles wired to the current library store |
| `frontend/src/lib/PairEditor.svelte` | `745fda9` verbatim |
| `frontend/src/lib/LibraryHistogram.svelte`, `histogram.ts` | `0b99987` verbatim (the histogram's first version) |
| `frontend/src/main.ts`, `frontend/index.html` title | `745fda9` (system fonts, original name) |
| `MapView`, `Toasts`, `ErrorPanel`, state/data modules | unchanged from `main`; restyled only through the legacy tokens |

## What this "before" build shows (each later removed/refined on main)

### Identity & layout
- App named **"Write like me"** with an `<h1>` masthead + always-visible tagline (`745fda9`);
  main later renamed it Litmus with a small italic serif wordmark.
- **Three-tab underline navigation** ("Training examples" first and default); main later deleted
  the tabs, made Detect the single page, and moved examples into a modal library sheet behind one
  "Calibrate" button (`774fad4`).
- **1060px fixed shell**; main later narrowed to a 700px reading column, vertically centered.
- **System font stack, one ad-hoc size ramp, blue accent (`#1f5f8b`) on primary buttons and
  active tabs, card drop shadows**; main later moved to Manrope+Fraunces, a 5-step type scale,
  ink-black buttons, flat borders, and exactly two semantic hues.
- **Full-width amber "Backend unreachable" banner** (`745fda9`); main shrank it to an inline pill.

### Detect / Compare
- **Intro lede paragraph** above the fields and **"Try an example" as a prominent top button**
  (`745fda9`); main deleted the lede and demoted the button to a small ghost control.
- **Field labels with role annotations** — "First text *(stays put)* / Second text *(moves)*"
  (`745fda9`).
- **Word counters under each textarea** (`745fda9`); dropped on main in `fe05f82`.
- **Always-visible hint row** with "Swap texts" / "Compare two texts" ghost buttons on the right
  (`745fda9` layout; mode affordances from `774fad4^`: X icon closes the second field). Main
  replaced these with one segmented control.
- **Result in a shadowed card** (`745fda9`); main stripped the card to a bare top border.
- **Pair chart: 46px zone-block gradient with flag-on-stick markers and the three-part legend**
  ("← sounds more like AI than the first / anything in the middle is hard to tell apart / sounds
  more human than the first →") (`745fda9`); main replaced it with the 12px litmus strip, dot
  pins, and two pole words.
- **Single-text chart: 1px baseline with dot pin and "MORE LIKE AI / MORE HUMAN" axis captions**
  (`774fad4^`); also replaced by the litmus strip on main.
- **Mono scores line** "first −0.097 · second 0.110 · gap +0.208" (`745fda9`); main moved values
  onto the pins.
- **Verbose save flow**: "Saves the second text as the human version · switch" + "Add as training
  pair" (`745fda9`); main compacted it to a "Human version: [First|Second]" segment + "Save as
  pair".
- Old copy throughout: "You **have pasted** the same text twice.", "Add training examples",
  "Saved to training examples."

### Training examples (library)
- **Full tab page** instead of a modal sheet (`745fda9`).
- **"AI version" / "Human version" tinted pill tags repeated on every row** (`745fda9`); main
  flattened them to one dot-marker header row.
- **"Added {date}" footers**, "**Import JSON**/**Export JSON**" button labels, "N training
  pair(s)" count, "— add one more to enable comparison" note (`745fda9`).
- **Always-visible per-row text buttons**: "Try in compare", "Edit", "Delete" (`745fda9`); main
  removed "Try in detect" entirely (`6a772ac`) and hid Edit/Delete behind hover-revealed icons.
- **"Show full text" ghost button** on a 420-character heuristic (`745fda9`); main switched to a
  measured "Show more" underline link.
- **"Ready to test? Compare two texts →" footer link** (`745fda9`).
- **Histogram in its first form** (`0b99987`): y-axis gridlines and tick numbers, an
  always-visible caption line under the plot, empty days drawing nothing; main later removed the
  gridlines, moved the count into a tooltip, and added faint full-height tracks
  (`a3cdaf3`, `1ffec1a`).

### Visualization
- Kept from main (it never existed in the legacy era) but rendered through the legacy tokens:
  blue/orange palette, blue-tinted segmented control, shadowed card.
