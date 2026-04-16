# Site Sweep — Security & Quality Findings (2026-04-16)

Full pass of `app.py` (2466 lines), `index.html` (16,161 lines), Supabase config, and public routes. Only items outside the main auth/2FA/RLS plan are listed here.

---

## Fixed this pass (staged locally, not pushed)

| # | Severity | What | Where | Fix |
|---|---|---|---|---|
| F1 | **High** | Public `/proposal/view` returned every column including `archived`, `archived_at`, `stage_id`, `created_by`, `approved_*`, internal `snap.activity_log`, etc. | `app.py:1928` | Rewrote with explicit field whitelist + nested-snap key stripping. |
| F2 | **High** | `/proposal/approve` could be replayed infinitely with a leaked token — each call appended to the activity log and fired off a notification to the owner. | `app.py:1950` | Reject when `snap.approved_by` or `snap.approved_at` is already set → 409. Added per-IP rate limit (10/10min) + length caps on `approver_name` (120) and `comment` (2000). |
| F3 | **Medium** | Public `/leads/submit` had no rate limit and no field length caps — anyone on the internet could spam 10MB descriptions or thousands of fake leads. | `app.py:2066` | Added per-IP rate limit (10/10min) and hard caps on every text field. |
| F4 | **Medium** | Error responses in public routes leaked `str(e)` (stack/DB details) to unauthenticated callers. | `app.py:public_proposal_approve` | Log internally; return generic message. Same pattern should be applied to other public routes in follow-up. |
| F5 | **Low** | Cmdk search rendered `item.label` and `item.hint` via `innerHTML` without `esc()`. Labels can contain proposal/client names (user-controlled). | `index.html:4288` | Wrap both in `esc()`. Defensive — no confirmed exploit path. |

---

## Deferred — needs user attention (NOT fixed this pass)

### H1. `/send-email` accepts arbitrary recipient, subject, body from any authenticated user
**Location:** `app.py:996`
**Risk:** Any auth'd user (including future `field` and `user` roles) can send email from `@hdgrading.com` to any address, attach any PDF, with any subject/body. Insider phishing risk; domain reputation risk.
**Fix options:**
- Whitelist `to` against known client emails (look up in `clients` table).
- Log every send to an audit table.
- Restrict to admin/dev role only.
- Rate-limit per-user (e.g. 20/day).
**Recommendation:** ship at least rate-limiting + audit log in the next batch. Whitelist is the right long-term answer.

### H2. ICS feed token is a 16-char hash of `SECRET_KEY`
**Location:** `app.py:1681`
**Risk:** Token is deterministic — rotating `SECRET_KEY` invalidates all calendar subscriptions; token-leak exposes the whole schedule forever. Also a single shared token, so no way to revoke one user's access.
**Fix:** generate a random per-user token stored in `hd_users.ics_token`, rotate on password change. Low urgency.

### H3. Supabase PostgREST query parameter injection (minor)
**Location:** every `f'?column=eq.{value}'` in `app.py` (40+ occurrences)
**Risk:** PostgREST parses extra `&` / `?` characters; a value like `justin&role=eq.admin` could reshape the query. Most values come from trusted sources (session, integer route params), so exposure is small. The newly-added domain-validated email (Batch 1) further narrows the attack surface.
**Fix:** centralize URL building via `urllib.parse.quote()` helper. Follow-up PR.

### H4. `/quotes/delete`, `/projects/update`, `/change-orders/delete` — no ownership check
**Location:** multiple
**Risk:** Any authenticated user (incl. field users) can delete any proposal/project/CO. Currently mitigated by role gates on the UI, not the backend.
**Fix:** add `created_by == session.username OR role in ('admin','dev')` guards. Medium effort; defer post-RLS.

### H5. File upload relies on extension only
**Location:** `app.py:1072`, `app.py:1160`
**Risk:** Renamed `.exe → .png` uploads pass the check. Served as static assets, so no execution risk, but clients downloading could be tricked. Low.
**Fix:** server-side magic-byte sniffing (`python-magic`). Low urgency.

### H6. `SECRET_KEY` is read from env, but default fallback is hardcoded dev key
**Location:** `app.py:17`
**Risk:** If Railway loses the env var in a config change, sessions silently become forgeable.
**Fix:** refuse to start if `SECRET_KEY` is the default or empty. One-line guard in Batch 1.

### H7. No CORS config
**Location:** global
**Risk:** Default Flask allows any origin to POST. CSRF (Batch 2) will block the dangerous subset, but setting an explicit `Access-Control-Allow-Origin: <hd domain>` is cleaner.
**Fix:** add Flask-CORS or manual headers in `set_security_headers`. Low effort.

### H8. Error messages leak details across many authed routes
**Location:** ~30 places in `app.py` using `'error': str(e)`
**Risk:** Authenticated users see internal errors. Lower risk than public routes but still not production-grade.
**Fix:** introduce `_internal_error(e, context)` helper that logs + returns generic text. Follow-up pass.

---

## UI/UX findings

### UX1. Single `console.log` leftover
- `index.html:11165` — `console.log('[HD] Loaded '+clients.length+' clients for autocomplete');`
- Benign but noisy. Safe to remove.

### UX2. 357 `innerHTML` assignments throughout `index.html`
- Most wrap user data in `esc()` (verified at `index.html:4702`). A spot-check found the fix in F5 above; the rest appear correct.
- Long-term: incremental move to DOM API. Not for today.

### UX3. Inconsistent request timeouts
- `http.get`/`http.post` timeouts vary from 2s → 30s across similar operations.
- Impact: slow Supabase requests can stall user-facing panels (15s timeouts on `boot/data` block the dashboard).
- Fix: standardize (`10s` default, `30s` for uploads), move to a wrapper. Follow-up.

### UX4. Mobile viewport — no horizontal overflow audit
- Spec planned in Batch 5 (a11y sweep). Would need browser testing on a real 360px viewport.

### UX5. Login page already has strong a11y foundation
- `skip-link` present (`index.html:1380`), `sr-only` labels on both inputs, `aria-label` on toggle, `aria-live` regions on error fields, `aria-pressed` on show-password toggle. This is the best-styled screen in the app.

### UX6. Admin nav visibility depends on fresh role
- As discussed: user's stale session cookie is why the UI still shows "Administrator." One login cycle fixes it. Already on shopping list.

---

## Programmatic errors / dead code found

- `app.py:148` returned `password_hint` on failed login — **already addressed** in the staged Batch 1 `/auth/login` rewrite.
- `app.py:1310` / `1394` / `1402` — `/setup/*` routes. One-shot migration helpers. Consider deleting or guarding with a feature flag post-launch. Not urgent.
- `app.py:1825` — `/feedback/list` gates with `@require_auth`, but data includes all feedback including potentially private messages. Consider gating to `@require_admin`.
- `index.html:4705` — explicit "Bulk delete/select removed per user request" stub. Dead code, two functions returning empty divs. Could be removed, low priority.

---

## Summary

- **4 commits on top of `origin/main`, nothing pushed yet.** Everything is reversible.
- **5 security fixes applied** (F1–F5). All are additive and scoped; smoke-test impact is limited to public proposal sharing + lead form + cmdk palette.
- **8 further hardening items deferred** to post-shower batches (H1–H8) with notes on fix direction and urgency.
- Auth/2FA/RLS plan from earlier in the session remains unchanged and is the right next move.

Ready to push whenever you are.
