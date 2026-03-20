# HD Hauling & Grading — Quote Tool

Full-stack asphalt quoting app. Generates branded PDFs, connects to Notion, PIN-protected.

---

## Deploy to Railway (15 minutes)

### Step 1 — GitHub
1. Go to **github.com** → Sign up or log in
2. Click **+** (top right) → **New repository**
3. Name it `hd-quote-tool` → **Create repository**
4. Click **Add file** → **Upload files**
5. Drag and drop everything from this unzipped folder → **Commit changes**

### Step 2 — Railway
1. Go to **railway.app** → **Start a New Project**
2. Click **Deploy from GitHub repo** → connect your GitHub → select `hd-quote-tool`
3. Railway detects Python and deploys automatically (2–3 minutes)
4. Go to **Settings** → **Domains** → **Generate Domain**

### Step 3 — Set Environment Variables
In Railway, go to your project → **Variables** tab → add these:

| Variable | Value | Notes |
|---|---|---|
| `APP_PIN` | Your chosen PIN | e.g. `4821` — this is what you type to log in |
| `SECRET_KEY` | Any random string | e.g. `hd-hauling-secret-2025-xyz` |
| `NOTION_KEY` | Your Notion API key | Already set as default in code |
| `NOTION_PIPELINE` | Estimating Pipeline DB ID | Already set as default |
| `NOTION_CLIENTS` | Client Contacts DB ID | Already set as default |

> **Important:** Setting `APP_PIN` and `SECRET_KEY` in Railway environment variables overrides the defaults in the code. Do this — don't leave the default PIN.

### Step 4 — Done
Open your Railway URL. Enter your PIN. Start quoting.

---

## Local Development

```bash
pip install flask reportlab pillow requests gunicorn

# Set environment variables (Mac/Linux)
export APP_PIN=1234
export SECRET_KEY=local-dev-key

python app.py
# Open http://localhost:5000
```

---

## File Structure

```
hd-quote-tool/
├── app.py                  Flask server (auth, PDF endpoint, Notion proxy)
├── generate_proposal.py    PDF generator
├── requirements.txt        Python dependencies
├── Procfile               Railway/Heroku process config
├── runtime.txt            Python version pin
├── assets/
│   └── hd_logo.png        HD logo (baked into PDFs)
└── static/
    └── index.html         Full quote tool frontend
```

---

## Environment Variables Reference

| Variable | Description | Default (change in Railway) |
|---|---|---|
| `APP_PIN` | Login PIN for the app | `2025` |
| `SECRET_KEY` | Flask session signing key | `hd-hauling-dev-key-change-in-prod` |
| `NOTION_KEY` | Notion integration API key | Pre-loaded |
| `NOTION_PIPELINE` | Estimating Pipeline database ID | Pre-loaded |
| `NOTION_CLIENTS` | Client Contacts database ID | Pre-loaded |
| `PORT` | Port (set automatically by Railway) | `5000` |

---

## Notion Database Requirements

**Estimating Pipeline** needs these properties:
- `Name` (title)
- `Client` (text)
- `Address` (text)
- `Date` (date)
- `Status` (select — must include **Quoted** as an option)
- `Bid Total` (number)
- `Total SF` (number)

**Client Contacts** is read-only — used for the client autocomplete dropdown when building a quote.
