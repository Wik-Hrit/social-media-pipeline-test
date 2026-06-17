def handle_response(response):
    status = response.status_code

    if status == 200:
        return True, response.json()
    elif status == 401:
        print("Error 401: Invalid API key")
        return False, None
    elif status == 402:
        print("Error 402: Payment required — free tier limit reached or feature requires paid plan")
        return False, None
    elif status == 403:
        print("Error 403: Access denied")
        return False, None
    elif status == 404:
        print("Error 404: Wrong endpoint")
        return False, None
    elif status == 429:
        print("Error 429: Rate limit exceeded — wait before retrying")
        return False, None
    elif status == 500:
        print("Error 500: Server error")
        return False, None
    else:
        print(f"Unexpected error: {status}")
        return False, None