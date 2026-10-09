import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.context.models import TemporalContext
from backend.app.core.config import get_settings

WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


class DateResolver:
    def resolve(self, message: str, *, now: datetime | None = None) -> TemporalContext:
        timezone = ZoneInfo(get_settings().user_timezone)
        current = now.astimezone(timezone) if now else datetime.now(timezone)
        text = normalize(message)
        target = None
        if "apres-demain" in text or "apres demain" in text:
            target = current.date() + timedelta(days=2)
        elif "demain" in text:
            target = current.date() + timedelta(days=1)
        elif "aujourd'hui" in text or "aujourdhui" in text:
            target = current.date()
        elif "semaine prochaine" in text:
            target = current.date() + timedelta(days=7 - current.weekday())
        else:
            for name, weekday in WEEKDAYS.items():
                if re.search(rf"\b{name}(?:\s+prochain)?\b", text):
                    days = (weekday - current.weekday()) % 7
                    if days == 0:
                        days += 7
                    target = current.date() + timedelta(days=days)
                    break
        period = None
        if "matin" in text:
            period = "morning"
        elif "apres-midi" in text or "apres midi" in text:
            period = "afternoon"
        elif "soir" in text:
            period = "evening"
        return TemporalContext(
            timezone=str(timezone),
            now=current,
            today=current.date().isoformat(),
            resolved_date=target.isoformat() if target else None,
            period=period,
        )


date_resolver = DateResolver()
