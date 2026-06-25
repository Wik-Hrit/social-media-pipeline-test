import asyncio
from twikit import Client

async def main():
    c = Client()
    await c.login(
        auth_info_1='HritwikVarpcr',
        auth_info_2='varmahritwik@gmail.com',
        password='Hritwik@8586'
    )
    print('Login OK')
    c.save_cookies('twikit_cookies.json')
    print('Cookies saved')

asyncio.run(main())
