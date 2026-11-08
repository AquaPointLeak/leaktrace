# LeakTrace QA run: shared brief (all agents read this first)

## What is being tested
LeakTrace is a pool-leak inspection app. The originals live in `/Users/juju_mclovin/Desktop/LeakTrace/`:
- `index.html`: landing page. Links to the mobile builder, the desktop builder and the portal.
- `aquapoint-portal.html`: read-only portal for customers. Sign-in is by magic link only.
- `leak-report-builder-desktop.html` and `leak-report-builder-mobile.html`: the staff app.
  - About 95% of the code is shared between them; only the page shell differs (see `.claude/skills/report-sync/SKILL.md`).
  - Features: sign-up and sign-in, business settings, reports, presets ("Preset Sections"), the public preset catalogue, PDF export, and JSON backup and restore.

**You test copies, never the live app.** The harness serves copies at `http://<name>.localhost:8787/site/<page>`, with Supabase replaced by a local mock. The live Supabase project is never contacted. Never open or call `supabase.co`.

**What the mock does:**
- Email confirmation is ON. Sign-up sends a "Confirm your signup" mail to the mock mailbox.
  - To read it: `python3 harness/board.py mail <email>`, or `fetch('/mock/mailbox?to=<email>')` in the page.
  - To open a link: navigate to it, then **reload the tab**. A hash-only change does not reload the page; a real email click would.
- Magic links (portal) and password-reset links work the same way.
- Row rules are approximations of the real ones:
  - a user sees their own rows;
  - a portal customer sees reports with `shared_with_client=true` and `client_email` equal to their email;
  - the catalogue shows approved entries, the user's own entries, and everything for an admin.
- `admin@leaktrace.test` is the catalogue admin.

If a behaviour looks like it comes from the mock rather than the app (for example a mock error format), still file it, but set `--area harness` and say so. The coordinator will separate it out.

**Test logins:** `harness/test-accounts.json`.
- Only use accounts whose `owner` is you.
- Never paste passwords into reports, logs or your final message.

## Working directory
`/Users/juju_mclovin/Desktop/LeakTrace/Leak Trace Testers`. Run every `harness/...` command from here.

## The board (live dashboard at http://board.localhost:8787/)
Use `python3 harness/board.py ...` (see `--help`). Never edit board JSON by hand.

**Agent status.** Update your status at every step change so the user can follow along:
```
python3 harness/board.py status <you> --step "Building report 2 of 3 on desktop" [--done 3] [--log "..."] [--state working|waiting|blocked|done]
```
Keep steps short and human-readable. Log notable findings in one line each.

**Bugs.** One bug per real issue, reproduced at least twice:
```
python3 harness/board.py bug new --reporter <you> --title "..." --page leak-report-builder-desktop.html \
  --viewport desktop|mobile|both --severity critical|high|medium|low --area auth|reports|presets|pdf|catalogue|portal|nav|ui|harness|other \
  --steps "1. ... 2. ..." --expected "..." --actual "..." --fix "what you'd like changed"
```
Severity guide:
- **critical**: data loss, a security or privacy leak, or the app is unusable.
- **high**: a core flow is broken.
- **medium**: wrong output or a confusing failure.
- **low**: cosmetic or polish.

**Before filing**, run `python3 harness/board.py bug list` and don't file a duplicate. If you find the same issue on the other viewport, add a note to the existing bug instead:
```
bug update BUG-00X --note "also on mobile" --by <you>
```

## Browser rules (testers)
- Use the built-in browser tools (`mcp__Claude_Browser__*`).
- **Use your own tab.** Create it with `tabs_create` and pass `tabId` on every call. Never touch other tabs; the user's dashboard is in one of them.
- **Use your own origin**, so sessions don't collide:
  - Tester A: `a.localhost`
  - Tester B: `b.localhost`, plus `portal.localhost` for customers
- **Mobile:** `resize_window {preset:"mobile", tabId}` gives 375×812 with a mobile user agent.
  - The emulation can be cleared between turns. Before each mobile step, re-apply it and check that `window.innerWidth === 375` with `javascript_tool`.
  - Reset it with `preset:"desktop"` when you're done.
- **Desktop:** default pane size. Record the real `innerWidth` in your log.
- **Drive the UI like a user:** use `find` or `read_page` refs and `computer` clicks and typing, and take screenshots to look for layout problems. Use `javascript_tool` only for:
  - **Native dialogs.** Before an action that calls `confirm()` or `prompt()`, stub them, e.g. `window.confirm=()=>true; window.prompt=()=>'My preset'`.
  - **File pickers.** The pane has no file upload. Build a `File` from a canvas, e.g.
    `const c=document.createElement('canvas');c.width=800;c.height=600;const g=c.getContext('2d');g.fillStyle='#3a8';g.fillRect(0,0,800,600);g.fillStyle='#fff';g.font='48px sans-serif';g.fillText('Leak photo 1',40,300);const b=await new Promise(r=>c.toBlob(r,'image/jpeg',.85));const f=new File([b],'leak1.jpg',{type:'image/jpeg'});`
    Then call the handler the picker would call:
    - `handleItemPhotoFiles(catId,itemId,[f])`
    - `handlePhotoFiles(catId,[f])`
    - `handleLogoFile([f])`
    - `handleItemVideoFiles(...)` or `handleCatVideoFiles(...)` for video; a short canvas `MediaRecorder` webm is fine.
    - `restoreReportBackup([file])` for restore.

    Read the ids from the `onchange` attribute of the matching `<input type=file>`.
  - **Downloads.** Don't let files download into the user's Downloads folder.
    - Before clicking Export PDF or Download Backup, wrap the save step:
      - `window.savePDF=(doc,name)=>{window.__lastPdf={name,pages:doc.getNumberOfPages(),bytes:doc.output('arraybuffer').byteLength}}`
      - for backups, temporarily override `URL.createObjectURL` or `HTMLAnchorElement.prototype.click` to capture the blob.
    - Then inspect what was captured.
    - To look at a PDF, open `doc.output('bloburl')` in your own tab.
  - **Reading state** to confirm what you saw (`state.current`, `state.templates`, `/api/state` counts).
