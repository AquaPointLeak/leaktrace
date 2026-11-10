# LeakTrace front-end redesign: audit and brief

Audit date: 2026-11-09. Based on the source of all four pages plus screenshots of
the landing page (first two screens), both login screens, the desktop builder
(job list and editor at 1024px) and the mobile builder (list and editor at
375px). The signed-in portal and the lower half of the landing page were not
reviewed.

## Status (2026-11-09)

**Decision:** the whole product uses the landing page look (navy, signal teal,
Bricolage Grotesque, cool grey-blue surface).

**Done, uncommitted, in the repo-root files:** the portal and both builders now use
the landing page's palette and fonts through one shared token block (colours, type
scale `--fs-*`, radii `--r-*`). Off-token colours and the old token names are gone.
Components were restyled to match: buttons, cards, pills, section labels, logo mark,
top bars and focus rings. Markup, ids, layout and behaviour are unchanged. The
builder sync check passes, with the new layout-only differences accepted in
`baseline.json`.

**Not done (needs your call):** the layout fixes in section 2, the customer PDF,
dark mode, a logo in the portal top bar, and `index.html` (left as is, it already
defines the target look). The header colour default conflict (`#0B2947` vs `#004179`)
is also still there.

## 1. Where the code lives

| Page | Role | Lines |
|---|---|---|
| `index.html` | Marketing landing page | 472 |
| `aquapoint-portal.html` | Customer portal (magic-link sign-in) | 628 |
| `leak-report-builder-desktop.html` | Staff report builder, sidebar layout | 2,858 |
| `leak-report-builder-mobile.html` | Staff report builder, single column | 2,777 |

- **The originals are in the repo root** (`/Users/juju_mclovin/Desktop/LeakTrace/`).
  `Leak Trace Testers/site/` is a generated, gitignored copy with Supabase swapped
  for the mock. Edit the originals, then run `python3 harness/build_site.py` to
  preview.
- Each page is one file with CSS in a single `<style>` block and no build step.
- Desktop and mobile builders must be edited together. The `report-sync` skill
  covers this and `sync_check.py` verifies it.
- There is no dark mode (no `prefers-color-scheme` rules in any page).

## 2. Findings

### The marketing site and the app look like two different products

| | `index.html` | Portal and builders |
|---|---|---|
| Display font | Bricolage Grotesque | Space Grotesk |
| Accent | `#3FD0C9` (signal) | `#1DBFAE` (aqua) |
| Dark base | `#0B2947` navy, `#061726` abyss | `#12313A` ink |
| Page background | `#F5F8FA` cool grey-blue | `#F6F3EC` warm cream |
| Token names | `--abyss --navy --signal --surface` | `--ink --aqua --paper` |

A visitor who signs up from the landing page lands in an app with a different
typeface, a different teal and a warmer background.

### Token and scale state

- **Good:** the portal and both builders share an identical 17-token `:root`
  block (the three copies hash the same). Colours are mostly tokenised.
- Off-token colours remain: `#fff` (18 uses in the desktop builder), `#efebdf`,
  `#106e63` (3), and the status-pill colours (`#f1e6d2/#8a6416`,
  `#dce7f5/#2a5b94`, `#fbebcf`) plus `#9fc2c0`.
- The token block is copy-pasted into three files, so any palette change is three
  edits that can drift.
- **No type scale:** 16 to 18 distinct `font-size` values per page, in half-pixel
  steps from 9.5px to 14px. **No radius scale:** 4, 6, 7, 8, 9, 10, 20px and 50%.
- 38 to 42 inline `style=` attributes in each builder bypass the stylesheet.
- Responsive coverage is thin: 3 `@media` blocks (desktop builder), 2 (mobile),
  4 (landing), 0 (portal).

### Header colour defaults conflict

The business profile default is `#0B2947` (the landing navy), but the code falls
back to `#004179` in `headerRgb()` and in the Business Settings colour inputs
(desktop lines 403 and 2576 to 2577). A business that never sets a colour can see
one value in settings and another on the PDF.

### Screen-level issues seen

**Desktop builder**
- The login screen shows an empty 320px dark sidebar beside the form. It looks
  broken.
