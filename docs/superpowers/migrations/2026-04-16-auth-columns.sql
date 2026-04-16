-- 2026-04-16: Auth hardening columns + support tables
-- Applies new columns for lockout/rehash tracking and tables for 2FA + resets + login attempts.
-- Idempotent: safe to re-run.

-- hd_users: lockout + rehash tracking
alter table hd_users add column if not exists failed_login_count int not null default 0;
alter table hd_users add column if not exists locked_until timestamptz;
alter table hd_users add column if not exists last_login_at timestamptz;
alter table hd_users add column if not exists password_updated_at timestamptz;

-- Append-only log of login attempts for forensics
create table if not exists hd_login_attempts (
  id bigserial primary key,
  identifier text not null,
  ip_address text,
  success boolean not null,
  attempted_at timestamptz default now()
);
create index if not exists idx_hd_login_attempts_id on hd_login_attempts(identifier, attempted_at desc);

-- 2FA codes (hashed, short-lived, single-use)
create table if not exists hd_2fa_codes (
  id bigserial primary key,
  user_id bigint not null references hd_users(id) on delete cascade,
  code_hash text not null,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  ip_address text,
  created_at timestamptz default now()
);
create index if not exists idx_hd_2fa_codes_user on hd_2fa_codes(user_id, expires_at desc);

-- Password reset tokens (signed body + DB-tracked consumption)
create table if not exists hd_password_resets (
  id bigserial primary key,
  user_id bigint not null references hd_users(id) on delete cascade,
  token_hash text not null unique,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  ip_address text,
  created_at timestamptz default now()
);
create index if not exists idx_hd_password_resets_token on hd_password_resets(token_hash);
