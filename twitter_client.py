"""
twitter_client.py — twitterapi.io HTTP client.
Fix #5: API key validation — raises RuntimeError immediately if missing
Fix #6: Settings imported from config.py
Fix #7: print() replaced with log.*()
"""

import requests
import os
import time
import logging
from dotenv import load_dotenv
from error_handler import handle_response
from config import MAX_RETRIES, RETRY_DELAY, RATE_LIMIT_DELAY, RETRY_CODES, MIN_CREDITS_THRESHOLD, STOP_ON_LOW_CREDITS

load_dotenv()
log = logging.getLogger(__name__)

API_KEY  = os.getenv("TWITTER_API_KEY")
BASE_URL = "https://api.twitterapi.io"
headers  = {"X-API-Key": API_KEY}

# Fix #5 — API key validation: stop immediately if missing
if not API_KEY:
    raise RuntimeError(
        "Twitter API key missing. Set TWITTER_API_KEY in your .env file."
    )


def check_credits() -> int:
    """
    Fetch remaining recharge credits from twitterapi.io.
    Returns credit balance, or -1 if the check fails.
    Logs a warning if below MIN_CREDITS_THRESHOLD.
    """
    try:
        resp = requests.get(
            "https://api.twitterapi.io/oapi/my/info",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data     = resp.json()
            credits  = data.get("recharge_credits", 0)
            bonus    = data.get("total_bonus_credits", 0)  # correct field name
            total    = credits + bonus
            log.info(f"  💳 Credits remaining: {total} (recharge: {credits}, bonus: {bonus})")
            if total < MIN_CREDITS_THRESHOLD:
                log.warning(f"  ⚠ LOW CREDITS: {total} remaining (threshold: {MIN_CREDITS_THRESHOLD})")
                if STOP_ON_LOW_CREDITS:
                    raise RuntimeError(f"Credits too low ({total}). Top up at https://twitterapi.io/dashboard")
            return total
        else:
            log.warning(f"  Credit check failed: HTTP {resp.status_code}")
            return -1
    except RuntimeError:
        raise
    except Exception as e:
        log.warning(f"  Credit check error: {e}")
        return -1


def get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code in RETRY_CODES:
                wait = RATE_LIMIT_DELAY if response.status_code == 429 else RETRY_DELAY
                log.warning(f"  HTTP {response.status_code}. Attempt {attempt+1}/{MAX_RETRIES} — retrying in {wait}s...")
                time.sleep(wait)
                continue

            success, data = handle_response(response)
            return success, data

        except requests.exceptions.Timeout:
            log.warning(f"  Timeout. Attempt {attempt+1}/{MAX_RETRIES}")

        except requests.exceptions.ConnectionError:
            log.warning(f"  Connection error. Attempt {attempt+1}/{MAX_RETRIES}")

        except requests.exceptions.RequestException as e:
            log.error(f"  Request failed: {e}")

        if attempt < MAX_RETRIES - 1:
            log.info(f"  Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)

    log.error("  All retry attempts failed.")
    return False, None