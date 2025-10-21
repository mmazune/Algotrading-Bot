"""
News calendar and event-based trading guards.
"""
from .calendar import load_events_csv, upcoming_windows, affects_symbol, is_in_event_window

__all__ = ['load_events_csv', 'upcoming_windows', 'affects_symbol', 'is_in_event_window']
