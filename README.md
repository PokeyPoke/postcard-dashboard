# Postcard Dashboard

A static, zero-backend dashboard that generates weather, stock, crypto, and transit data pages. Built with Python and deployed via GitHub Actions to GitHub Pages.

## Quick Start

1. **Clone and setup:**
   ```bash
   git clone <this-repo>
   cd postcard-dashboard
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Build locally:**
   ```bash
   python build.py
   ```

3. **View the site:**
   ```bash
   open dist/index.html  # On Linux: xdg-open dist/index.html
   ```

## Features

- **📍 Weather**: 60+ US cities with current conditions and forecasts
- **💰 Crypto**: 150+ cryptocurrencies with live prices from CoinGecko
- **📈 Stocks**: 200+ US stocks with prices from Stooq
- **👤 Personal Pages**: Customizable per-user dashboards
- **🚌 Transit**: Optional live transit ETA via Cloudflare Worker
- **🔍 Search**: Client-side filtering on all list pages
- **📱 Mobile**: Responsive dark theme design

## Data Configuration

### Cities (`data/cities.csv`)
```csv
slug,name,country,city
nyc,New York City,US,New York
la,Los Angeles,US,Los Angeles
```

### Stocks (`data/stocks.txt`)
One ticker per line:
```
AAPL
MSFT
GOOGL
```

### Crypto (`data/coins.txt`)
CoinGecko IDs, one per line:
```
bitcoin
ethereum
solana
```

### Users (`data/users.yaml`)
```yaml
users:
  username:
    weather:
      city: "San Francisco, CA"  # or latitude/longitude
      units: "fahrenheit"        # "celsius" or "fahrenheit"
    crypto:
      coins: ["bitcoin", "ethereum"]
      vs_currency: "usd"
    stocks:
      tickers: ["AAPL", "MSFT"]
    transit:  # optional
      api_url: "https://your-worker.workers.dev/v1/eta?route=N&stop=123"
```

## Deployment

### GitHub Pages (Automatic)
1. Push to `main` branch → full build and deploy
2. Hourly cron → sharded build (24 parallel jobs) and deploy

### Manual Deploy
```bash
python build.py
# Upload dist/ folder to your web host
```

## Sharded Builds

For large datasets, the build supports sharding:
```bash
export SHARD_INDEX=0
export SHARD_TOTAL=4
python build.py  # Builds 1/4 of the data
```

GitHub Actions automatically uses 4 shards for scheduled builds.

## Transit Integration

1. **Deploy the Cloudflare Worker:**
   ```bash
   cd cloudflare
   wrangler login
   wrangler publish
   ```

2. **Configure environment variables in Cloudflare:**
   - `TRANSIT_UPSTREAM`: Optional upstream API URL
   - Leave empty for mock data

3. **Add to user config:**
   ```yaml
   transit:
     api_url: "https://your-worker.workers.dev/v1/eta?route=12&stop=456"
   ```

## API Endpoints

Each user gets a JSON feed at `/api/username.json`:
```json
{
  "updated_at": "2025-08-09 12:00:00 UTC",
  "weather": { "current_temp": "72°F", "humidity": "65%" },
  "crypto": { "bitcoin": 45000, "ethereum": 2800 },
  "stocks": { "AAPL": { "close": 180.50, "change": 2.1 } }
}
```

## Configuration

### `config.yaml`
```yaml
build:
  throttle_ms: 400          # API request throttling
  retry_delay_ms: 2000      # Retry delay on rate limits
  chunk_sizes:
    crypto: 100             # CoinGecko batch size
    stocks: 50              # Stock batch size

apis:
  open_meteo_geocoding: "https://geocoding-api.open-meteo.com/v1/search"
  open_meteo_forecast: "https://api.open-meteo.com/v1/forecast"
  stooq_base: "https://stooq.com/q/l/?s={}&f=sd2t2ohlcv&h&e=csv"
  coingecko_price: "https://api.coingecko.com/api/v3/simple/price"
```

## Troubleshooting

### Build Issues

**"Rate limited (HTTP 429)"**
- Increase `throttle_ms` in config.yaml
- Check API quotas
- Use sharded builds for large datasets

**"Module not found"**
```bash
source venv/bin/activate  # Activate virtual environment
pip install -r requirements.txt
```

**"Permission denied" on build.py**
```bash
chmod +x build.py
```

### GitHub Actions

**Build failing on API calls**
- APIs may be temporarily down
- Check GitHub Actions logs for specific errors
- Builds continue with fallback data when APIs fail

**Sharded builds not merging correctly**
- Ensure all shards complete successfully
- Check artifact upload/download in Actions

### Transit Worker

**Worker not responding**
```bash
wrangler tail  # View worker logs
curl https://your-worker.workers.dev/health  # Health check
```

**ETA data not updating**
- Check browser console for JavaScript errors
- Verify CORS headers on worker
- Check `data-api` and `data-target` attributes

### Search Not Working

**Search box not filtering**
- Check browser console for JavaScript errors
- Ensure `search.js` is loaded correctly
- Verify table structure matches expected format

## File Structure

```
/
├── build.py              # Main build script
├── requirements.txt      # Python dependencies
├── config.yaml          # Build configuration
├── data/                 # Data files
│   ├── cities.csv
│   ├── stocks.txt
│   ├── coins.txt
│   └── users.yaml
├── templates/            # Jinja2 templates
│   ├── base.html
│   ├── module_card.html
│   └── list.html
├── static/              # Static assets
│   ├── style.css
│   ├── search.js
│   └── transit.js
├── cloudflare/          # Transit worker
│   └── worker.js
├── wrangler.toml        # Cloudflare config
└── .github/workflows/   # CI/CD
    └── build.yml
```

## API Rate Limits

- **Open-Meteo**: No key required, 10,000 requests/day
- **CoinGecko**: 50 requests/minute (free tier)
- **Stooq**: No published limits, be respectful

## Performance Tips

1. **Use sharding** for >1000 data points
2. **Adjust throttling** based on API response times
3. **Monitor build times** in GitHub Actions
4. **Cache static assets** with CDN if self-hosting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test locally with `python build.py`
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

---

**Generated pages:**
- `/` - Home with navigation
- `/city/` - Cities index + individual city pages
- `/crypto/` - Crypto index + individual coin pages  
- `/stocks/` - Stocks index + individual ticker pages
- `/u/username/` - Personal dashboard pages
- `/api/username.json` - JSON feeds for devices

**Repository:** https://github.com/PokeyPoke/postcard-dashboard

**Live demo:** Coming soon (see [Issue #1](https://github.com/PokeyPoke/postcard-dashboard/issues/1) for deployment setup)