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
ALTER TABLE hd_email_log DISABLE ROW LEVEL SECURITY;
