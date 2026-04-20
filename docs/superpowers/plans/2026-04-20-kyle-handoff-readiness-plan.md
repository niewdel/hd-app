# Kyle Handoff Readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the HD platform production-ready for Kyle (CEO) to use live on 2026-04-21 — no broken states, no silent data loss, no footguns, no dev artifacts, and every H-item from the 2026-04-16 site sweep resolved or explicitly waived.

**Architecture:** Five-commit rollout. Each commit is independently revertable and auto-deploys to Railway (~60s). Execution uses a lightweight verification-before-complete discipline instead of unit tests (the codebase has no test framework; the spec explicitly relies on smoke tests + Kyle's feedback loop).

**Tech Stack:** Python 3.11 / Flask / Gunicorn (backend), raw HTTP to Supabase PostgREST (data), vanilla JS in single `index.html` (frontend), ReportLab + python-docx (doc generation). No build step, no test runner.

**Reference spec:** `docs/superpowers/specs/2026-04-20-kyle-handoff-readiness-design.md`

---

## Phase 1 — Commit 1: WS1 Blockers

Small, critical, fast. Ship first to flush the obvious issues.

---

### Task 1: Remove dev console.log

**Files:**
- Modify: `index.html:11209`

- [ ] **Step 1: Verify the line exists**

Run: `grep -n "\[HD\] Loaded " index.html`
Expected output: `11209:      console.log('[HD] Loaded '+clients.length+' clients for autocomplete');`

- [ ] **Step 2: Remove the line**

Edit `index.html`. Delete the entire line `console.log('[HD] Loaded '+clients.length+' clients for autocomplete');` at line 11209. Do not replace with anything; remove the line completely.

- [ ] **Step 3: Verify the removal**

Run: `grep -n "\[HD\] Loaded " index.html`
Expected: no output.

---

### Task 2: Fix nav-admin visibility attribute

**Context:** `nav-admin` at line 1474 currently has `data-dev-hidden`, which hides it from admin users. Per spec, admin (Kyle) needs to see the admin panel — just not the Users/Roadmap/Activity/Archived tabs inside it.

**Files:**
- Modify: `index.html:1474`

- [ ] **Step 1: Read current state**

Run: `grep -n 'id="nav-admin"' index.html`
Confirm the line has `data-dev-hidden`.

- [ ] **Step 2: Swap attribute**

Replace `data-dev-hidden` with `data-admin-hidden` on the `nav-admin` element (keep all other attributes intact).

- [ ] **Step 3: Verify**

Run: `grep -n 'id="nav-admin"' index.html`
Expected: the element now has `data-admin-hidden`, not `data-dev-hidden`.

---

### Task 3: Mark Users tab and pane as dev-only

**Files:**
- Modify: `index.html:2805` (Users tab button)
- Modify: `index.html:2843` (Users pane div)

- [ ] **Step 1: Add `data-dev-hidden` to the Users tab button**

At line 2805, current state:
```html
<button class="stab" id="admin-tab-users" onclick="showAdminTab('users')">Users</button>
```
Change to:
```html
<button class="stab" id="admin-tab-users" data-dev-hidden onclick="showAdminTab('users')">Users</button>
```

- [ ] **Step 2: Add `data-dev-hidden` to the Users pane**

At line 2843, current state:
```html
<div id="admin-pane-users">
```
Change to:
```html
<div id="admin-pane-users" data-dev-hidden>
```

- [ ] **Step 3: Verify**

Run: `grep -n 'admin-tab-users\|admin-pane-users' index.html`
Expected: both elements now have `data-dev-hidden`.

---

### Task 4: Mark Activity Log and Archived tabs/panes as dev-only

**Files:**
- Modify: `index.html` admin tabs/panes for `activity` and `deleted`

- [ ] **Step 1: Locate Activity and Archived tab buttons**

Run: `grep -n 'admin-tab-activity\|admin-tab-deleted\|admin-pane-activity\|admin-pane-deleted' index.html`
Note the line numbers.

- [ ] **Step 2: Add `data-dev-hidden` to each of the four elements**

On each of the four elements (two buttons, two panes), add the `data-dev-hidden` attribute. Pattern example:
```html
<button class="stab" id="admin-tab-activity" data-dev-hidden onclick="showAdminTab('activity')">Activity Log</button>
```
And for the pane:
```html
<div id="admin-pane-activity" data-dev-hidden style="display:none;">
```

- [ ] **Step 3: Verify**

Run: `grep -nE 'id="admin-(tab|pane)-(activity|deleted)".*data-dev-hidden' index.html`
Expected: 4 lines returned.

---

### Task 5: Promote Roadmap to standalone dev-only panel

**Context:** Currently Roadmap is both a standalone `panel-roadmap` AND a nested Admin tab (`admin-tab-roadmap` / `admin-pane-roadmap`). Per spec: remove the Admin tab entirely; keep the standalone panel; mark its nav entry dev-only.

**Files:**
- Modify: `index.html:2808` (admin-tab-roadmap button — DELETE)
- Modify: `index.html:2875` (admin-pane-roadmap div — DELETE)
- Modify: `index.html:11651-11660` (showAdminTab function — drop 'roadmap' handling)
- Modify: `index.html` (nav item for standalone roadmap — add `data-dev-hidden`)

- [ ] **Step 1: Delete the Roadmap tab button**

Remove the entire line at 2808:
```html
<button class="stab" id="admin-tab-roadmap" onclick="showAdminTab('roadmap')">Roadmap</button>
```

- [ ] **Step 2: Delete the admin-pane-roadmap div**

Locate the `<div id="admin-pane-roadmap" ...>` block starting near line 2875. Delete the entire block including its closing `</div>`. Verify the surrounding admin-pane divs still close properly.

- [ ] **Step 3: Update showAdminTab to drop 'roadmap'**

At line 11652, change:
```js
['company','users','activity','deleted','roadmap'].forEach(function(t){
```
to:
```js
['company','users','activity','deleted'].forEach(function(t){
```

And at line 11659, delete the line:
```js
if(tab==='roadmap')loadAdminRoadmapList();
```

- [ ] **Step 4: Mark the standalone Roadmap nav entry as dev-only**

Run: `grep -n "showPanel('roadmap'" index.html` — locate the standalone nav item. Add `data-dev-hidden` to its nav-item element. If no standalone nav entry currently exists, add one matching the existing pattern (likely near the Admin nav item).

- [ ] **Step 5: Verify**

Run: `grep -n 'admin-tab-roadmap\|admin-pane-roadmap' index.html`
Expected: no output (both removed).

Run: `grep -n "showPanel('roadmap'" index.html`
Expected: at least one line with `data-dev-hidden`.

---

### Task 6: Hide "All Bug Reports" admin cards from admin role

**Context:** Two instances per grep — line 2559 and line 2931. Both are admin-visible management lists that should be dev-only. Kyle keeps the "Submit a Bug" form.

**Files:**
- Modify: `index.html:2559` and surrounding card
- Modify: `index.html:2931` and surrounding card

- [ ] **Step 1: Locate the parent card containers**

Run: `grep -n "All Bug Reports" index.html`
For each hit, open a 20-line window around it to find the wrapping `<div class="card ...">` or equivalent container. The container is what needs `data-dev-hidden`, not the inner title span.

- [ ] **Step 2: Add `data-dev-hidden` to each parent card**

For each of the two card containers wrapping "All Bug Reports":
- Add the `data-dev-hidden` attribute to the outer card div.
- If the card already has `data-admin-hidden`, replace it with `data-dev-hidden`.

- [ ] **Step 3: Verify submit form is NOT affected**

Run: `grep -n "Submit a Bug\|bug-submit\|submitBug" index.html | head -20`
Confirm the submit-a-bug form/card does NOT have `data-dev-hidden`. Kyle must still see that.

---

### Task 7: Add SECRET_KEY startup guard

**Files:**
- Modify: `app.py:24`

- [ ] **Step 1: Read current state**

Run: `grep -n 'SECRET_KEY' app.py`
Expected: `24:app.secret_key = os.environ.get('SECRET_KEY', 'hd-hauling-dev-key')`

- [ ] **Step 2: Replace line 24 with a startup guard**

Current:
```python
app.secret_key = os.environ.get('SECRET_KEY', 'hd-hauling-dev-key')
```
Replace with:
```python
_SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not _SECRET_KEY or _SECRET_KEY == 'hd-hauling-dev-key':
    raise RuntimeError('SECRET_KEY env var must be set to a non-default value. Refusing to start.')
app.secret_key = _SECRET_KEY
```

- [ ] **Step 3: Local import check**

Run: `python -c "import app"` from the project root.
Expected: either (a) clean import (means Railway env var is set locally), or (b) `RuntimeError: SECRET_KEY env var must be set...`. Both are correct behavior. If you get a different error, the edit is wrong.

---

### Task 8: Guard margin ZeroDivisionError in job cost path

**Context:** The PDF generator itself receives `margin_pct` as a passed-in value (`generate_job_cost.py:100`). If the frontend computes margin as `(bid-cost)/cost` with cost==0, the error is upstream. Audit the frontend callsite and add a guard there.

**Files:**
- Investigate: `index.html` (search for margin_pct computation)
- Modify: wherever the computation happens, OR `generate_job_cost.py` if needed

- [ ] **Step 1: Find frontend margin calculations**

Run: `grep -nE 'margin_pct\s*[:=]|marginPct' index.html | head -20`
Identify any site where margin_pct is divided by a value that could be 0.

- [ ] **Step 2: Add a zero-safe guard**

At each callsite found, wrap the division. Pattern:
```js
var marginPct = (cost > 0) ? ((bid - cost) / cost * 100) : 0;
```
Replace any bare `(bid-cost)/cost` expressions with this pattern.

- [ ] **Step 3: Defensive guard in the generator**

In `generate_job_cost.py`, after line 102 (`if margin_pct is not None: margin_pct = float(margin_pct)`), add:
```python
if margin_pct is None or not (margin_pct == margin_pct):  # NaN check
    margin_pct = 0.0
```

- [ ] **Step 4: Verify**

Run: `grep -nE '\(bid\s*-\s*cost\)\s*/\s*cost|bidPrice.*totalCost' index.html`
Expected: any remaining occurrences are inside a `cost > 0` guard.

---

### Task 9: Clear stale "Work order not found" state

**Files:**
- Modify: `index.html:11977`

- [ ] **Step 1: Read current state**

Run: `grep -n "Work order not found" index.html`
Expected: two hits — `11977` (sets the error) and `12485` (toasts it).

- [ ] **Step 2: Find the WO-load success path**

Locate the function that calls `renderWoHeader` or sets the wo-detail-header when a WO is successfully loaded. Grep: `grep -n "wo-detail-header" index.html | head -10`.

- [ ] **Step 3: Ensure success path clears the error HTML**

On the success branch of the WO load, ensure this runs before rendering the real header content:
```js
var hdr = document.getElementById('wo-detail-header');
if(hdr) hdr.innerHTML = '';
```
If the success path already overwrites `innerHTML` with the real header, no change needed — in that case this task is a no-op. Confirm by reading the function body.

- [ ] **Step 4: Verify**

Open `index.html` to the `wo-detail-header` handling function. Confirm every execution path either (a) writes real header content, or (b) writes the "not found" message, with no way to leave a stale "not found" visible when a later load succeeds.

---

### Task 10: Add 5s timeout + error state to weather fetch

**Files:**
- Modify: `index.html:12633` (`fetchWeather` function)

- [ ] **Step 1: Read current fetchWeather implementation**

Open `index.html` around line 12633. Read the full function body (~20-40 lines).

- [ ] **Step 2: Wrap the fetch with an AbortController timeout**

Replace the current `fetch(...)` call inside `fetchWeather` with:
```js
var controller = new AbortController();
var timeoutId = setTimeout(function(){ controller.abort(); }, 5000);
fetch(url, {signal: controller.signal})
  .then(function(r){ clearTimeout(timeoutId); return r.json(); })
  .then(function(data){ if(cb) cb(data); })
  .catch(function(err){
    clearTimeout(timeoutId);
    var el = document.getElementById('dash-weather-strip');
    if(el) el.innerHTML = '<div style="padding:12px;color:var(--muted);font-size:12px;">Weather unavailable</div>';
    if(cb) cb(null);
  });
```
Preserve the existing `url` variable and any caller arguments. If `fetchWeather` takes a callback `cb`, keep calling it with `null` on failure so callers can detect the error.

- [ ] **Step 3: Verify**

Run: `grep -nE 'fetchWeather|AbortController' index.html | head -10`
Confirm `AbortController` appears near line 12633.

---

### Task 11: Smoke test Phase 1 locally

- [ ] **Step 1: Confirm no syntax errors in index.html**

Run: `python -c "import html.parser; html.parser.HTMLParser().feed(open('index.html').read())"`
Expected: no exceptions.

- [ ] **Step 2: Confirm app.py still imports**

Run: `SECRET_KEY=test-handoff-key python -c "import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Check admin-tab function did not break**

Run: `grep -A 10 "function showAdminTab" index.html`
Expected: the tabs list no longer includes `'roadmap'`. No trailing commas or syntax issues.

---

### Task 12: Commit Phase 1

- [ ] **Step 1: Stage files**

Run: `git add index.html app.py generate_job_cost.py`

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
Phase 1: WS1 blockers for Kyle handoff

- Remove dev console.log artifact in autocomplete loader.
- Fix nav-admin visibility: data-dev-hidden → data-admin-hidden
  so admin (Kyle) can enter the admin panel for Company info.
- Mark Users / Activity Log / Archived admin tabs + panes as
  data-dev-hidden; Kyle sees only Company.
- Promote Roadmap to standalone dev-only panel; remove nested
  Admin tab + pane + showAdminTab handling.
- Mark both "All Bug Reports" admin management cards as
  data-dev-hidden; Kyle retains the submit form.
- SECRET_KEY startup guard refuses boot on default/empty.
- Zero-safe guard on margin_pct computation in job-cost path
  plus defensive None/NaN guard in generate_job_cost.py.
- Clear stale "Work order not found" HTML when a valid WO
  loads after a failed one.
- Weather fetch gets a 5s AbortController timeout and renders
  "Weather unavailable" on failure.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push and wait for Railway**

```bash
git push origin main
```
Wait ~60s. Open `https://web-production-e19b3.up.railway.app/auth/check` — expect a JSON response, not a 500. If the response is a 500, Railway env var for SECRET_KEY may be missing — fix via Railway dashboard before continuing.

- [ ] **Step 4: Live smoke as dev**

Log in as `justin@hdgrading.com`. Walk: Dashboard → Projects → Admin → confirm all tabs visible (Company, Users, Activity, Archived). Confirm standalone Roadmap panel is reachable from nav. Confirm no console errors.

- [ ] **Step 5: Live smoke as admin**

Log in as `kharrison@hdgrading.com` (use the temporary password set earlier, or reset via task 29 before this step). Walk: Admin → confirm ONLY Company tab is visible, no Users/Activity/Archived/Roadmap tab visible. Confirm Roadmap nav entry is NOT in sidebar. Confirm Bug Reports page shows submit form but no "All Bug Reports" card.

---

## Phase 2 — Commit 2: WS3 Backend Hardening + Backfill

Backend first because H8 `_safe_error` and H3 `_sb_eq` feed into frontend error surfaces that WS2 depends on.

---

### Task 13: Write created_by backfill migration

**Files:**
- Create: `docs/superpowers/migrations/2026-04-20-created-by-backfill.sql`

- [ ] **Step 1: Identify affected tables**

Run this Supabase query to confirm which tables have `created_by` columns:
```bash
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/proposals?select=id,created_by&created_by=is.null&limit=5" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY"
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/change_orders?select=id,created_by&created_by=is.null&limit=5" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY"
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/clients?select=id,created_by&created_by=is.null&limit=5" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY"
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_tasks?select=id,created_by&created_by=is.null&limit=5" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY"
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_reminders?select=id,created_by&created_by=is.null&limit=5" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY"
```
Note which tables return non-empty arrays — those need the backfill. If a table errors with `column "created_by" does not exist`, skip it.

- [ ] **Step 2: Write the SQL file**

Create `docs/superpowers/migrations/2026-04-20-created-by-backfill.sql` with content:
```sql
-- Backfill null created_by to 'estimates@hdgrading.com' before ownership
-- checks land. This is a string-only value, not a real user row.

UPDATE proposals    SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE change_orders SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE clients      SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE hd_tasks     SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
UPDATE hd_reminders SET created_by = 'estimates@hdgrading.com' WHERE created_by IS NULL;
```
Remove any `UPDATE` line whose table returned "column does not exist" in Step 1.

- [ ] **Step 3: Apply the migration**

Use the Supabase MCP (if available) to execute the SQL. Otherwise, use the SQL editor in the Supabase dashboard. Verify each UPDATE returns a count message.

- [ ] **Step 4: Verify backfill**

Repeat the curl commands from Step 1 with `?created_by=is.null`. Expected: all return `[]`.

---

### Task 14: Add `_safe_error` helper

**Files:**
- Modify: `app.py` near other helpers (line ~100, above `require_auth`)

- [ ] **Step 1: Read surrounding context**

Read `app.py:94-115` to see where other helpers live. Plan insertion around line 114 (after `log_access`, before `require_auth`).

- [ ] **Step 2: Insert the helper**

Insert at line 114 (or the end of the helper block):
```python
def _safe_error(e, context=''):
    """Log exception internally; return a generic client-safe message.
    Use in authed routes where leaking str(e) is undesirable."""
    try:
        app.logger.exception('[%s] %s', context or 'route', e)
    except Exception:
        pass
    return jsonify({'error': 'Internal error. Check logs.'}), 500
```

- [ ] **Step 3: Verify**

Run: `grep -n "_safe_error" app.py`
Expected: one line — the definition.

---

### Task 15: Pilot-migrate one route to `_safe_error` (verify pattern)

**Files:**
- Modify: one `@require_auth` route in `app.py` currently using `str(e)`

- [ ] **Step 1: Pick a pilot route**

Run: `grep -n "'error': str(e)" app.py | head -5`
Pick the first `@require_auth` route (not `@require_dev` or a public route). Note its line.

- [ ] **Step 2: Migrate its error handler**

Inside that route's `except` block, replace:
```python
return jsonify({'error': str(e)}), 500
```
with:
```python
return _safe_error(e, context='<route-name>')
```
Replace `<route-name>` with the route's URL path (e.g., `'quotes/list'`).

- [ ] **Step 3: Local sanity check**

Run: `SECRET_KEY=test-handoff-key python -c "import app; print('ok')"`
Expected: `ok`.

---

### Task 16: Migrate remaining authed routes to `_safe_error`

**Files:**
- Modify: `app.py` (~30 authed route error handlers)

- [ ] **Step 1: Enumerate all candidate sites**

Run: `grep -nB 20 "'error': str(e)" app.py > /tmp/safe-error-sites.txt`
Open the file. Mark each hit as:
- **AUTHED** — route has `@require_auth`, `@require_admin`, or `@require_dev` within 20 lines above.
- **PUBLIC** — no auth decorator (e.g., `/proposal/view`, `/leads/submit`). Skip these; they already use a separate pattern.

- [ ] **Step 2: Migrate each AUTHED hit**

For each AUTHED site:
- Replace the `return jsonify({'error': str(e)}), 500` (or 400/403) line with `return _safe_error(e, context='<url-path>')`.
- Preserve the original HTTP status code only when it's 400 or 403 (semantic). For 500s, `_safe_error` returns 500.
- If the status was 400 ("bad request"), keep an explicit message: leave that handler unchanged — `_safe_error` is only for 500-class leaks.

- [ ] **Step 3: Verify**

Run: `grep -c "'error': str(e)" app.py`
Expected: a small single-digit number (remaining are public-route handlers; do not touch).

Run: `grep -c "_safe_error" app.py`
Expected: 25–30 (one definition + ~25–30 callsites).

- [ ] **Step 4: Local sanity check**

Run: `SECRET_KEY=test-handoff-key python -c "import app; print('ok')"`
Expected: `ok`.

---

### Task 17: Add `_sb_eq` helper for query-param safety

**Files:**
- Modify: `app.py` near `sb_url` (line ~74)

- [ ] **Step 1: Insert helper**

After the `sb_url` function (around line 76), add:
```python
from urllib.parse import quote as _url_quote

def _sb_eq(column, value):
    """Build a safe PostgREST 'column=eq.<value>' filter with proper URL encoding.
    Prevents query-param injection via unescaped & or ? in value."""
    return '{}=eq.{}'.format(column, _url_quote(str(value), safe=''))
```

- [ ] **Step 2: Verify**

Run: `grep -n "_sb_eq\|_url_quote" app.py`
Expected: 2+ lines from the import and definition.

---

### Task 18: Migrate PostgREST query f-strings to `_sb_eq`

**Context:** 104 `eq.` occurrences throughout `app.py`. Most are in f-strings like `f'?id=eq.{qid}'`. The target is to route them through `_sb_eq` where the interpolated value is not a strictly-validated integer.

**Files:**
- Modify: `app.py` (all call sites)

- [ ] **Step 1: Enumerate sites**

Run: `grep -nE "f['\"].*eq\.\{" app.py > /tmp/eq-sites.txt`
Review the file.

- [ ] **Step 2: Classify each site**

For each hit, classify:
- **INT-PARAM** — interpolated value is a route variable typed `int` (e.g., `<int:qid>`). Low risk. Skip unless the migration is trivial.
- **SESSION-STR** — interpolated value is `session.get('username')`. Kyle and Justin both have `@hdgrading.com` emails; validated at login (line ~155). Low risk, but migrate for defense-in-depth.
- **USER-INPUT** — interpolated value comes from `request.args.get` or `data.get` without strict type coercion. **Must migrate.**

- [ ] **Step 3: Migrate USER-INPUT and SESSION-STR sites**

For each USER-INPUT or SESSION-STR site, replace:
```python
url = sb_url('proposals', f'?id=eq.{qid}')
```
with:
```python
url = sb_url('proposals', '?' + _sb_eq('id', qid))
```
Watch for f-strings with multiple `eq.` clauses joined by `&` — handle each segment individually.

- [ ] **Step 4: Verify**

Run: `grep -c "_sb_eq" app.py`
Expected: 1 (definition) + N (callsites). N should be at least 20.

Run: `SECRET_KEY=test-handoff-key python -c "import app; print('ok')"`
Expected: `ok`.

---

### Task 19: Add `_owns_or_admin` helper

**Files:**
- Modify: `app.py` near other helpers (after `require_dev`, line ~143)

- [ ] **Step 1: Insert helper**

After line 143 (after the `require_dev` decorator), add:
```python
def _owns_or_admin(record_created_by):
    """Return True if the current session owns the record or is admin/dev.
    Null-safe — records with null created_by are owned by 'estimates@hdgrading.com'
    after the 2026-04-20 backfill, so null here means not-yet-migrated and
    we fall through to admin/dev check."""
    role = session.get('role', '')
    if role in ('admin', 'dev'):
        return True
    if record_created_by and record_created_by == session.get('username'):
        return True
    return False
```

- [ ] **Step 2: Verify**

Run: `grep -n "_owns_or_admin" app.py`
Expected: one line (the definition).

---

### Task 20: Apply ownership checks to delete/update routes

**Context:** Eight target routes. Kyle is admin so passes unconditionally; the guard becomes load-bearing only when a non-admin user is added.

**Files:**
- Modify: `app.py:399` (`/quotes/delete`)
- Modify: `app.py:651` (`/projects/update`)
- Modify: `app.py:712` (`/clients/delete`)
- Modify: `app.py:1067` (`/change-orders/delete`)
- Modify: `app.py:2469` (`/tasks PATCH`)
- Modify: `app.py:2494` (`/tasks DELETE`)
- Modify: `app.py:2554` (`/reminders PATCH`)
- Modify: `app.py:2578` (`/reminders DELETE`)

- [ ] **Step 1: For each target route, insert a fetch-then-check**

Pattern (example for `/quotes/delete/<int:qid>` at line 399):
```python
@app.route('/quotes/delete/<int:qid>', methods=['DELETE'])
@require_auth
def quotes_delete(qid):
    try:
        # Ownership check
        lookup = http.get(sb_url('proposals', '?' + _sb_eq('id', qid) + '&select=created_by'),
                          headers=sb_admin_headers(), timeout=10)
        rows = lookup.json() if lookup.ok else []
        if not rows:
            return jsonify({'error': 'Not found'}), 404
        if not _owns_or_admin(rows[0].get('created_by')):
            return jsonify({'error': 'Not permitted'}), 403
        # ... existing delete logic unchanged below this point
```
Apply the same pattern to each of the 8 routes, adjusting table name and column name per route.

- [ ] **Step 2: Table-name mapping**

| Route | Supabase table |
|---|---|
| `/quotes/delete` | `proposals` |
| `/projects/update` | `proposals` |
| `/clients/delete` | `clients` |
| `/change-orders/delete` | `change_orders` |
| `/tasks PATCH/DELETE` | `hd_tasks` |
| `/reminders PATCH/DELETE` | `hd_reminders` |

- [ ] **Step 3: Verify**

Run: `grep -c "_owns_or_admin" app.py`
Expected: 1 (definition) + 8 (callsites) = 9.

Run: `SECRET_KEY=test-handoff-key python -c "import app; print('ok')"`
Expected: `ok`.

---

### Task 21: Add explicit CORS header for Railway domain

**Files:**
- Modify: `app.py:51` (`set_security_headers`)

- [ ] **Step 1: Read current headers**

Read `app.py:51-72`. Confirm the current `set_security_headers` body.

- [ ] **Step 2: Add CORS header**

Insert right before `return response` (around line 72):
```python
    origin = request.headers.get('Origin', '')
    allowed = 'https://web-production-e19b3.up.railway.app'
    if origin == allowed:
        response.headers['Access-Control-Allow-Origin'] = allowed
        response.headers['Access-Control-Allow-Credentials'] = 'true'
```

- [ ] **Step 3: Verify**

Run: `grep -n "Access-Control-Allow-Origin" app.py`
Expected: one line inside `set_security_headers`.

---

### Task 22: Create `hd_email_log` table

**Files:**
- Create: `docs/superpowers/migrations/2026-04-20-email-log.sql`

- [ ] **Step 1: Write migration**

Content:
```sql
CREATE TABLE IF NOT EXISTS hd_email_log (
  id SERIAL PRIMARY KEY,
  sender_username TEXT NOT NULL,
  recipient_to TEXT NOT NULL,
  subject TEXT,
  attachment_name TEXT,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  success BOOLEAN NOT NULL DEFAULT true,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_hd_email_log_sender_time ON hd_email_log(sender_username, sent_at DESC);
```

- [ ] **Step 2: Apply migration**

Run the SQL against Supabase (MCP or dashboard).

- [ ] **Step 3: Verify**

```bash
curl -s "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_email_log?limit=1" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY"
```
Expected: `[]` (table exists, empty).

---

### Task 23: Rate limit + audit log `/send-email`

**Files:**
- Modify: `app.py:1078` (`/send-email` route)

- [ ] **Step 1: Read current send_email body**

Read `app.py:1078-1130` (or wherever the function ends).

- [ ] **Step 2: Add rate limit + audit log**

Near the top of `send_email()`, after the auth check but before the actual send:
```python
    sender = session.get('username', '')
    # 20 sends per rolling 24h per user
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    count_url = sb_url('hd_email_log',
        '?select=id&' + _sb_eq('sender_username', sender) +
        '&sent_at=gte.' + _url_quote(since))
    count_resp = http.get(count_url, headers=sb_admin_headers(prefer='count=exact'), timeout=10)
    if count_resp.ok:
        count_header = count_resp.headers.get('Content-Range', '')
        sent_count = 0
        if '/' in count_header:
            try: sent_count = int(count_header.split('/')[-1])
            except ValueError: pass
        if sent_count >= 20:
            return jsonify({'error': 'Daily email limit reached (20 per 24h).'}), 429
```

At the end of `send_email()`, after the send attempt, log the result:
```python
    try:
        http.post(sb_url('hd_email_log'),
                  headers=sb_admin_headers(),
                  json={
                      'sender_username': sender,
                      'recipient_to': (data.get('to') or '')[:500],
                      'subject': (data.get('subject') or '')[:500],
                      'attachment_name': (data.get('attachment_name') or '')[:500],
                      'success': send_succeeded,  # set by existing send logic
                      'error': None if send_succeeded else (send_error_str or '')[:500]
                  }, timeout=10)
    except Exception:
        pass  # audit log failure must not fail the user's send
```
Adjust `send_succeeded` and `send_error_str` variable names to match the existing code structure.

- [ ] **Step 3: Import check**

At the top of `app.py`, verify `from datetime import datetime, timedelta` is imported. If not, add it.

- [ ] **Step 4: Local sanity check**

Run: `SECRET_KEY=test-handoff-key python -c "import app; print('ok')"`
Expected: `ok`.

---

### Task 24: Commit Phase 2

- [ ] **Step 1: Stage**

```bash
git add app.py docs/superpowers/migrations/
```

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
Phase 2: WS3 backend hardening + created_by backfill

Closed H1/H3/H4/H6/H7/H8 from the 2026-04-16 site sweep.

- _safe_error helper + migrate ~30 authed-route str(e) leaks
  to generic messages with internal logging (H8).
- _sb_eq helper wrapping urllib.parse.quote; migrated PostgREST
  query-param f-strings to prevent injection (H3).
- _owns_or_admin guard applied to /quotes/delete,
  /projects/update, /clients/delete, /change-orders/delete,
  /tasks, /reminders (PATCH + DELETE each) (H4).
- Explicit CORS Access-Control-Allow-Origin for the Railway
  production domain (H7).
- /send-email: 20/24h rolling rate limit per user + audit log
  to new hd_email_log table (H1).
- SQL migrations committed for created_by backfill to
  estimates@hdgrading.com and hd_email_log table.

H2 (ICS token) and H5 (file upload magic bytes) waived per
spec — rationale in the handoff-readiness design doc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push + Railway smoke**

```bash
git push origin main
```
Wait ~60s. `curl -s https://web-production-e19b3.up.railway.app/auth/check` — expect JSON, not 500.

- [ ] **Step 4: Live smoke**

Log in as dev. Save a proposal. Edit it. Delete a test reminder. Confirm no 500s in network tab. Confirm delete succeeded.

---

## Phase 3 — Commit 3: WS2 Silent-Failure Hardening

Introduce `_safeFetch`, migrate write-path handlers.

---

### Task 25: Add `_safeFetch` helper

**Files:**
- Modify: `index.html` (near top of the main `<script>` block, with other fetch helpers)

- [ ] **Step 1: Find insertion point**

Run: `grep -n "function esc\|function toast" index.html | head -5`
Insert near the global utility helpers (typically in the 3800-4000 range, above `showAdminElements`).

- [ ] **Step 2: Insert helper**

```js
/**
 * Fetch wrapper that:
 *  - throws on non-2xx,
 *  - preserves server-sent JSON {error} messages,
 *  - always returns parsed JSON on success (or null on 204).
 * Use in any save/delete/update handler instead of raw fetch().
 */
async function _safeFetch(url, opts){
  opts = opts || {};
  opts.headers = opts.headers || {};
  if(opts.body && !opts.headers['Content-Type']){
    opts.headers['Content-Type'] = 'application/json';
  }
  const r = await fetch(url, opts);
  let body = null;
  try { body = await r.json(); } catch(_) {}
  if(!r.ok){
    const msg = (body && body.error) || ('Request failed ('+r.status+')');
    const err = new Error(msg);
    err.status = r.status;
    err.body = body;
    throw err;
  }
  return body;
}
```

- [ ] **Step 3: Verify**

Run: `grep -n "_safeFetch" index.html`
Expected: one line (definition).

---

### Task 26: Migrate saveBugUpdate

**Files:**
- Modify: `index.html` (`saveBugUpdate` function)

- [ ] **Step 1: Locate**

Run: `grep -n "function saveBugUpdate" index.html`

- [ ] **Step 2: Rewrite the fetch flow**

Replace the existing `fetch('/bugs/' + ...)` call pattern with:
```js
try {
  await _safeFetch('/bugs/' + _editingBugId, {
    method: 'PATCH',
    body: JSON.stringify({status: newStatus, admin_notes: notes})
  });
  toast('Bug updated', 'ok');
  closeBugUpdateModal();
  loadBugs();
} catch(e) {
  toast(e.message || 'Failed to update bug', 'err');
  // Intentionally keep the modal open so user can retry.
}
```
Mark the enclosing function `async`. Remove any existing `.then()` chain.

- [ ] **Step 3: Verify**

Run: `grep -nA 20 "function saveBugUpdate" index.html | head -30`
Confirm the function uses `_safeFetch`, is `async`, and has the try/catch.

---

### Task 27: Migrate deleteReminder

**Files:**
- Modify: `index.html` (`deleteReminder` function)

- [ ] **Step 1: Locate**

Run: `grep -n "function deleteReminder" index.html`

- [ ] **Step 2: Rewrite**

```js
async function deleteReminder(rid){
  if(!confirm('Delete this reminder?')) return;
  try {
    await _safeFetch('/reminders/' + rid, {method:'DELETE'});
    toast('Reminder deleted','ok');
    loadReminders();
  } catch(e) {
    toast(e.message || 'Failed to delete reminder', 'err');
  }
}
```

- [ ] **Step 3: Verify**

Run: `grep -nA 10 "function deleteReminder" index.html`
Confirm the rewritten body.

---

### Task 28: Migrate remaining write-path handlers

**Files:**
- Modify: `index.html` — multiple handlers

- [ ] **Step 1: Enumerate**

Run: `grep -nE "fetch\('/(quotes|projects|clients|subs|tasks|reminders|change-orders|admin|bugs)/" index.html > /tmp/write-sites.txt`
Review. Each hit is a candidate for `_safeFetch`.

- [ ] **Step 2: Migrate each**

Apply the pattern:
```js
try {
  const result = await _safeFetch(url, {method: 'POST|PATCH|DELETE', body: JSON.stringify(payload)});
  toast('Saved','ok');
  closeModal();
  reload();
} catch(e) {
  toast(e.message || 'Failed', 'err');
  // DO NOT close modal on failure.
}
```

Handlers that need migration (non-exhaustive — use grep list as ground truth):
- `saveClient`, `deleteClient`
- `saveSub`, `deleteSub`
- `saveReminder`
- `saveTask`, `deleteTask`, task PATCH flow
- `saveQuote` (including lock-path — keep existing toast for lock case)
- Change-order delete (`deleteCO` or equivalent)
- `saveCompanyInfo`
- Bug-submit form handler

Mark each enclosing function `async`.

- [ ] **Step 3: Verify coverage**

Run: `grep -c "_safeFetch" index.html`
Expected: 15+ (helper definition + all migrated callsites).

---

### Task 29: Generate Kyle's password and store bcrypt hash

**Context:** New task per user request during spec review. Generate a secure random password, hash with existing bcrypt flow, update Kyle's `pin_hash` in Supabase. Plaintext goes into the runbook in Phase 5.

**Files:**
- Run: a local Python one-liner
- Update: Supabase `hd_users` row where `id=12`

- [ ] **Step 1: Generate password**

Run:
```bash
python -c "import secrets, string; alphabet = string.ascii_letters + string.digits; print(''.join(secrets.choice(alphabet) for _ in range(16)))"
```
Save the output to a temporary variable. Call it `KYLE_PLAINTEXT`.

- [ ] **Step 2: Bcrypt hash it**

Run:
```bash
python -c "
from security import hash_password
print(hash_password('$KYLE_PLAINTEXT'))
"
```
Save the output. Call it `KYLE_HASH`.

- [ ] **Step 3: Update Supabase**

```bash
curl -s -X PATCH "https://azznfkboiwayifhhcguz.supabase.co/rest/v1/hd_users?id=eq.12" \
  -H "apikey: $SERVICE_KEY" -H "Authorization: Bearer $SERVICE_KEY" \
  -H "Content-Type: application/json" -H "Prefer: return=minimal" \
  -d "{\"pin_hash\":\"$KYLE_HASH\"}"
```
Expected: empty response body, HTTP 204.

- [ ] **Step 4: Verify login works**

Log out. Log in at the Railway URL as `kharrison@hdgrading.com` with `$KYLE_PLAINTEXT`. Confirm successful login. Log out again.

- [ ] **Step 5: Stash the plaintext for Phase 5**

Write `KYLE_PLAINTEXT` to `/tmp/kyle-password.txt` for use in the runbook task (Task 42). This file does not get committed; it's consumed in-session.

---

### Task 30: Commit Phase 3

- [ ] **Step 1: Stage**

```bash
git add index.html
```
Do NOT stage `/tmp/kyle-password.txt`.

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
Phase 3: WS2 silent-failure hardening

- New _safeFetch wrapper: throws on non-2xx, preserves server
  error messages, returns parsed JSON on success.
- Migrated all write-path UI handlers (save/delete for bugs,
  reminders, clients, subs, tasks, quotes, change orders,
  company info) to use _safeFetch with try/catch + error toast.
- Modals now stay open on failure so the user can retry
  instead of silently losing their edit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin main
```

- [ ] **Step 3: Smoke**

Wait 60s. Log in as dev. Open a client, edit, save — toast. Force a failure by disconnecting wifi mid-save — confirm toast shows and modal stays open.

---

## Phase 4 — Commit 4: WS4 Per-Panel Polish + WS5 Doc Generators

---

### Task 31: Dashboard polish

**Files:**
- Modify: `index.html` — dashboard render functions

- [ ] **Step 1: Today's schedule empty state**

Run: `grep -n "dash-today-schedule" index.html`. Find the render function. When the events array is empty, inject:
```html
<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px;">No scheduled work today. Open the Schedule panel to add a work order.</div>
```

- [ ] **Step 2: Activity feed fallback**

Find the activity render function (`renderActivity` or similar). When empty, show:
```html
<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px;">No recent activity.</div>
```

- [ ] **Step 3: Verify**

Open Dashboard with no work orders today. Confirm empty state renders. Open with activity log empty, confirm fallback renders.

---

### Task 32: Projects + Pipeline polish

**Files:**
- Modify: `index.html` — projects / pipeline render functions

- [ ] **Step 1: Filter-empty state on Projects list**

Find `renderProjects` or `filterProjects`. When filter returns 0 results, render:
```html
<div style="padding:24px;text-align:center;color:var(--muted);">No projects match this filter. <button class="btn-ghost" onclick="clearProjectFilters()">Clear filters</button></div>
```
Add `clearProjectFilters()` as a helper that resets all filter UI + calls `renderProjects` again.

- [ ] **Step 2: Kanban horizontal-scroll affordance**

On the pipeline Kanban container (overflow-x:auto at line ~2048), add a subtle fade on the right edge to hint at scrolling. Inline style:
```html
<div class="pipeline-board" style="position:relative;overflow-x:auto;mask-image:linear-gradient(to right, black 95%, transparent);">
```
Adjust selector to match existing class name.

- [ ] **Step 3: Verify**

Open Projects with no matching filter. Confirm empty state. Open pipeline on a screen narrower than the total Kanban width. Confirm a right-edge fade is visible.

---

### Task 33: Build Proposal polish

**Files:**
- Modify: `index.html` — Build Proposal panel

- [ ] **Step 1: Lock indicator**

Run: `grep -n "_proposalLocked" index.html`. Find where the flag is set. In the Build Proposal header area, add an indicator:
```html
<div id="proposal-lock-badge" style="display:none;padding:4px 10px;background:var(--red);color:#fff;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:0.4px;">LOCKED · READ-ONLY</div>
```
And in the function that sets `_proposalLocked = true`, add:
```js
var badge = document.getElementById('proposal-lock-badge');
if(badge) badge.style.display = _proposalLocked ? '' : 'none';
```

- [ ] **Step 2: Verify**

Open a proposal that's in the "Approved" or later stage (where lock fires). Confirm the LOCKED badge appears.

---

### Task 34: Settings — Restore Defaults button

**Files:**
- Modify: `index.html` — Settings Material Prices card

- [ ] **Step 1: Locate Material Prices card**

Run: `grep -n "renderMatTable\|Material Prices" index.html | head -5`.

- [ ] **Step 2: Add button**

Inside the Material Prices card header, add:
```html
<button class="btn-ghost" onclick="if(confirm('Replace the current material table with the default list? This cannot be undone.')) applyMatDefaults();">Restore Defaults</button>
```

- [ ] **Step 3: Ensure `applyMatDefaults` exists**

Run: `grep -n "function applyMatDefaults" index.html`.

If it exists, confirm it copies `MAT_DEFAULT` into `MAT`, re-renders, and persists. If it does not exist, add:
```js
function applyMatDefaults(){
  MAT = Object.assign({}, MAT_DEFAULT);
  LTYPES = Object.keys(MAT_DEFAULT);
  try { localStorage.setItem('hd_mat_custom', JSON.stringify(MAT)); } catch(_){}
  renderMatTable();
  toast('Material defaults restored', 'ok');
}
```

- [ ] **Step 4: Verify**

In Settings, click "Restore Defaults", confirm prompt, confirm the material table returns to the seed values.

---

### Task 35: Work Order polish

**Files:**
- Modify: `index.html` — WO handlers

- [ ] **Step 1: Null-guard clock-in/out**

Run: `grep -n "_woActiveEntry" index.html | head -10`. In each handler that reads `_woActiveEntry`, add an explicit toast when null:
```js
if(!_woActiveEntry){
  toast('No active time entry to clock out.','err');
  return;
}
```
(Instead of silent `return`.)

- [ ] **Step 2: Verify**

Open a work order. Try to clock out without having clocked in. Confirm a toast appears explaining why.

---

### Task 36: Contacts, Schedule, Reports, Tasks, Change Orders empty states

**Files:**
- Modify: `index.html` — various render functions

- [ ] **Step 1: Locate each panel's empty-state**

For each of Contacts (clients + subs), Schedule (queue panel), Reports (picker + output), Tasks (list), Change Orders (list):
- Run: `grep -n "renderClients\|renderSubs\|renderQueue\|renderTasks\|renderCOList" index.html`.
- Find the block that renders when the list is empty (may be absent).

- [ ] **Step 2: Add empty-state HTML to each**

Pattern:
```js
if(!items || items.length === 0){
  container.innerHTML = '<div style="padding:24px;text-align:center;color:var(--muted);font-size:13px;">' +
    emptyMessage +
    '</div>';
  return;
}
```
Where `emptyMessage` is appropriate text per panel:
- Contacts clients: "No clients yet. Add one with the + button."
- Contacts subs: "No subcontractors yet."
- Schedule queue: "No unscheduled work orders."
- Tasks: "No open tasks."
- Change Orders: "No change orders for this proposal."

- [ ] **Step 3: Verify**

Open each panel with empty data. Confirm each empty state renders with the right message.

---

### Task 37: Doc generator hardening — proposal pricing table

**Files:**
- Modify: `generate_proposal.py` (pricing options table build, around line 909)

- [ ] **Step 1: Locate the pricing options table build**

Read `generate_proposal.py:900-940`.

- [ ] **Step 2: Add description length cap**

Where option descriptions are rendered into cells, truncate if > 150 chars:
```python
def _truncate(txt, n=150):
    if not txt: return ''
    s = str(txt)
    return s if len(s) <= n else s[:n-1] + '…'
```
Apply to the description cell value.

- [ ] **Step 3: Verify**

Generate a PDF with a proposal containing an option whose description is > 200 chars. Open the PDF. Confirm truncation with ellipsis.

---

### Task 38: Doc generator hardening — change order numerics

**Files:**
- Modify: `generate_change_order.py` (numeric parsing)

- [ ] **Step 1: Guard numeric inputs**

Near the top of `build()` or wherever `add_total`/`deduct_total` are parsed, add:
```python
def _num(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except (TypeError, ValueError):
        return default

add_total    = _num(data.get('add_total'))
deduct_total = _num(data.get('deduct_total'))
```

Replace any bare `float(data.get(...))` calls with `_num(data.get(...))`.

- [ ] **Step 2: Verify**

Generate a change order PDF with missing add_total. Confirm no 500.

---

### Task 39: Doc generator smoke test

- [ ] **Step 1: Make curl wrapper**

Create `/tmp/gen-smoke.sh`:
```bash
#!/bin/bash
BASE="https://web-production-e19b3.up.railway.app"
COOKIE="/tmp/hd.cookies"
# Login
curl -s -c $COOKIE -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"justin@hdgrading.com","password":"'"$JUSTIN_PASSWORD"'"}' > /dev/null

# For each generator, POST a realistic payload; expect PDF/DOCX bytes
for route in generate-pdf generate-docx generate-co-pdf generate-job-cost; do
  echo "Testing /$route"
  curl -s -b $COOKIE -X POST "$BASE/$route" \
    -H "Content-Type: application/json" \
    -d @/tmp/gen-payload.json -o "/tmp/out-$route.bin" -w "%{http_code}\n"
done
```

- [ ] **Step 2: Run smoke**

Export `JUSTIN_PASSWORD` in your shell. Save a realistic payload JSON to `/tmp/gen-payload.json` (copy from an actual saved proposal — use Supabase curl to grab `snap` for a real row).

Run the script. Expected: all four return 200. Open each output file to verify it's a real PDF/DOCX and not an error page.

- [ ] **Step 3: Stripped-payload test**

Modify `/tmp/gen-payload.json` to remove optional fields. Re-run. Expected: all four still return 200; outputs may have blank sections but no crashes.

---

### Task 40: Commit Phase 4

- [ ] **Step 1: Stage**

```bash
git add index.html generate_proposal.py generate_change_order.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
Phase 4: WS4 per-panel polish + WS5 doc generator hardening

- Dashboard: empty states for today's schedule and activity.
- Projects: filter-empty state with Clear button;
  horizontal-scroll fade affordance on pipeline Kanban.
- Build Proposal: visible LOCKED · READ-ONLY badge when
  _proposalLocked is true.
- Settings: Restore Defaults button for Material Prices
  (confirms before overwriting).
- Work Order: explicit toast when clock-in/out fires with
  no active entry.
- Contacts, Schedule, Reports, Tasks, Change Orders: empty
  states added.
- generate_proposal.py: truncate option descriptions > 150
  chars with ellipsis to prevent table overflow.
- generate_change_order.py: _num() wrapper defends against
  missing or non-numeric add_total / deduct_total inputs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin main
```

- [ ] **Step 3: Smoke**

Wait 60s. Walk every panel as dev, confirm no regressions. Generate one PDF from a real proposal, confirm it renders.

---

## Phase 5 — Commit 5: Runbook + Housekeeping

---

### Task 41: Verify Phase 3 password is still valid

- [ ] **Step 1: Confirm plaintext is saved**

Run: `cat /tmp/kyle-password.txt`. Expected: the 16-char password generated in Task 29.

- [ ] **Step 2: Re-test login**

At the Railway URL, log in as `kharrison@hdgrading.com` with this password. Confirm success. Log out.

---

### Task 42: Write kyle-handoff.md runbook

**Files:**
- Create: `docs/kyle-handoff.md`

- [ ] **Step 1: Get the plaintext password**

```bash
KYLE_PASS=$(cat /tmp/kyle-password.txt)
```

- [ ] **Step 2: Write the runbook**

Create `docs/kyle-handoff.md` with this content (substitute `${KYLE_PASS}` with the actual value):

```markdown
# Welcome to the HD Platform

## Login

- **URL:** https://web-production-e19b3.up.railway.app
- **Username:** kharrison@hdgrading.com
- **Temporary password:** <REPLACE_WITH_KYLE_PASS>
- **First step:** log in, then change your password via Settings → My Profile → Change Password.

## What This App Is

HD's internal operations platform — proposals, CRM, pipeline, scheduling,
work orders, job costing, reporting, exports. Built in-house. Every panel
you see is live production data.

## What Justin Wants From You

Walk the whole thing. Open every panel. Build a proposal. Move it through
the pipeline. Export a PDF. File a change order against it. Log a work
order. The goal: fresh eyes on everything. Tell us what's confusing, what's
broken, what's missing, what you'd change.

Specific surfaces where your input matters most:
- Dashboard — does the top-of-screen info feel like the right stuff?
- Build Proposal — does the flow make sense end-to-end?
- Pipeline — does it show what you need to see to run the business?
- Reports — is anything missing?

## What's Still Polish-Pending (Known)

We did a full sweep the night before handoff, but here's what's explicitly
not yet addressed so you don't flag these as bugs:

- **Full visual redesign** — we have a design direction locked in
  (Field Ops Premium + Command Center density + Executive Industrial
  polish for exports), but the rollout is a multi-week arc. What you see
  tomorrow is the current system.
- **Mobile UX** — the app works on mobile but hasn't had a dedicated
  mobile pass. Tables and dense views will feel cramped on a phone.
- **ICS calendar feed tokens** — per-user rotation is deferred; a single
  shared token powers the schedule feed for now.
- **File-upload magic-byte validation** — deferred (no execution risk,
  static-asset serving only).

## How to Report a Bug or Idea

Use the in-app **Bug Reports** panel. Click "Submit a Bug," type a short
description, attach a screenshot if relevant, set severity, submit. That
goes into the tracked queue.

## When to Escalate to Justin Directly

Text or call Justin's cell for:
- You can't log in at all.
- You see a stack trace or a 500 error page.
- You think data you saved is gone.
- Something you expected to be there isn't.

For anything else, the Bug Reports panel is faster for us to triage than
a text thread.

— Justin
```

Replace `<REPLACE_WITH_KYLE_PASS>` literally with the contents of `/tmp/kyle-password.txt`.

- [ ] **Step 3: Verify**

Open `docs/kyle-handoff.md`. Confirm the password is pasted in and readable. No `${KYLE_PASS}` placeholders remaining.

---

### Task 43: Update CLAUDE.md

**Files:**
- Modify: `/Users/justinledwein/Documents/claude-projects/Niewdel/hd-app/CLAUDE.md`

- [ ] **Step 1: Document the new role visibility model**

Add a new section before "### Admin Panel" (search for that anchor):

```markdown
### Role Visibility Model (updated 2026-04-20)

- `dev` (Justin): sees everything, including Users / Activity Log / Archived / Roadmap / All Bug Reports list.
- `admin` (Kyle): sees everything EXCEPT Users / Activity Log / Archived / Roadmap / All Bug Reports list. Can submit bugs.
- `user`: standard operational role, no admin surfaces.
- `field`: reduced UI, no pricing surfaces.

**Attribute rules:**
- `data-admin-hidden` — hidden from user/field, visible to admin+dev.
- `data-dev-hidden` — hidden from everyone except dev.
- `data-field-hidden` — hidden only from field.

`showAdminElements()` removes these attributes based on `window._userRole`.

The Roadmap panel is now a standalone nav entry with `data-dev-hidden`, not a nested Admin tab. Admin tab list in `showAdminTab` is `['company','users','activity','deleted']` — no `'roadmap'`.
```

- [ ] **Step 2: Add new helpers to the API / conventions list**

Document the new backend helpers:
- `_safe_error(e, context)` — logs internally, returns generic 500.
- `_sb_eq(column, value)` — URL-safe PostgREST filter builder.
- `_owns_or_admin(record_created_by)` — ownership check with null-safe admin/dev bypass.

Document the new frontend helper:
- `_safeFetch(url, opts)` — throws on non-2xx, preserves server error messages. Use in all write-path handlers.

- [ ] **Step 3: Update the "Fixed bugs" / pending-work sections**

Move H1, H3, H4, H6, H7, H8 from pending to fixed. Mark H2, H5 as "waived per 2026-04-20 spec."

Add an entry in Pending for:
- Redesign rollout (all REDESIGN_*.md files).

---

### Task 44: Update MEMORY.md

**Files:**
- Modify: `/Users/justinledwein/.claude/projects/-Users-justinledwein-Documents-claude-projects-Niewdel-hd-app/memory/MEMORY.md`
- Create: a new session memory file

- [ ] **Step 1: Add session entry**

In `MEMORY.md`, under `## Session History`, add:
```
- [2026-04-20 Kyle handoff readiness — full sweep](session_2026_04_20.md)
```

- [ ] **Step 2: Create the session memory file**

Create `/Users/justinledwein/.claude/projects/-Users-justinledwein-Documents-claude-projects-Niewdel-hd-app/memory/session_2026_04_20.md`:

```markdown
---
name: 2026-04-20 Kyle handoff readiness
description: Full-sweep session preparing the HD app for CEO Kyle Harrison's first live day on 2026-04-21.
type: project
---

Prepared HD platform for CEO handoff. Five commits shipped:

1. WS1 blockers — console.log removed, admin nav visibility fix
   (data-dev-hidden → data-admin-hidden), Users/Roadmap/Activity/
   Archived tabs + All Bug Reports cards marked data-dev-hidden,
   Roadmap promoted to standalone dev-only panel, SECRET_KEY
   startup guard, ZeroDivision guard on job cost margin, stale
   "Work order not found" state fix, weather fetch 5s timeout +
   error state.
2. WS3 backend hardening — closed H1/H3/H4/H6/H7/H8. _safe_error
   helper, _sb_eq query-param helper, _owns_or_admin ownership
   guard on 8 routes, explicit CORS for Railway domain,
   /send-email rate limit + audit log. Created hd_email_log
   table. Backfilled null created_by to estimates@hdgrading.com
   on proposals, change_orders, clients, hd_tasks, hd_reminders.
   H2 (ICS token) and H5 (magic bytes) waived.
3. WS2 silent-failure hardening — new _safeFetch wrapper, all
   write-path handlers (save/delete for bugs, reminders, clients,
   subs, tasks, quotes, change orders, company info) migrated to
   try/catch with error toast and modal stays open on failure.
4. WS4 per-panel polish + WS5 doc generator hardening — empty
   states, lock indicator on Build Proposal, Restore Defaults
   button for Material Prices, Kanban scroll affordance,
   explicit toast on clock-in/out null entry, proposal PDF
   description truncation, CO numeric guard.
5. Runbook + housekeeping — docs/kyle-handoff.md with Kyle's
   temporary password, CLAUDE.md updated with new role model
   and helpers.

Kyle's account: kharrison@hdgrading.com, role=admin, id=12.
Justin remains dev, id=1.

Specs: docs/superpowers/specs/2026-04-20-kyle-handoff-readiness-design.md
Plan:  docs/superpowers/plans/2026-04-20-kyle-handoff-readiness-plan.md
```

- [ ] **Step 3: Verify**

Read both files. Confirm they reference each other and the spec/plan paths.

---

### Task 45: Final smoke test

- [ ] **Step 1: Dev walk-through**

Log in as `justin@hdgrading.com`. In this order, touch:
- Dashboard — confirm no console errors, weather renders or shows "unavailable."
- Projects → Pipeline → List → Bid Calendar.
- Build Proposal — create a new one, add items, save.
- Open the saved proposal, edit, delete.
- Contacts → clients → subs → create/edit/delete a test record.
- Schedule → create a work order → clock in → clock out → delete.
- Reports → open each report category.
- Settings → every tab, including Material Prices (click Restore Defaults and cancel the confirm).
- Admin → Company, Users, Activity, Archived (all visible as dev).
- Standalone Roadmap — visible in nav.
- Bugs panel — both submit form and All Bug Reports list visible.
- Tasks — create/complete a task.

Open DevTools Console before starting. Expected: zero errors, zero log lines from HD code.

- [ ] **Step 2: Admin (Kyle) walk-through**

Log out. Log in as `kharrison@hdgrading.com`.

Touch:
- Dashboard → Projects → Build Proposal → Contacts → Schedule → Reports → Settings → Admin (should show only Company tab).
- Bugs panel — submit form visible, All Bug Reports card NOT visible.
- Roadmap nav entry NOT in sidebar.

DevTools Console. Expected: zero errors, zero log lines.

- [ ] **Step 3: Write-path failure test**

As admin, open a client record. Edit a field. Disconnect wifi. Click Save. Expected: toast shows error message, modal stays open.

Reconnect wifi. Click Save again. Expected: toast shows success, modal closes.

- [ ] **Step 4: Delete-path test**

As admin, delete a test reminder. Expected: toast confirms, reminder disappears.

---

### Task 46: Commit Phase 5

- [ ] **Step 1: Stage**

```bash
git add CLAUDE.md docs/kyle-handoff.md
```

Do NOT stage `/tmp/kyle-password.txt` (temp file, outside repo).

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
Phase 5: runbook + housekeeping for Kyle handoff

- docs/kyle-handoff.md runbook: login URL, Kyle's temporary
  password, framing of the eval, known polish-pending items,
  bug-reporting flow, escalation path.
- CLAUDE.md: documented new role visibility model
  (admin vs dev split), new backend helpers (_safe_error,
  _sb_eq, _owns_or_admin), new frontend helper (_safeFetch),
  Roadmap promoted to standalone, H-item status updates.
- Memory: session_2026_04_20.md session summary.

Ship done. Kyle starts live on 2026-04-21.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin main
```

- [ ] **Step 3: Final Railway verify**

Wait 60s. `curl -s https://web-production-e19b3.up.railway.app/auth/check` — JSON, not 500. Log in as both users one more time, confirm no regressions from the final commit.

- [ ] **Step 4: Deliver runbook to Kyle**

Either (a) text Kyle the URL + paste the contents of `docs/kyle-handoff.md`, or (b) hand him the markdown file directly. The password is in the runbook — do NOT send it separately in plaintext over an unencrypted channel.

- [ ] **Step 5: Clean up temp password file**

```bash
rm /tmp/kyle-password.txt
```

---

## Success Criteria — Exit Checklist

Before calling this done, confirm all of these:

- [ ] Phase 1 commit pushed and smoke-tested on Railway.
- [ ] Phase 2 commit pushed. `/auth/check` returns JSON, not 500.
- [ ] Phase 3 commit pushed. Write-path failure test passes (toast + modal stays open).
- [ ] Phase 4 commit pushed. PDF smoke test passes for realistic + stripped payloads.
- [ ] Phase 5 commit pushed. Both users can log in. Admin sees no dev-only surfaces.
- [ ] No console errors in DevTools during either full walkthrough.
- [ ] `docs/kyle-handoff.md` delivered to Kyle.
- [ ] `/tmp/kyle-password.txt` deleted.
- [ ] CLAUDE.md and MEMORY.md reflect the final state.

---

## Notes for the Executor

1. **When in doubt about a class name, id, or line number,** grep first. The codebase has moved since the spec was written; any citation here is best-effort. Verify before editing.

2. **Commit message template:** each phase commit has its body already drafted in the task. Paste verbatim unless a task genuinely expanded — then edit.

3. **If the SECRET_KEY guard (Task 7) rejects Railway boot**, the `SECRET_KEY` env var is missing on Railway. Set it in the Railway dashboard before retrying the Phase 1 push.

4. **If a migration SQL fails** (Task 13 or 22), check whether the column exists. Drop the failing `UPDATE` line and re-run; document the skipped table in a comment in the migration file.

5. **If a grep in a later task returns a different line number** than this plan cites, trust the grep, not the plan. The plan was written against `index.html` at ~995KB and `app.py` at ~117KB. Edits in earlier phases shift line numbers.

6. **If any handler migrated to `_safeFetch` already had careful error handling,** preserve that behavior. `_safeFetch` is an improvement, not a replacement for thoughtful UX.

7. **Do not skip Phase 5 smoke tests.** The value of this plan is proven at smoke, not at commit.
