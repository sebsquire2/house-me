import logging
import boto3
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


def send(prop: Property, sender: str, recipient: str, region: str = "eu-west-1") -> None:
    subject, body = _format_email(prop)
    client = boto3.client("ses", region_name=region)
    try:
        client.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        logger.info("Sent email for %s", prop.unique_id)
    except Exception as e:
        logger.error("Failed to send email for %s: %s", prop.unique_id, e)
        raise
