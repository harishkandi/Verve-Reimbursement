"""Email notifications, queued during a request and sent only after its commit succeeds."""

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ..config import settings
from ..models import User

log = logging.getLogger("reimbursement.notify")


def queue(db: Session, to: User | None, subject: str, body: str) -> None:
    if to is None or not to.is_active:
        return
    db.info.setdefault("outbox", []).append((to.email, subject, body))


def claim_link(claim_id: int) -> str:
    return f"{settings.app_url}/claims/{claim_id}"


def commit(db: Session) -> None:
    db.commit()
    outbox = db.info.pop("outbox", [])
    for to, subject, body in outbox:
        _send(to, subject, body)


def _send(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        log.info("email (not sent, SMTP_HOST unset) to=%s subject=%s", to, subject)
        return
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(msg)
    except Exception:
        # The claim change is already saved; a mail outage must not undo it.
        log.exception("email to %s failed", to)
