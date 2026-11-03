import os
from datetime import datetime, timezone, timedelta

# Enforce Indian Standard Time (+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Return the current time strictly in Indian Standard Time (IST)."""
    return datetime.now(IST)
