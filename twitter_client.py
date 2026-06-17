import requests
import os
import time
from dotenv import load_dotenv
from error_handler import handle_response

load_dotenv()

API_KEY = os.getenv("TWITTER_API_KEY")
BASE_URL = "https://api.twitterapi.io"

headers = {
    "X-API-Key": API_KEY
}

MAX_RETRIES = 3

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
            success, data = handle_response(response)
            return success, data

        except requests.exceptions.Timeout:
            print(f"  Timeout. Attempt {attempt+1}/{MAX_RETRIES}")

        except requests.exceptions.ConnectionError:
            print(f"  Connection error. Attempt {attempt+1}/{MAX_RETRIES}")

        except requests.exceptions.RequestException as e:
            print(f"  Request failed: {e}")

        if attempt < MAX_RETRIES - 1:
            print("  Retrying in 3 seconds...")
            time.sleep(3)

    print("  All retry attempts failed.")
    return False, None