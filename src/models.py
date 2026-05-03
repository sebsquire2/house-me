from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Property:
    source: str
    property_id: str
    url: str
    address: str
    price_pcm: int
    bedrooms: int
    property_type: str
    available_date: Optional[date]
    available_date_raw: str

    @property
    def unique_id(self) -> str:
        return f"{self.source}:{self.property_id}"
