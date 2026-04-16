-- 2026-04-16: RLS lockdown on all public tables.
-- Backend uses service_role which bypasses RLS natively — no policies needed.
-- If the anon key leaks, attackers see nothing.

-- Drop pre-existing over-permissive policies
drop policy if exists "Allow all for service key" on hd_bug_reports;
drop policy if exists "Allow all for service key" on hd_roadmap;
drop policy if exists "Allow authenticated access" on content_digests;

-- Enable RLS on every public table
alter table hd_users enable row level security;
alter table proposals enable row level security;
alter table clients enable row level security;
alter table pipeline_stages enable row level security;
alter table hd_access_log enable row level security;
alter table hd_settings enable row level security;
alter table hd_notifications enable row level security;
alter table hd_leads enable row level security;
alter table hd_reminders enable row level security;
alter table hd_tasks enable row level security;
alter table hd_time_entries enable row level security;
alter table change_orders enable row level security;
alter table hd_feedback enable row level security;
alter table hd_bug_reports enable row level security;
alter table hd_roadmap enable row level security;

-- New auth tables should be locked down too
alter table hd_login_attempts enable row level security;
alter table hd_2fa_codes enable row level security;
alter table hd_password_resets enable row level security;

-- Revoke every grant from public-facing roles; service_role retains implicit bypass
revoke all on hd_users from anon, authenticated;
revoke all on proposals from anon, authenticated;
revoke all on clients from anon, authenticated;
revoke all on pipeline_stages from anon, authenticated;
revoke all on hd_access_log from anon, authenticated;
revoke all on hd_settings from anon, authenticated;
revoke all on hd_notifications from anon, authenticated;
revoke all on hd_leads from anon, authenticated;
revoke all on hd_reminders from anon, authenticated;
revoke all on hd_tasks from anon, authenticated;
revoke all on hd_time_entries from anon, authenticated;
revoke all on change_orders from anon, authenticated;
revoke all on hd_feedback from anon, authenticated;
revoke all on hd_bug_reports from anon, authenticated;
revoke all on hd_roadmap from anon, authenticated;
revoke all on hd_login_attempts from anon, authenticated;
revoke all on hd_2fa_codes from anon, authenticated;
revoke all on hd_password_resets from anon, authenticated;
