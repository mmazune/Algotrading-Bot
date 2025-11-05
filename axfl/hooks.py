"""Trade lifecycle hooks for notifications and persistence."""
import datetime as dt
from axfl.notify.trades import open_alert, close_alert
from axfl.metrics import perf

def on_trade_opened(*, trade_id, order_id, instrument, strategy, side, units, entry,
                    sl=None, tp=None, spread_pips=None, reason:str="signal") -> str:
    opened_at_iso = dt.datetime.utcnow().isoformat(timespec="seconds")+"Z"
    perf.record_open(trade_id=trade_id, order_id=order_id, instrument=instrument, strategy=strategy,
                     side=side, units=units, entry=entry, opened_at_iso=opened_at_iso)
    open_alert(order_id=order_id, trade_id=trade_id, instrument=instrument, side=side, units=units,
               entry=entry, strategy=strategy, sl=sl, tp=tp, spread_pips=spread_pips, reason=reason)
    return opened_at_iso

def on_trade_closed(*, trade_id, order_id, instrument, strategy, side, units, entry, exit_price,
                    opened_at_iso, reason:str="close") -> None:
    closed_at_iso = dt.datetime.utcnow().isoformat(timespec="seconds")+"Z"
    perf.record_close(trade_id=trade_id, exit_price=exit_price, closed_at_iso=closed_at_iso)
    close_alert(order_id=order_id, trade_id=trade_id, instrument=instrument, side=side, units=units,
                entry=entry, exit_price=exit_price, strategy=strategy, opened_at_iso=opened_at_iso, reason=reason)
