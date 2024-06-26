import pandas as pd
from newsdataapi import NewsDataApiClient

api = NewsDataApiClient(apikey="YOUR_API_KEY")

page_count = 0
num_pages = 10
page = None
results = []

while page_count <= num_pages:
    response = api.news_api(q="world news", page=page, language='en')
    results.extend(response['results'])
    page = response.get('nextPage', None)
    if not page:
        break
    page_count += 1

df = pd.DataFrame(results)
df.to_csv(f"news_results.csv", index=False)