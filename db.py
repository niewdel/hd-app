import sqlite3, os, json

# Railway persistent volume at /data, fallback to app dir
DB_DIR  = '/data' if os.path.isdir('/data') else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'hd_quotes.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS quotes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT    NOT NULL,
                client    TEXT    DEFAULT '',
                date      TEXT    DEFAULT '',
                total     REAL    DEFAULT 0,
                snap      TEXT    NOT NULL,
                created_at TEXT   DEFAULT (datetime('now'))
            )
        ''')
        conn.commit()

def save_quote(name, client, date, total, snap):
    with get_conn() as conn:
        cur = conn.execute(
            'INSERT INTO quotes (name, client, date, total, snap) VALUES (?,?,?,?,?)',
            (name, client, date, float(total), snap)
        )
        conn.commit()
        return cur.lastrowid

def list_quotes():
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT id, name, client, date, total, snap, created_at FROM quotes ORDER BY created_at DESC'
        ).fetchall()
        return [dict(r) for r in rows]

def get_quote(qid):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM quotes WHERE id=?', (qid,)).fetchone()
        return dict(row) if row else None

def delete_quote(qid):
    with get_conn() as conn:
        conn.execute('DELETE FROM quotes WHERE id=?', (qid,))
        conn.commit()

# Init on import
init_db()
