-- Rollback of 2026-04-16-rls-lockdown.sql
-- Re-disables RLS and restores grants to anon/authenticated.

alter table hd_users disable row level security;
alter table proposals disable row level security;
alter table clients disable row level security;
alter table pipeline_stages disable row level security;
alter table hd_access_log disable row level security;
alter table hd_settings disable row level security;
alter table hd_notifications disable row level security;
alter table hd_leads disable row level security;
alter table hd_reminders disable row level security;
alter table hd_tasks disable row level security;
alter table hd_time_entries disable row level security;
alter table change_orders disable row level security;
alter table hd_feedback disable row level security;
alter table hd_bug_reports disable row level security;
alter table hd_roadmap disable row level security;
alter table hd_login_attempts disable row level security;
alter table hd_2fa_codes disable row level security;
alter table hd_password_resets disable row level security;

-- Restore Supabase default grants
grant all on
  hd_users, proposals, clients, pipeline_stages, hd_access_log,
  hd_settings, hd_notifications, hd_leads, hd_reminders, hd_tasks,
  hd_time_entries, change_orders, hd_feedback, hd_bug_reports, hd_roadmap,
  hd_login_attempts, hd_2fa_codes, hd_password_resets
to anon, authenticated;
