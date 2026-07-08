"""
error_handler.py
HTTP response handler for twitterapi.io requests.
"""
import logging

log = logging.getLogger(__name__)

_MESSAGES = {
    401: "Invalid API key",
    402: "Payment required — free tier limit reached or feature requires paid plan",
    403: "Access denied",
    404: "Wrong endpoint",
    429: "Rate limit exceeded — will retry",
    500: "Server error — will retry",
    502: "Bad gateway — will retry",
    503: "Service unavailable — will retry",
}

# Codes that should trigger a retry in twitter_client.py
RETRY_CODES = {429, 500, 502, 503}


def handle_response(response):
    status = response.status_code

    if status == 200:
        try:
            return True, response.json()
        except Exception as e:
            log.error(f"Failed to parse JSON response: {e}")
            return False, None

    msg = _MESSAGES.get(status, f"Unexpected error: {status}")
    level = logging.WARNING if status in RETRY_CODES else logging.ERROR
    log.log(level, f"HTTP {status}: {msg}")
    return False, None