- **Never** change files outside `Leak Trace Testers/board` through the board CLI. Never edit the app files.

## Fake data
Make it realistic and varied:
- **Pool-service customers**, e.g. "Marisol Vega, 4412 Juniper Hollow Dr, Scottsdale AZ 85255"; residential and commercial, spa or no spa.
- **Customer emails:** use `customer1@leaktrace.test` / `customer2@leaktrace.test` where the portal is tested, otherwise `@example.test`.
- **Job info:** made-up job numbers, dates and technician names.
- **Findings:** a mix of Pass, Attention, Fail and N/A, with notes such as "Dye test showed draw at main drain cover", "Skimmer throat crack, 2in", "Static test held 30 min on return line 2".
- **Edge cases:** long names, apostrophes, `<b>html</b>`, emoji, blank optional fields, a very long note.

---

## Run 2 addendum (read this too)

**State of the app now.** BUG-001 to BUG-014 are fixed and verified, so run `bug list` before filing anything. Things you should expect and not report:
- The landing page offers the **first month free**: nav button "First month free", hero and pricing buttons "Start your first month free", closing banner "Your first month is free".
- Those sign-up buttons open the builder on the **create-account** form (the link carries `#signup`). The "Sign in" link opens the sign-in form.
- There is **no billing, trial or card collection anywhere** in the app, and the hero says "No card required". Report that once, as a go-live finding (below), not on every page.

**This run has two jobs:** find defects, and judge whether the site is ready to go live and be sold.

### Go-live readiness (both testers; start these titles with `[GO-LIVE]`)
Walk the whole first-customer journey as a stranger would: land → sign up → confirm email → set up the letterhead → first report with photos → PDF → share with a customer → the customer opens the portal. Then check:
1. **Copy and pricing:** the offer wording, prices and plan names agree everywhere; no placeholder or lorem text; no dead buttons or anchors (for example, does "Get in touch" lead anywhere you can actually contact someone?).
2. **Trust and legal:** Terms of service, Privacy policy, a support contact and a company name or address can be found from the landing page, sign-up and portal.
3. **Sign-up and recovery:** every error message is plain English and says what to do (wrong password, duplicate email, expired or reused confirm, magic and reset links, weak password). Nothing dead-ends.
4. **Data safety:** photos, video and notes survive save, reload, backup and restore. Deleting asks first. Nothing leaks between accounts or between customers.
5. **Output quality:** the PDF looks like something you would hand a paying customer (fonts, logo, long text, many photos, odd characters).
6. **Mobile and desktop:** tap targets, sideways scrolling, the keyboard covering fields, cut-off buttons, readable text.
7. **Page basics:** tab titles, favicon, share/meta tags, 404 behaviour, accessibility basics (labels, contrast, keyboard focus).

Severity for `[GO-LIVE]` items: **critical** = you could not sell it, or you would be exposed (data loss, privacy leak, cannot sign up). **high** = would embarrass you or lose a customer at launch. **medium / low** = polish. Gaps only the owner can fill (billing, legal text, a support address) are still reported, once each, with `--area other`.

### Coordinator rules for this run
- **Nothing in the original files changes until the user approves.** Prepare each fix as `board/fixes/FIX-NNN.diff`, a unified diff against the originals in `/Users/juju_mclovin/Desktop/LeakTrace`, and make sure it passes `git apply --check`. Try it on a scratch clone first: copy `harness/` and `site/` into `board/fixes/work/FIX-NNN/`, apply the patch there, run `PORT=879N python3 harness/server.py` from the clone and test on `http://x.localhost:879N/site/...`, then stop that scratch server.
- Both builders get edited together. Follow `.claude/skills/report-sync/SKILL.md` and run `python3 .claude/skills/report-sync/sync_check.py` from the LeakTrace folder.
- Bugs that need an owner decision or content only the owner has (billing, legal text, support contact): set status `triaged` with `--set needs_owner=true` and `--set owner_question="..."`. They go in the readiness verdict, not the fix queue.
- **Approval:** set `awaiting-approval` and end your turn with an APPROVAL PACKET. The user's answer arrives as a message. After a yes: apply the patch, run `sync_check.py`, run `python3 harness/build_site.py`, set `fixed`, and commit locally (one commit per fix, message `Fix BUG-NNN: <title>`, with a `Co-Authored-By:` trailer naming your own model). **Never `git push`**; the user pushes. Testers then re-test and set `verified` or `reopened`.
- The shared `site/` folder is what the testers use. Only run `build_site.py` after an approved fix is applied.
