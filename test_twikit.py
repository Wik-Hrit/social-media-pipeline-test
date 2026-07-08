import asyncio
import os
from twikit import Client
from dotenv import load_dotenv

load_dotenv()

async def main():
    c = Client()
    await c.login(
        auth_info_1=os.getenv("TWITTER_USERNAME"),
        auth_info_2=os.getenv("TWITTER_EMAIL"),
        password=os.getenv("TWITTER_PASSWORD"),
    )
    print('Login OK')
    c.save_cookies('twikit_cookies.json')
    print('Cookies saved')

asyncio.run(main())