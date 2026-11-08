---
name: report-sync
description: Keep leak-report-builder-desktop.html and leak-report-builder-mobile.html in step. Use whenever either report builder is edited (features, bug fixes, PDF output, storage, Supabase, presets, styles), when the user says "sync the builders", "mirror this to mobile/desktop", or asks whether the two versions have drifted. Run the check after every edit to either file.
---

# Report builder sync

LeakTrace ships the field report builder twice: `leak-report-builder-desktop.html`
and `leak-report-builder-mobile.html` (project root). Each one is a single file
holding its CSS, markup and app script. **About 95% of the code is the same in
both.** Only the page shell differs:

| | Desktop | Mobile |
|---|---|---|
| Shell | `#shell` → `#sidebar` + `#mainPanel` | `#topbar` + `#app` |
| Report list | `renderSidebar()` (always visible) | `renderList()` (its own view) |
| Navigation | `closeMain()`, `renderMainEmpty()` | `goList()`, `renderTopbar()`, back links |
| Screen headers | `.editor-header` + ✕ Close button | `.back-link` + `.list-header` |
| Grids | `.items-grid`, `.job-fields-grid` | single column, `@media(max-width:520px)` |
| `MAIN_EL` | `'mainPanel'` | `'app'` |

Everything else must stay the same in both files: storage, Supabase, auth, state,
job fields, categories, items, photos, video, presets, catalogue logic, PDF
generation, backups and the theme tokens.

## When you change either builder

1. **Make the change in both files in the same turn.** Don't leave one for later.
   - For shared logic, apply the identical edit to both files. Line numbers differ
     (mobile runs about 15–75 lines earlier), so locate the code by function name.
   - For a layout function (listed in the table above), write the version that
     fits that layout, e.g. a sidebar button on desktop becomes a topbar button
     on mobile (`renderTopbar`). New buttons and actions need to appear in both
     navigations.
   - If you rename or remove a function, check that the other file's layout code
     doesn't still call it (desktop calls `renderSidebar()` from shared code such
     as `saveCurrentReport`).
2. **Run the check:**
   ```bash
   python3 .claude/skills/report-sync/sync_check.py
   ```
   Run it from the LeakTrace folder. It compares the files function by function
   against `baseline.json`, which holds the accepted layout differences.
   - `In sync` (exit 0) means you're done.
   - `NEW DIFFERENCES` lists each chunk that differs in a new way. Look at one with
     `--show NAME` (for example `--show renderEditor` or `--show "<style>"`).
     Then fix the drift, or, if the difference really belongs to the layout,
     go to step 3.
   - `NOW IDENTICAL` means a former layout difference was merged. Accept it.
3. **Accept only intentional layout differences:**
   ```bash
   python3 .claude/skills/report-sync/sync_check.py --accept
   ```
   Run `--accept` only after you've read every NEW entry and confirmed it's
   layout-only. Tell the user which chunks you accepted and why. Never accept a
   difference just to make the check pass.

## Auditing for existing drift

If the user asks whether the builders have drifted, run the check with `--all`.
Then use `--show` on each NEW item and summarize: which side has the newer
behavior, and what you'd copy across. Ask before syncing anything where it isn't
clear which version is correct.

## Notes

- The checker skips blank lines and trailing whitespace. Comments and code order
  still count, so a moved line shows up as a difference.
- Chunks: `<head>`, `<style>`, `<markup>` (body HTML outside the script), one
  chunk per top-level `function` / `const` / `let`, plus `<script-preamble>`.
- `aquapoint-portal.html` and `index.html` are separate pages and aren't covered
  by this skill.
