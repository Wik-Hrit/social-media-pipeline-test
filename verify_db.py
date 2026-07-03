import sqlite3
conn = sqlite3.connect('pipeline.db')
tables = ['queries','fetch_runs','tweets','tweet_nlp','entities','hashtags','keywords','topics','events']
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'{t:<15}: {count}')
conn.close()