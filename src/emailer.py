import logging
import smtplib
from collections.abc import Iterator
from contextlib import contextmanager
from email.mime.text import MIMEText
from models import Property

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "rightmove": "Rightmove",
    "openrent": "OpenRent",
    "zoopla": "Zoopla",
}


def _format_email(prop: Property) -> tuple[str, str]:
    source = SOURCE_LABELS.get(prop.source, prop.source)
    available = prop.available_date_raw or "Unknown"

    subject = (
        f"[house-me] {prop.bedrooms}bed £{prop.price_pcm}pcm — "
        f"{prop.address[:60]} ({source})"
    )

    body = "\n".join([
        f"Source:     {source}",
        f"Address:    {prop.address}",
        f"Price:      £{prop.price_pcm} pcm",
        f"Bedrooms:   {prop.bedrooms}",
        f"Type:       {prop.property_type}",
        f"Available:  {available}",
        f"",
        f"Link: {prop.url}",
    ])

    return subject, body


@contextmanager
def connect(sender: str, app_password: str) -> Iterator[smtplib.SMTP_SSL]:
    """One Gmail login per run, shared by every send in it."""
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        yield smtp


def send(smtp: smtplib.SMTP_SSL, prop: Property, sender: str, recipient: str) -> None:
    subject, body = _format_email(prop)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    smtp.sendmail(sender, [recipient], msg.as_string())
    logger.info("Sent email for %s", prop.unique_id)
