import requests
import os
from dotenv import load_dotenv
from error_handler import handle_response

load_dotenv()

API_KEY = os.getenv("TWITTER_API_KEY")
BASE_URL = "https://api.twitterapi.io"

headers = {
    "X-API-Key": API_KEY
}

def get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    success, data = handle_response(response)
    return success, data