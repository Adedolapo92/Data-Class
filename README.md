# Automated Job Search Pipeline

Scrapes Greenhouse, Lever, LinkedIn, and Workday boards daily, filters and scores roles against your background, saves results to a dated markdown file, and emails you roles scoring 7+.

---

## Quick Start

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Edit config.yaml
#    - Add company slugs to companies.greenhouse / companies.lever
#    - Fill in email.username, email.password, email.to_addr
#    - Adjust keywords, domains, locations as needed

# 4. Run once
python main.py

# 5. Run in scheduler mode (runs now + every day at 08:00)
python main.py --schedule

# 6. Dry run (no files written, no email sent — good for testing)
python main.py --dry-run
```

Results land in `results/jobs_YYYY-MM-DD.md`. Seen job IDs are tracked in `seen_jobs.json` so the same role never repeats.

---

## Config Reference (`config.yaml`)

| Section | Key | Purpose |
|---|---|---|
| `companies.greenhouse` | list of slugs | Company slugs as they appear in the Greenhouse URL |
| `companies.lever` | list of slugs | Company slugs as they appear in the Lever URL |
| `companies.workday` | list of `{name, tenant, site_id}` | Workday board details |
| `linkedin_searches.keywords` | list | Keyword phrases sent to LinkedIn search |
| `linkedin_searches.locations` | list | LinkedIn location strings |
| `keywords.title_include` | list | Roles must match at least one of these (case-insensitive) |
| `keywords.title_exclude` | list | Roles matching any of these are dropped immediately |
| `keywords.background` | list | Your background keywords — used for scoring |
| `domains.high_fit` | list | Boosts score when found in title/description |
| `domains.low_fit` | list | Penalises score when found |
| `locations.preferred` | list | Strings for Remote / Austin — no flag added |
| `locations.flag_relocation` | list | NYC, SF, Seattle — included but flagged |
| `compensation.minimum_max_salary` | int | Roles where the listed max is below this are excluded |
| `email.smtp_host/port` | string/int | SMTP server details |
| `email.username` / `email.password` | string | SMTP credentials (use Gmail App Passwords) |
| `email.to_addr` | string | Where the digest is sent |
| `email.min_score_to_email` | int | Only roles ≥ this score appear in the email |
| `output.results_dir` | path | Where markdown files are saved |
| `output.seen_jobs_file` | path | JSON file tracking seen job IDs |

---

## Scoring Rubric

| Factor | Points |
|---|---|
| Base | 5 |
| Each preferred domain matched in title/description (max 3) | +1 each |
| 3+ background keywords in description | +1 |
| Senior / Staff / Principal / Group / Lead in title | +1 |
| Each deprioritised domain matched (max 2) | −1 each |

Score is clamped to **1–10**. Roles scoring **7+** are emailed.

---

## Setting Up the Daily Schedule

### macOS / Linux — cron

```bash
# Open your crontab
crontab -e

# Add this line (adjust paths to match your setup):
0 8 * * * /path/to/.venv/bin/python /path/to/Data-Class/main.py >> /path/to/Data-Class/cron.log 2>&1
```

Verify it's registered:
```bash
crontab -l
```

### Windows — Task Scheduler

1. Open **Task Scheduler** → *Create Basic Task*
2. **Trigger:** Daily, at 8:00 AM
3. **Action:** Start a program
   - Program: `C:\path\to\.venv\Scripts\python.exe`
   - Arguments: `C:\path\to\Data-Class\main.py`
   - Start in: `C:\path\to\Data-Class`
4. Check *Run whether user is logged on or not* and *Run with highest privileges*

Alternatively you can use `main.py --schedule` and keep the terminal open (or run it as a background service with `nohup python main.py --schedule &` on Linux).

---

## Gmail App Password Setup

Gmail requires an **App Password** instead of your regular password when 2FA is enabled (recommended):

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Under "How you sign in to Google" → *2-Step Verification* → enable it
3. Search for "App passwords" → create one for "Mail"
4. Copy the 16-character password into `config.yaml` → `email.password`

---

## Project Structure

```
Data-Class/
├── config.yaml              ← all settings live here
├── main.py                  ← entry point + scheduler
├── requirements.txt
├── seen_jobs.json           ← auto-created; tracks seen job IDs
├── results/                 ← auto-created; dated markdown files
│   └── jobs_2026-04-28.md
└── job_search/
    ├── pipeline.py          ← orchestrates scrape → filter → score → output
    ├── filters.py           ← title / location / salary filtering
    ├── scorer.py            ← fit score (1-10) + one-line note
    ├── tracker.py           ← seen-jobs deduplication
    ├── output.py            ← markdown writer
    ├── email_digest.py      ← SMTP email sender
    └── scrapers/
        ├── greenhouse.py
        ├── lever.py
        ├── linkedin.py
        └── workday.py
```
