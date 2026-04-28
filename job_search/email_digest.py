"""Send a daily email digest of high-scoring jobs via SMTP."""

from __future__ import annotations

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

log = logging.getLogger(__name__)


def send_digest(jobs: list[dict[str, Any]], cfg: dict) -> bool:
    """
    Email all *jobs* (pre-filtered to min score) using the SMTP settings in *cfg*.
    Returns True on success.
    """
    email_cfg = cfg.get("email", {})
    if not jobs:
        log.info("Email digest: no roles to send (all below min score threshold).")
        return True

    today = date.today().isoformat()
    subject = f"{email_cfg.get('subject_prefix', '[Job Digest]')} {today} — {len(jobs)} role(s) scored ≥ {cfg.get('email', {}).get('min_score_to_email', 7)}"

    plain_body, html_body = _build_body(jobs, today)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg.get("from_addr", email_cfg.get("username", ""))
    msg["To"] = email_cfg.get("to_addr", "")
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        smtp_cls = smtplib.SMTP
        host = email_cfg.get("smtp_host", "smtp.gmail.com")
        port = email_cfg.get("smtp_port", 587)

        with smtp_cls(host, port, timeout=30) as server:
            if email_cfg.get("use_tls", True):
                server.starttls()
            server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(msg["From"], msg["To"], msg.as_string())

        log.info("Email digest sent: %d roles to %s", len(jobs), msg["To"])
        return True

    except smtplib.SMTPException as exc:
        log.error("Failed to send email digest: %s", exc)
        return False
    except KeyError as exc:
        log.error("Missing email config key: %s — check config.yaml", exc)
        return False


def _build_body(jobs: list[dict[str, Any]], today: str) -> tuple[str, str]:
    """Return (plain_text, html) tuple."""
    sorted_jobs = sorted(jobs, key=lambda j: j.get("fit_score", 0), reverse=True)

    # ── Plain text ──────────────────────────────────────────────────────────────
    plain_lines = [
        f"Job Search Digest — {today}",
        f"{len(jobs)} role(s) with fit score ≥ threshold",
        "=" * 60,
        "",
    ]
    for job in sorted_jobs:
        reloc = " [RELOCATION REQUIRED]" if job.get("relocation_required") else ""
        plain_lines += [
            f"[{job.get('fit_score', 0)}/10] {job['title']} — {job['company']}",
            f"  Location : {job.get('location_label', '')}{reloc}",
            f"  Salary   : {job.get('salary_display', 'comp unknown')}",
            f"  Fit note : {job.get('fit_note', '')}",
            f"  Apply    : {job.get('url', '')}",
            "",
        ]

    # ── HTML ───────────────────────────────────────────────────────────────────
    html_rows = ""
    for job in sorted_jobs:
        score = job.get("fit_score", 0)
        color = "#2ecc71" if score >= 8 else "#f39c12" if score >= 6 else "#e74c3c"
        reloc_badge = (
            ' <span style="background:#e74c3c;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;">RELOCATION</span>'
            if job.get("relocation_required")
            else ""
        )
        remote_badge = (
            ' <span style="background:#3498db;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;">REMOTE</span>'
            if job.get("remote")
            else ""
        )
        html_rows += f"""
        <tr>
          <td style="padding:12px;border-bottom:1px solid #eee;">
            <strong><a href="{job.get('url','')}" style="color:#2c3e50;text-decoration:none;">{job['title']}</a></strong>
            <br><span style="color:#666;">{job['company']}</span>
          </td>
          <td style="padding:12px;border-bottom:1px solid #eee;">
            {job.get('location_label','')}{reloc_badge}{remote_badge}
          </td>
          <td style="padding:12px;border-bottom:1px solid #eee;">{job.get('salary_display','comp unknown')}</td>
          <td style="padding:12px;border-bottom:1px solid #eee;text-align:center;">
            <span style="background:{color};color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;">{score}/10</span>
          </td>
          <td style="padding:12px;border-bottom:1px solid #eee;font-size:13px;color:#555;">{job.get('fit_note','')}</td>
        </tr>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;">
      <h2 style="color:#2c3e50;">Job Search Digest — {today}</h2>
      <p style="color:#666;">{len(jobs)} role(s) matching your criteria</p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#2c3e50;color:#fff;">
            <th style="padding:10px;text-align:left;">Role / Company</th>
            <th style="padding:10px;text-align:left;">Location</th>
            <th style="padding:10px;text-align:left;">Salary</th>
            <th style="padding:10px;text-align:center;">Score</th>
            <th style="padding:10px;text-align:left;">Fit Note</th>
          </tr>
        </thead>
        <tbody>{html_rows}</tbody>
      </table>
      <p style="margin-top:20px;color:#999;font-size:12px;">
        Generated by your automated job search pipeline.
      </p>
    </body></html>
    """

    return "\n".join(plain_lines), html
