import time

from constants import BPS
from endpoints.get_virtual_chain_blue_score import current_blue_score_data


def add_cache_control(blue_score, timestamp, response):
    if blue_score and current_blue_score_data["blue_score"] > 0:
        delta = abs(blue_score - current_blue_score_data["blue_score"]) / BPS
        if delta < 20:
            response.headers["Cache-Control"] = "public, max-age=2"
        elif delta < 60:
            response.headers["Cache-Control"] = "public, max-age=10"
        elif delta < 600:
            response.headers["Cache-Control"] = "public, max-age=60"
        else:
            response.headers["Cache-Control"] = "public, max-age=600"
    elif timestamp:
        if int(timestamp) / 1000 > int(time.time()) - 20:
            response.headers["Cache-Control"] = "public, max-age=2"
        elif int(timestamp) / 1000 > int(time.time()) - 60:
            response.headers["Cache-Control"] = "public, max-age=10"
        elif int(timestamp) / 1000 > int(time.time()) - 600:
            response.headers["Cache-Control"] = "public, max-age=60"
        else:
            response.headers["Cache-Control"] = "public, max-age=600"
