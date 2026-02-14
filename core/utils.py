from datetime import timedelta
from django.utils import timezone

# You can add specific holiday dates here (YYYY, MM, DD)
HOLIDAYS = [
    timezone.datetime(2026, 1, 26).date(), # Republic Day
    timezone.datetime(2026, 8, 15).date(), # Independence Day
    timezone.datetime(2026, 12, 25).date(), # Christmas
]

def is_business_day(current_date):
    """Returns True if Mon-Fri and not a holiday."""
    # 5 = Saturday, 6 = Sunday
    if current_date.weekday() >= 5:
        return False
    if current_date in HOLIDAYS:
        return False
    return True

def calculate_business_deadline(start_dt):
    """
    Calculates a 24-hour deadline.
    If the deadline falls on a weekend or holiday, it pushes it 
    to the next available business day.
    """
    # 1. Add the initial 24-hour window
    deadline = start_dt + timedelta(hours=24)
    
    # 2. Check if the resulting deadline lands on a non-business day
    # If so, keep adding 24 hours until we hit a business day.
    while not is_business_day(deadline.date()):
        deadline += timedelta(days=1)
        
    return deadline