import time

from constants import BPS
from endpoints.get_virtual_chain_blue_score import current_blue_score_data


def add_cache_control(blue_score, timestamp, response):
    if blue_score and current_blue_score_data["blue_score"] > 0:
        delta_seconds = abs(current_blue_score_data["blue_score"] - int(blue_score)) / BPS
    elif timestamp:
        delta_seconds = abs(time.time() - int(timestamp) / 1000)
    else:
        return
    if delta_seconds < 20:
        ttl = 4
    elif delta_seconds < 60:
        ttl = 20
    elif delta_seconds < 600:
        ttl = 60
    elif delta_seconds < 3600:
        ttl = 600
    elif delta_seconds < 86400:
        ttl = 1200
    else:
        ttl = 3600
    response.headers["Cache-Control"] = f"public, max-age={ttl}"
