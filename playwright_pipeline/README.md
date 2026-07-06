Playwright scraping pipeline

Usage:
- Put keywords in environment variable `KEYWORDS` or pass as argument to `scrape.js`.
- Container (from docker-compose) will run `node scrape.js` and write results to `/data`.

Example run locally (requires Docker):

```bash
# build and start
docker-compose up --build -d

# run playwright scraper once (if not auto-run by service)
docker-compose run --rm playwright node scrape.js "주식,테마,종목"

# check output files under ./data
ls -la data/
```

Notes:
- Prefer using YouTube Data API for robust results; this scraper is a fallback/demo.
- Ensure `YOUTUBE_API_KEY` is set in environment when using API-based methods.
