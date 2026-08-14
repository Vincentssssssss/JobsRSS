import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import List

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import Job


@dataclass
class DigestSummary:
    total_new: int
    high_match: int
    by_source: dict[str, int]
    jobs: List[Job]


def build_24h_summary(db: Session) -> DigestSummary:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    jobs = (
        db.query(Job)
        .filter(Job.first_seen_at >= cutoff)
        .order_by(desc(Job.match_score), desc(Job.posted_at), desc(Job.id))
        .limit(200)
        .all()
    )
    by_source: dict[str, int] = {}
    for job in jobs:
        by_source[job.source] = by_source.get(job.source, 0) + 1
    high_match = len([job for job in jobs if job.match_score >= get_settings().high_match_threshold])
    return DigestSummary(total_new=len(jobs), high_match=high_match, by_source=by_source, jobs=jobs)


def render_digest_html(summary: DigestSummary) -> str:
    source_items = "".join(f"<li><strong>{source}</strong>: {count}</li>" for source, count in summary.by_source.items())
    rows = []
    for job in summary.jobs[:40]:
        rows.append(
            f"<tr>"
            f"<td>{job.company}</td>"
            f"<td>{job.title}</td>"
            f"<td>{job.location}</td>"
            f"<td>{int(job.match_score)}</td>"
            f"<td><a href='{job.apply_url}'>Apply</a></td>"
            f"</tr>"
        )
    table_rows = "".join(rows) if rows else "<tr><td colspan='5'>No jobs in the past 24 hours.</td></tr>"
    return f"""
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif; color: #1d1d1f;">
  <h2>JobsRSS Daily Digest (Last 24h)</h2>
  <p>Total new jobs: <strong>{summary.total_new}</strong></p>
  <p>High match jobs: <strong>{summary.high_match}</strong></p>
  <h3>By source</h3>
  <ul>{source_items}</ul>
  <h3>Top jobs</h3>
  <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
    <thead>
      <tr>
        <th>Company</th><th>Title</th><th>Location</th><th>Score</th><th>Apply</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>
"""


def send_daily_digest(db: Session) -> bool:
    settings = get_settings()
    recipients = settings.csv_items(settings.digest_email_recipients)
    if not recipients:
        return False
    if not settings.digest_email_smtp_host or not settings.digest_email_sender:
        return False

    summary = build_24h_summary(db)
    html = render_digest_html(summary)
    message = MIMEText(html, "html", "utf-8")
    message["Subject"] = "JobsRSS Daily Digest (Last 24h)"
    message["From"] = settings.digest_email_sender
    message["To"] = ", ".join(recipients)

    with smtplib.SMTP(settings.digest_email_smtp_host, settings.digest_email_smtp_port, timeout=40) as server:
        if settings.digest_email_use_tls:
            server.starttls()
        if settings.digest_email_smtp_username and settings.digest_email_smtp_password:
            server.login(settings.digest_email_smtp_username, settings.digest_email_smtp_password)
        server.sendmail(settings.digest_email_sender, recipients, message.as_string())
    return True
