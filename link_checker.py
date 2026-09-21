#!/usr/bin/env python3
"""
CA ANZ Broken Link Checker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monthly crawl of all CA ANZ domains checking for:
  - 4xx errors  (including 404 Not Found)
  - 5xx server errors
  - Redirect chains and loops

Generates an Excel report + sends an email digest.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import time
import logging
import smtplib
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# ─────────────────────────────────────────────────────────────────
#  CONFIGURATION  (edit here or override via environment variables)
# ─────────────────────────────────────────────────────────────────
SEED_DOMAINS = [
    "https://www.charteredaccountantsanz.com",
    "https://acuity.charteredaccountantsanz.com",
    "https://members.charteredaccountantsanz.com",
    "https://store.charteredaccountantsanz.com",
]

INTERNAL_DOMAIN_PATTERNS = ["charteredaccountantsanz.com"]

MAX_PAGES           = 7000   # Safety cap on internal pages crawled
CRAWL_DELAY         = 0.3    # Seconds between internal page requests (be polite)
REQUEST_TIMEOUT     = 20     # Seconds before a request is abandoned
MAX_REDIRECT_DEPTH  = 5      # Flag redirect chains longer than this
CHECK_WORKERS       = 15     # Parallel threads for external link checking

# Email — set via GitHub Actions secrets (do NOT hardcode credentials here)
EMAIL_FROM      = os.environ.get("EMAIL_FROM", "")
EMAIL_TO        = os.environ.get("EMAIL_TO", "")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
SMTP_SERVER     = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

HEADERS = {
  "User-Agent": USER_AGENT,
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
  "Accept-Language": "en-AU,en;q=0.9",
  "Accept-Encoding": "gzip, deflate, br",
  "Connection": "keep-alive",
  "Upgrade-Insecure-Requests": "1",
}

# ─────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────
def is_internal(url: str) -> bool:
    """Returns True if the URL belongs to any CA ANZ domain."""
    return any(p in urlparse(url).netloc for p in INTERNAL_DOMAIN_PATTERNS)


def normalise(url: str) -> str:
    """Strip fragments and trailing slashes for clean deduplication."""
    return url.split("#")[0].rstrip("/")


def classify_error(status_code: int, redirect_chain: list, error_type_override: str = None) -> str | None:
    """Returns a human-readable error label, or None if the URL is healthy."""
    if error_type_override:
        return error_type_override

    chain = redirect_chain or []

    # Redirect loop detection
    if len(set(chain)) < len(chain):
        return "Redirect Loop"
    if len(chain) > MAX_REDIRECT_DEPTH:
        return f"Redirect Chain Too Long ({len(chain)} hops)"

    if status_code == 404:
        return "404 Not Found"
    if 400 <= status_code < 500:
        return f"4xx Client Error ({status_code})"
    if 500 <= status_code < 600:
        return f"5xx Server Error ({status_code})"

    return None  # Healthy


# ─────────────────────────────────────────────────────────────────
#  URL CHECKER
# ─────────────────────────────────────────────────────────────────
def check_url(session: requests.Session, url: str) -> dict:
    """
    Performs a GET request and returns a result dict with:
      url, status_code, error_type, redirect_chain, final_url, response_time_ms
    """
    result = {
        "url":              url,
        "status_code":      None,
        "error_type":       None,
        "redirect_chain":   [],
        "final_url":        url,
        "response_time_ms": None,
    }

    try:
        t0 = time.time()
        resp = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers=HEADERS,
        )
        result["response_time_ms"] = round((time.time() - t0) * 1000)
        result["status_code"]      = resp.status_code
        result["final_url"]        = resp.url

        if resp.history:
            result["redirect_chain"] = [r.url for r in resp.history] + [resp.url]

        result["error_type"] = classify_error(resp.status_code, result["redirect_chain"])

    except requests.exceptions.TooManyRedirects:
        result["error_type"]  = "Redirect Loop / Too Many Redirects"
        result["status_code"] = 0
    except requests.exceptions.Timeout:
        result["error_type"]  = "Timeout"
        result["status_code"] = 0
    except requests.exceptions.SSLError:
        result["error_type"]  = "SSL Certificate Error"
        result["status_code"] = 0
    except requests.exceptions.ConnectionError:
        result["error_type"]  = "Connection Error (DNS/Network)"
        result["status_code"] = 0
    except Exception as exc:
        result["error_type"]  = f"Unexpected Error: {str(exc)[:80]}"
        result["status_code"] = 0

    return result


# ─────────────────────────────────────────────────────────────────
#  PHASE 1 — CRAWL INTERNAL PAGES
# ─────────────────────────────────────────────────────────────────
def crawl() -> tuple[dict, dict, set]:
    """
    BFS crawl of all internal CA ANZ domains.

    Returns:
      url_to_sources   — dict: found_url → [list of pages it was linked from]
      internal_results — dict: url → check_result  (internal pages only)
      external_links   — set of external URLs found on internal pages
    """
    session          = requests.Session()
    visited          = set()
    queue            = deque(normalise(u) for u in SEED_DOMAINS)
    url_to_sources   = defaultdict(list)
    internal_results = {}
    external_links   = set()
    page_count       = 0

    log.info("Phase 1 — Crawling internal pages...")

    while queue and page_count < MAX_PAGES:
        url = queue.popleft()
        if url in visited:
            continue

        visited.add(url)
        page_count += 1

        log.info(f"  [{page_count}/{MAX_PAGES}] {url}")
        result = check_url(session, url)
        internal_results[url] = result
        time.sleep(CRAWL_DELAY)

        # Only parse HTML for pages that loaded successfully
        if result["status_code"] != 200:
            continue

        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup.find_all("a", href=True):
                href = tag["href"].strip()

                # Skip non-navigational links
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
                    continue

                abs_url = normalise(urljoin(url, href))
                parsed  = urlparse(abs_url)

                if parsed.scheme not in ("http", "https"):
                    continue

                url_to_sources[abs_url].append(url)

                if is_internal(abs_url) and abs_url not in visited:
                    queue.append(abs_url)
                elif not is_internal(abs_url):
                    external_links.add(abs_url)

        except Exception as exc:
            log.warning(f"  Could not parse links on {url}: {exc}")

    log.info(
        f"Phase 1 complete — {page_count} internal pages crawled, "
        f"{len(external_links)} unique external links found."
    )
    return url_to_sources, internal_results, external_links


# ─────────────────────────────────────────────────────────────────
#  PHASE 2 — CHECK EXTERNAL LINKS (parallel)
# ─────────────────────────────────────────────────────────────────
def check_external(external_links: set) -> dict:
    """
    Checks all external URLs in parallel using a thread pool.
    Returns dict: url → check_result
    """
    if not external_links:
        return {}

    log.info(f"Phase 2 — Checking {len(external_links)} external links (parallel, {CHECK_WORKERS} workers)...")
    session  = requests.Session()
    results  = {}
    total    = len(external_links)
    done     = 0

    def _check(url):
        return url, check_url(session, url)

    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as executor:
        futures = {executor.submit(_check, url): url for url in external_links}
        for future in as_completed(futures):
            url, result = future.result()
            results[url] = result
            done += 1
            if done % 200 == 0 or done == total:
                log.info(f"  External: {done}/{total} checked")

    broken_ext = sum(1 for r in results.values() if r["error_type"])
    log.info(f"Phase 2 complete — {broken_ext} external issues found.")
    return results


# ─────────────────────────────────────────────────────────────────
#  PHASE 3 — GENERATE EXCEL REPORT
# ─────────────────────────────────────────────────────────────────
# Colour palette
C_NAVY   = "1F3864"
C_RED    = "FF4C4C"
C_ORANGE = "FF8C00"
C_YELLOW = "FFD966"
C_GREEN  = "C6EFCE"
C_WHITE  = "FFFFFF"
C_LIGHT  = "F2F2F2"

def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)

def _font(color=C_NAVY, bold=False, size=11) -> Font:
    return Font(color=color, bold=bold, size=size)

def _write_header(ws, headers: list, fill_color=C_NAVY):
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.fill = _fill(fill_color)
        cell.font = _font(color=C_WHITE, bold=True)
        cell.alignment = Alignment(wrap_text=False, vertical="center")

def _autofit(ws, max_width=90):
    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(width + 4, max_width)


def generate_excel(
    url_to_sources: dict,
    internal_results: dict,
    external_results: dict,
    path: str,
) -> dict:
    """
    Generates a colour-coded Excel workbook with 4 sheets:
      1. Summary
      2. Broken Links
      3. Redirect Chains
      4. All Results (full log)
    Returns the broken dict for use in the email.
    """
    all_results = {**internal_results, **external_results}
    broken      = {u: r for u, r in all_results.items() if r["error_type"]}
    redirects   = {u: r for u, r in all_results.items() if len(r.get("redirect_chain") or []) > 1}

    # Breakdown counts
    cnt_404      = sum(1 for r in broken.values() if "404"      in (r["error_type"] or ""))
    cnt_4xx      = sum(1 for r in broken.values() if "4xx"      in (r["error_type"] or ""))
    cnt_5xx      = sum(1 for r in broken.values() if "5xx"      in (r["error_type"] or ""))
    cnt_redirect = sum(1 for r in broken.values() if "Redirect" in (r["error_type"] or ""))
    cnt_timeout  = sum(1 for r in broken.values() if "Timeout"  in (r["error_type"] or ""))
    cnt_conn     = sum(1 for r in broken.values() if "Connection" in (r["error_type"] or ""))
    cnt_other    = len(broken) - cnt_404 - cnt_4xx - cnt_5xx - cnt_redirect - cnt_timeout - cnt_conn

    wb = Workbook()

    # ── SHEET 1 : Summary ─────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "📊 Summary"
    ws1.column_dimensions["A"].width = 40
    ws1.column_dimensions["B"].width = 15

    ws1["A1"] = "CA ANZ Monthly Broken Link Report"
    ws1["A1"].font = Font(bold=True, size=16, color=C_NAVY)
    ws1["A2"] = f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M AEST')}"
    ws1["A3"] = f"Domains: {' | '.join(SEED_DOMAINS)}"
    ws1.append([])

    summary_rows = [
        ("Metric",                          "Count",                       C_NAVY,   C_WHITE),
        ("Total URLs Checked",              len(all_results),              C_LIGHT,  C_NAVY),
        ("  ↳ Internal Pages Crawled",      len(internal_results),         C_LIGHT,  C_NAVY),
        ("  ↳ External Links Checked",      len(external_results),         C_LIGHT,  C_NAVY),
        ("✅ Working (no issues)",           len(all_results)-len(broken),  C_GREEN,  C_NAVY),
        ("🔴 Total Issues Found",            len(broken),                   C_RED,    C_WHITE),
        ("   ↳ 404 Not Found",              cnt_404,                       C_LIGHT,  C_NAVY),
        ("   ↳ Other 4xx Client Errors",    cnt_4xx,                       C_LIGHT,  C_NAVY),
        ("   ↳ 5xx Server Errors",          cnt_5xx,                       C_LIGHT,  C_NAVY),
        ("   ↳ Redirect Issues",            cnt_redirect,                  C_LIGHT,  C_NAVY),
        ("   ↳ Timeouts",                   cnt_timeout,                   C_LIGHT,  C_NAVY),
        ("   ↳ Connection Errors",          cnt_conn,                      C_LIGHT,  C_NAVY),
        ("   ↳ Other Errors",               max(cnt_other, 0),             C_LIGHT,  C_NAVY),
        ("⚠️ Pages with Any Redirect",      len(redirects),                C_YELLOW, C_NAVY),
    ]

    for label, count, bg, fg in summary_rows:
        ws1.append([label, count])
        for cell in ws1[ws1.max_row]:
            cell.fill = _fill(bg)
            cell.font = _font(color=fg, bold=(label in ("Metric", "🔴 Total Issues Found", "✅ Working (no issues)")))

    # ── SHEET 2 : Broken Links ────────────────────────────────────
    ws2 = wb.create_sheet("🔴 Broken Links")
    _write_header(ws2, [
        "Source Page (where link was found)",
        "Broken / Error URL",
        "Link Type",
        "HTTP Status",
        "Error Category",
        "Response Time (ms)",
    ])

    for url, result in sorted(broken.items(), key=lambda x: (x[1]["error_type"] or "", x[0])):
        sources   = url_to_sources.get(url, ["(seed / direct)"])
        link_type = "Internal" if is_internal(url) else "External"
        error     = result["error_type"] or ""

        ws2.append([
            sources[0],
            url,
            link_type,
            result["status_code"],
            error,
            result["response_time_ms"],
        ])

        row_fill = (
            _fill(C_RED)    if ("404" in error or "4xx" in error) else
            _fill(C_ORANGE) if "5xx" in error else
            _fill(C_YELLOW)
        )
        for cell in ws2[ws2.max_row]:
            cell.fill = row_fill

    # ── SHEET 3 : Redirect Chains ─────────────────────────────────
    ws3 = wb.create_sheet("🟡 Redirect Chains")
    _write_header(ws3, ["Source URL", "Hop Count", "Full Redirect Chain", "Final URL", "Issue?"])

    for url, result in sorted(redirects.items(), key=lambda x: -len(x[1].get("redirect_chain") or [])):
        chain    = result.get("redirect_chain") or []
        has_loop = "⚠️ Yes" if result["error_type"] and "Redirect" in result["error_type"] else "No"
        ws3.append([
            url,
            len(chain),
            " → ".join(chain),
            result["final_url"],
            has_loop,
        ])
        if has_loop == "⚠️ Yes":
            for cell in ws3[ws3.max_row]:
                cell.fill = _fill(C_YELLOW)

    # ── SHEET 4 : Full Results Log ────────────────────────────────
    ws4 = wb.create_sheet("📋 All Results")
    _write_header(ws4, [
        "URL",
        "Type",
        "HTTP Status",
        "Result",
        "Final URL",
        "Response Time (ms)",
    ])

    for url, result in sorted(all_results.items()):
        status = result["error_type"] or "✅ OK"
        ws4.append([
            url,
            "Internal" if is_internal(url) else "External",
            result["status_code"],
            status,
            result["final_url"],
            result["response_time_ms"],
        ])
        if result["error_type"]:
            for cell in ws4[ws4.max_row]:
                cell.fill = _fill(C_LIGHT)

    # Autofit all sheets
    for ws in [ws1, ws2, ws3, ws4]:
        _autofit(ws)

    wb.save(path)
    log.info(f"Excel report saved → {path}  ({len(broken)} issues)")
    return broken


# ─────────────────────────────────────────────────────────────────
#  PHASE 4 — EMAIL DIGEST
# ─────────────────────────────────────────────────────────────────
def send_email(report_path: str, all_results: dict, broken: dict):
    """Sends an HTML email digest with the Excel report attached."""
    total        = len(all_results)
    broken_count = len(broken)
    cnt_404      = sum(1 for r in broken.values() if "404"      in (r["error_type"] or ""))
    cnt_5xx      = sum(1 for r in broken.values() if "5xx"      in (r["error_type"] or ""))
    cnt_redirect = sum(1 for r in broken.values() if "Redirect" in (r["error_type"] or ""))
    cnt_timeout  = sum(1 for r in broken.values() if "Timeout"  in (r["error_type"] or ""))

    subject = (
        f"CA ANZ Link Check — {datetime.now().strftime('%B %Y')} — "
        + ("✅ All Clear!" if broken_count == 0 else f"🔴 {broken_count} issues found")
    )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: auto;">

      <div style="background:#1F3864; padding:20px; border-radius:8px 8px 0 0;">
        <h1 style="color:white; margin:0; font-size:20px;">🔗 CA ANZ Monthly Link Check Report</h1>
        <p style="color:#ccc; margin:6px 0 0;">{datetime.now().strftime('%d %B %Y')}</p>
      </div>

      <div style="background:#f9f9f9; padding:20px; border:1px solid #ddd;">
        <p><strong>Domains checked:</strong><br/>
        charteredaccountantsanz.com · acuity · members · store + all external links</p>

        <table border="1" cellpadding="10" cellspacing="0"
               style="border-collapse:collapse; width:100%; margin-top:10px;">
          <tr style="background:#1F3864; color:white;">
            <th align="left">Metric</th>
            <th align="right">Count</th>
          </tr>
          <tr>
            <td>Total URLs Checked</td>
            <td align="right"><strong>{total:,}</strong></td>
          </tr>
          <tr style="background:#C6EFCE;">
            <td>✅ Working (no issues)</td>
            <td align="right"><strong>{total - broken_count:,}</strong></td>
          </tr>
          <tr style="background:#FF4C4C; color:white;">
            <td>🔴 Total Issues Found</td>
            <td align="right"><strong>{broken_count:,}</strong></td>
          </tr>
          <tr style="background:#fff3cd;">
            <td>&nbsp;&nbsp;&nbsp;↳ 404 Not Found</td>
            <td align="right">{cnt_404:,}</td>
          </tr>
          <tr style="background:#fff3cd;">
            <td>&nbsp;&nbsp;&nbsp;↳ 5xx Server Errors</td>
            <td align="right">{cnt_5xx:,}</td>
          </tr>
          <tr style="background:#fff3cd;">
            <td>&nbsp;&nbsp;&nbsp;↳ Redirect Issues</td>
            <td align="right">{cnt_redirect:,}</td>
          </tr>
          <tr style="background:#fff3cd;">
            <td>&nbsp;&nbsp;&nbsp;↳ Timeouts / Connection Errors</td>
            <td align="right">{cnt_timeout:,}</td>
          </tr>
        </table>

        <p style="margin-top:20px;">
          📎 <strong>Full breakdown is attached</strong> as an Excel report with 4 tabs:<br/>
          <em>Summary · Broken Links · Redirect Chains · All Results</em>
        </p>

        <p>You can also download the report from the
          <a href="https://github.com">GitHub Actions Artifacts</a> section
          (link in your repo → Actions → latest run → Artifacts).</p>
      </div>

      <div style="background:#eee; padding:12px; border-radius:0 0 8px 8px; font-size:12px; color:#888;">
        This report is generated automatically each month by the CA ANZ Link Checker (GitHub Actions).<br/>
        To add recipients or change settings, contact your tech team (Morgan Lindqvist).
      </div>

    </body>
    </html>
    """

    msg             = MIMEMultipart()
    msg["From"]     = EMAIL_FROM
    msg["To"]       = EMAIL_TO
    msg["Subject"]  = subject
    msg.attach(MIMEText(html_body, "html"))

    # Attach Excel file
    with open(report_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(report_path)}"',
        )
        msg.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as srv:
        srv.ehlo()
        srv.starttls()
        srv.login(EMAIL_FROM, EMAIL_PASSWORD)
        srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

    log.info(f"Email digest sent → {EMAIL_TO}")


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    log.info("━" * 60)
    log.info("  CA ANZ Broken Link Checker — Starting")
    log.info(f"  Run date: {datetime.now().strftime('%d %B %Y, %H:%M')}")
    log.info("━" * 60)

    # Phase 1 — Crawl internal pages
    url_to_sources, internal_results, external_links = crawl()

    # Phase 2 — Check external links (parallel)
    external_results = check_external(external_links)

    # Phase 3 — Generate Excel report
    all_results  = {**internal_results, **external_results}
    report_name  = f"caanz_link_report_{datetime.now().strftime('%Y_%m')}.xlsx"
    broken       = generate_excel(url_to_sources, internal_results, external_results, report_name)

    # Phase 4 — Send email digest
    if EMAIL_FROM and EMAIL_TO and EMAIL_PASSWORD:
        send_email(report_name, all_results, broken)
    else:
        log.warning("EMAIL_FROM / EMAIL_TO / EMAIL_PASSWORD not set — skipping email.")
        log.info(f"Report saved locally as: {report_name}")

    log.info("━" * 60)
    log.info(f"  Done. {len(broken)} issues found across {len(all_results)} URLs checked.")
    log.info("━" * 60)


if __name__ == "__main__":
    main()