- The sidebar stacks five equal full-width outline buttons (Business Settings,
  Sign out, Preset Sections, Catalogue, Restore Backup) above the search and the
  report list. "Sign out" sits in the middle. The list starts low on a 768px-tall
  screen.
- At 1024px the sidebar takes about 31% of the width.
- Editor field rows show a boxed, editable label, a very narrow value input, and
  up/down/remove controls on every row. Value inputs are about 60 to 70px wide.
- The sticky action bar puts Delete Report, Download Backup, Save, Email PDF and
  Export PDF in one row. Delete has the same weight as Save and sits next to it.
- The envelope emoji on "Email PDF" is the only emoji in an otherwise text-only UI.

**Mobile builder**
- Six header buttons wrap onto three rows and use about 250px of an 812px screen
  before any content. The primary action, "+ New Report", is last.
- Every report card has a Delete button beside the status pill, which is a large
  tap target for a destructive action on a one-handed list.
- In the editor the label box and value input sit side by side, leaving the value
  about 130px wide. "Facility address" wraps one word per line.
- The fixed bottom bar uses about 110px (two rows, five buttons, Delete next to
  Save). The back link appears twice ("All Reports" button in the header and an
  in-page link).
- Card meta lines are monospace, wrap awkwardly and leave a dangling "·" when
  there is no date.

**Portal**
- The top bar has no logo, only text ("Your inspection reports / CLIENT PORTAL").
- Sign-in page is clean but sparse. No media queries. The signed-in views need
  their own review.

**Landing page**
- Strongest of the four: clear hero, scannable cards, consistent tokens and
  `clamp()` type. Needs alignment with the app more than a redesign.

## 3. Constraints and risks

1. **PDF output is separate from the CSS.** It is drawn with jsPDF (Helvetica,
   RGB literals such as `18,49,58` and `27,31,30`). A restyle will not change it,
   and a palette change will not reach it. Decide whether the PDF should follow
   the new look. If so it is its own piece of work, because customers receive it.
2. **Keep ids, labels and DOM structure stable where possible.** The QA harness
   and 34+ logged bugs were found against the current UI. Check
   `harness/QA-BRIEF.md` before renaming controls.
3. **Layout changes are behaviour changes.** Moving Delete behind a menu or
   restructuring the field rows changes how people work. These need your sign-off.
4. **Two files, one change.** Every builder edit is made twice and checked with
   `sync_check.py`.

## 4. Decisions needed from you

1. **Which look wins?** (a) Adopt the landing page's navy, signal and Bricolage
   across everything, (b) keep the app's ink, aqua and cream and bring the
   landing page to it, or (c) a new direction from a reference you give me.
2. **How far to go?** Visual restyle only (colours, type, spacing, components), or
   also layout changes to the sidebar, field rows and action bars listed above.
3. **PDF:** leave as is, or restyle to match.
4. **Dark mode:** wanted or not.
5. **Logo:** the app header uses a CSS "ripple" mark and the landing page uses an
   SVG. Do you have a final logo file?

## 5. Proposed approach

1. **Direction.** You choose from section 4 and share any logo, colours, fonts or
   reference sites.
2. **Tokens, no visual change.** One shared token set (colour roles, type scale,
   radii, spacing, shadow) in all four pages. Replace off-token colours and
   inline styles. Verify with before/after screenshots.
3. **Components.** Buttons (primary, secondary, quiet, destructive), inputs, pills,
   cards, sticky action bar and the empty and loading states.
4. **Screens.** Mobile header and list, editor field rows, desktop sidebar and
   login, then portal and landing page.
5. **Check.** Rebuild the QA copy, review at 375, 768 and 1280px, run
   `sync_check.py`, and walk the main flows (sign in, create, edit, export PDF).

## 6. Inputs that help most

- Logo file(s) and brand colours or fonts if they exist
- Two or three sites or apps you like, and anything you dislike
- Who uses each page and where (technician in a driveway on a phone, office staff
  at a desk, customer on any device)
- Whether this is for existing customers or a launch, which affects how much the
  UI can change
