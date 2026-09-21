# 🔗 CA ANZ Broken Link Checker

> Automated monthly crawl of all CA ANZ domains, checking for broken links,
> server errors, and redirect issues. Emails a formatted report automatically.
>
> 📁 Repository: https://github.com/jjhunjhunwala-arch/caanz-url-checker

---

## 📋 What It Checks

| Domain | Included? |
|--------|-----------|
| `www.charteredaccountantsanz.com` | ✅ Crawled |
| `acuity.charteredaccountantsanz.com` | ✅ Crawled |
| `members.charteredaccountantsanz.com` | ✅ Crawled (status check only — no login needed) |
| `store.charteredaccountantsanz.com` | ✅ Crawled |
| External links (LinkedIn, govt sites, etc.) | ✅ Checked (not crawled) |

| Error Type | Flagged? |
|------------|----------|
| 🔴 404 Not Found | ✅ Yes |
| 🔴 Other 4xx Client Errors | ✅ Yes |
| 🟠 5xx Server Errors | ✅ Yes |
| 🟡 Redirect Chains & Loops | ✅ Yes |
| ⏱️ Timeouts & Connection Errors | ✅ Yes |

---

## 🖱️ How to Run (Content Managers — No Tech Knowledge Needed)

### Option A — Automatic Monthly Run
Nothing to do! The checker runs automatically on the **28th of every month at 8am AEST**
and emails you the report. ✅

### Option B — Run Manually (on demand)

1. Go to: https://github.com/jjhunjhunwala-arch/caanz-url-checker
2. Click the **"Actions"** tab at the top
3. Click **"🔗 CA ANZ Monthly Link Checker"** in the left panel
4. Click the **"Run workflow"** dropdown button (top right)
5. Click the green **"Run workflow"** to confirm
6. ☕ Wait approximately **60–90 minutes** for the crawl to finish
7. Check your **email** for the report

> 💡 You can also watch the progress live by clicking on the running job.

### Option C — Download the Report from GitHub (if email fails)

1. Go to **Actions tab** → click on the latest completed run
2. Scroll to the bottom → **Artifacts** section
3. Click **"link-report-..."** to download the Excel file

---

## 📊 Excel Report Structure

The report has **4 tabs**:

| Tab | What's in it |
|-----|-------------|
| 📊 **Summary** | High-level counts — total URLs, issues by type |
| 🔴 **Broken Links** | Every broken URL, the page it was found on, status code, error type |
| 🟡 **Redirect Chains** | All pages with redirect hops, with the full chain shown |
| 📋 **All Results** | Complete log of every single URL checked (internal + external) |

### Colour Coding
| Colour | Meaning |
|--------|---------|
| 🔴 Red | 4xx errors (404, 403, etc.) |
| 🟠 Orange | 5xx server errors |
| 🟡 Yellow | Redirect issues / warnings |
| 🟢 Green | Working correctly |

---

## ⚙️ Setup Status

### ✅ Already Completed
- [x] GitHub repository created: `jjhunjhunwala-arch/caanz-url-checker`
- [x] `link_checker.py` committed to main branch
- [x] `.github/workflows/link-checker.yml` committed to main branch
- [x] GitHub Actions enabled
- [x] All 5 repository secrets configured (see below)

### 🔐 GitHub Secrets Configured
Go to: **Settings → Secrets and variables → Actions** to view or update.

| Secret Name | What it does | Status |
|-------------|-------------|--------|
| `EMAIL_FROM` | Gmail address reports are sent FROM | ✅ Set |
| `EMAIL_TO` | Email address where reports are delivered | ✅ Set |
| `EMAIL_PASSWORD` | Gmail App Password (not your regular Gmail password) | ✅ Set |
| `SMTP_SERVER` | `smtp.gmail.com` | ✅ Set |
| `SMTP_PORT` | `587` | ✅ Set |

> **Note:** Currently using a personal Gmail account for sending and receiving reports.
> To switch to a dedicated mailbox in future, simply update `EMAIL_FROM`, `EMAIL_TO`
> and `EMAIL_PASSWORD` secrets — no code changes needed.

### 🔑 How to Regenerate the Gmail App Password (if needed)
1. Go to https://myaccount.google.com/apppasswords
2. Revoke the old one named `CAANZ Link Checker`
3. Create a new one → copy the 16-character code
4. Go to repo → **Settings → Secrets → Actions** → click ✏️ next to `EMAIL_PASSWORD` → paste new value

---

## 🔧 Configuration (Advanced)

Edit the top of `link_checker.py` to adjust settings:

```python
MAX_PAGES          = 7000   # Safety cap on internal pages crawled
CRAWL_DELAY        = 0.3    # Seconds between requests (lower = faster but riskier)
REQUEST_TIMEOUT    = 20     # Seconds before abandoning a URL
MAX_REDIRECT_DEPTH = 5      # Flag chains longer than this
CHECK_WORKERS      = 15     # Parallel threads for external links
```

### To add more domains in the future:
```python
SEED_DOMAINS = [
    "https://www.charteredaccountantsanz.com",
    "https://acuity.charteredaccountantsanz.com",
    "https://members.charteredaccountantsanz.com",
    "https://store.charteredaccountantsanz.com",
    "https://yournewdomain.charteredaccountantsanz.com",  # ← Add here
]
```

### To add more email recipients:
Update the `EMAIL_TO` secret to a comma-separated list:
```
juhi.king@caanz.com, morgan.lindqvist@caanz.com, webcontent@caanz.com
```

---

## 🛠️ Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Email not received | Gmail blocking or App Password expired | Regenerate App Password and update `EMAIL_PASSWORD` secret |
| Run taking > 2 hours | Site is very large | Increase `timeout-minutes` in the workflow file |
| Lots of 403 errors on external links | Bot protection on external sites | Expected — LinkedIn, Cloudflare sites often block bots |
| Members pages showing errors | Login-protected pages return 401/403 | Expected — filter by domain column in Excel |
| Workflow doesn't appear in Actions | Actions not enabled | Go to Actions tab and enable |
| `ModuleNotFoundError` | Dependency issue | Contact tech team to update the `pip install` step |

---

## 📅 Run Schedule

| Run Type | When | Who triggers |
|----------|------|-------------|
| Automatic | 28th of every month, 8am AEST | GitHub Actions (nobody — fully automated) |
| Manual | Any time | Click "Run workflow" in Actions tab |
| Reports kept for | 90 days | Auto-deleted after by GitHub |

---

## 👥 Ownership

| Role | Person |
|------|--------|
| Tool Owner / Product Manager | Juhi King |
| Technical Setup & Maintenance | Morgan Lindqvist |
| Report Recipients | Juhi King (expand via `EMAIL_TO` secret when ready) |
