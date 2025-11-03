from .adapters.lsg import LSG
from .adapters.orb import ORB
from .adapters.arls import ARLS
from .price_action_breakout import PriceActionBreakout
from .ema_trend import EmaTrend
from .bollinger_mean_rev import BollingerMeanRev

REGISTRY = {
    "lsg": LSG,
    "orb": ORB,
    "arls": ARLS,
    "price_action_breakout": PriceActionBreakout,
    "ema_trend": EmaTrend,
    "bollinger_mean_rev": BollingerMeanRev,
}
