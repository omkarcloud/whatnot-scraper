"""Configuration for the Whatnot Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                     port the API listens on (default 8000)
    WHATNOT_PROXY            proxy URL for every request, e.g. http://user:pass@host:port
                             (default: none — direct). Whatnot's GraphQL API answered
                             every request from one IP in testing, so you very
                             likely don't need this.
    WHATNOT_FALLBACK_PROXY   proxy URL used only after Whatnot answers 403/429 on
                             your own IP, for WHATNOT_BLOCK_COOLDOWN seconds
                             (default: none — keep retrying direct)

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

WHATNOT_BLOCK_COOLDOWN = 900


def whatnot_proxy():
    return os.environ.get("WHATNOT_PROXY") or None


def whatnot_fallback_proxy():
    return os.environ.get("WHATNOT_FALLBACK_PROXY") or None
