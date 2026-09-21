# 🔗 CA ANZ Broken Link Checker

> Automated monthly crawl of all CA ANZ domains, checking for broken links,
> server errors, and redirect issues. Emails a formatted report automatically.

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

1. Go to your GitHub repository
2. Click the **"Actions"** tab at the top
3. Click **"🔗 CA ANZ Monthly Link Checker"** in the left panel
4. Click the **"Run workflow"** button (top right, blue button)
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

## ⚙️ One-Time Setup (Technical Team — Morgan)

### Step 1 — Create GitHub Repository

```bash
# Create a new private repo on GitHub (e.g., caanz-link-checker)
# Then add these two files:
#   link_checker.py
#   .github/workflows/link-checker.yml
```

### Step 2 — Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 5 secrets:

| Secret Name | Example Value | Notes |
|-------------|---------------|-------|
| `EMAIL_FROM` | `caanz.linkchecks@gmail.com` | Gmail address to SEND from |
| `EMAIL_TO` | `juhi.king@charteredaccountantsanz.com` | Where reports are emailed |
| `EMAIL_PASSWORD` | `abcd efgh ijkl mnop` | Gmail **App Password** (see below) |
| `SMTP_SERVER` | `smtp.gmail.com` | Leave as is for Gmail |
| `SMTP_PORT` | `587` | Leave as is for Gmail |

> **To add more recipients later**: Change `EMAIL_TO` to a comma-separated list,
> or use a distribution group email.

### Step 3 — Gmail App Password Setup

1. Use a dedicated Gmail account (e.g., `caanz.linkchecks@gmail.com`)
2. Enable **2-Step Verification** on that Gmail account
3. Go to: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Create an App Password → select **Mail** + **Other (custom)** → name it "CAANZ Link Checker"
5. Copy the 16-character password → paste it as the `EMAIL_PASSWORD` secret

### Step 4 — Enable GitHub Actions

- Go to the **Actions** tab → click **"I understand my workflows, go ahead and enable them"**
- That's it! First automatic run will happen on the 28th. 🎉

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
| Email not received | Secrets not set, or Gmail blocking | Check secrets; try regenerating App Password |
| Run taking > 2 hours | Site is very large | Increase `timeout-minutes` in the workflow file |
| Lots of 403 errors on external links | Bot protection on external sites | These are expected — LinkedIn, Cloudflare sites often block bots |
| Members pages all showing errors | Expected — login-protected | These are flagged intentionally; filter by domain in Excel |
| Workflow doesn't appear in Actions | Actions not enabled | Go to Actions tab and enable |
| `ModuleNotFoundError` | Dependency issue | Contact tech team to update the `pip install` step |

---

## 📅 Run Schedule

| Run Type | When | Who triggers |
|----------|------|-------------|
| Automatic | 28th of every month, 8am AEST | GitHub Actions (no one) |
| Manual | Any time | Content manager clicks "Run workflow" |
| Reports kept for | 90 days | Auto-deleted after |

---

## 👥 Ownership

| Role | Person |
|------|--------|
| Tool Owner / Product Manager | Juhi King |
| Technical Setup & Maintenance | Morgan Lindqvist |
| Report Recipients | Juhi King (expand as needed) |
