-- Add server-side tracking of "welcome modal seen" per account.
-- Run this in Supabase SQL Editor. Idempotent.

ALTER TABLE hd_users ADD COLUMN IF NOT EXISTS welcome_seen_at TIMESTAMPTZ;

-- Backfill: mark Justin (id=1) as seen so he doesn't get the welcome again
-- on next login. Kyle (id=12) and any future user start as NULL → they'll
-- see the welcome modal once on their first login per account.
UPDATE hd_users SET welcome_seen_at = NOW() WHERE id = 1;
