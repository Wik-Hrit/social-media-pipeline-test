import requests
import os
import time
import logging
from dotenv import load_dotenv
from error_handler import handle_response

load_dotenv()
log = logging.getLogger(__name__)

API_KEY  = os.getenv("TWITTER_API_KEY")
BASE_URL = "https://api.twitterapi.io"
headers  = {"X-API-Key": API_KEY}

MAX_RETRIES = 3
RETRY_CODES = {429, 500, 502, 503}   # Fix #4 — retry on 429 too

# Fix #11 — API key validation
if not API_KEY:
    log.error("TWITTER_API_KEY not set in .env — twitterapi.io will fail")


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

            # Fix #4 — retry on 429 rate limit
            if response.status_code in RETRY_CODES:
                wait = 10 if response.status_code == 429 else 3
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
            log.info("  Retrying in 3 seconds...")
            time.sleep(3)

    log.error("  All retry attempts failed.")
    return False, None