# User Setup Guide - Personal Dashboard Configuration

This guide shows you how to configure your personal preferences that will appear on the homepage and in your personal dashboard.

## Quick Setup

### 1. Edit Your User Configuration

Open `data/users.yaml` and add or modify your user profile:

```yaml
users:
  yourname:  # Replace with your preferred username
    weather:
      city: "Your City, State"       # e.g., "Seattle, WA" or "London, UK"
      # OR use coordinates instead:
      # latitude: 47.6062
      # longitude: -122.3321
      units: "fahrenheit"             # or "celsius"
    
    crypto:
      coins: ["bitcoin", "ethereum", "solana"]  # Your favorite cryptocurrencies
      vs_currency: "usd"              # or "eur", "gbp", etc.
    
    stocks:
      tickers: ["AAPL", "MSFT", "GOOGL"]       # Your stock portfolio
    
    transit:  # Optional
      api_url: "https://your-transit-worker.workers.dev/v1/eta?route=12&stop=456"
```

### 2. Set Homepage User

Edit `config.yaml` to show your preferences on the homepage:

```yaml
site:
  homepage_user: "yourname"  # Must match your username above
```

### 3. Rebuild Site

```bash
python build.py
```

## What You Get

### Personal Dashboard Pages
- **Your weather dashboard**: `/u/yourname/index.html` 
- **JSON API feed**: `/api/yourname.json`

### Homepage Integration
- **Weather tile**: Shows your preferred city's current conditions
- **Portfolio tile**: Highlights your best/worst performing stocks & crypto
- **Quick access**: Link to your personal dashboard

## Configuration Options

### Weather Configuration

**Option 1: City Name**
```yaml
weather:
  city: "San Francisco, CA"
  units: "fahrenheit"
```

**Option 2: Exact Coordinates** 
```yaml
weather:
  latitude: 37.7749
  longitude: -122.4194
  units: "celsius"
```

### Crypto Configuration

```yaml
crypto:
  coins: ["bitcoin", "ethereum", "cardano", "solana", "chainlink"]
  vs_currency: "usd"  # Supported: usd, eur, gbp, jpy, etc.
```

**Available coins**: Check `data/coins.txt` for the full list of supported cryptocurrencies.

### Stock Configuration

```yaml
stocks:
  tickers: ["AAPL", "MSFT", "TSLA", "SPY", "QQQ"]
```

**Available tickers**: Check `data/stocks.txt` for supported US stock symbols.

### Transit Configuration (Optional)

```yaml
transit:
  api_url: "https://your-cloudflare-worker.workers.dev/v1/eta?route=N&stop=times-sq"
```

This requires deploying the included Cloudflare Worker. See the main README for setup instructions.

## Multiple Users

You can configure multiple users in the same file:

```yaml
users:
  alice:
    weather:
      city: "New York, NY"
      units: "fahrenheit"
    crypto:
      coins: ["bitcoin", "ethereum"]
      vs_currency: "usd"
    stocks:
      tickers: ["SPY", "QQQ"]
  
  bob:
    weather:
      city: "London, UK"  
      units: "celsius"
    crypto:
      coins: ["bitcoin", "cardano"]
      vs_currency: "gbp"
    stocks:
      tickers: ["AAPL", "MSFT"]
```

Each user gets:
- Personal dashboard at `/u/alice/` and `/u/bob/`
- Personal API feeds at `/api/alice.json` and `/api/bob.json`

## Homepage Preview

Set `homepage_user` in `config.yaml` to control which user's data appears on the main homepage tiles:

```yaml
site:
  homepage_user: "alice"  # Alice's weather and portfolio highlights
```

## Example: Complete Personal Setup

Here's a complete example for someone interested in tech stocks and major crypto:

```yaml
# In data/users.yaml
users:
  techfan:
    weather:
      city: "Austin, TX"
      units: "fahrenheit"
    crypto:
      coins: ["bitcoin", "ethereum", "solana", "chainlink", "polygon"]
      vs_currency: "usd"
    stocks:
      tickers: ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMD", "INTC"]
    transit:
      api_url: "https://austin-transit.workers.dev/v1/eta?route=801&stop=downtown"

# In config.yaml  
site:
  homepage_user: "techfan"
```

After rebuilding, the homepage will show:
- **Weather**: Current conditions in Austin, TX
- **Portfolio**: Best/worst performers from their tech stocks and crypto picks
- **Personal Dashboard**: Link to `/u/techfan/index.html` with all their data

## JSON API Usage

Each user gets a JSON feed perfect for mobile apps or widgets:

```bash
curl https://yourdomain.github.io/postcard-dashboard/api/techfan.json
```

```json
{
  "updated_at": "2025-08-09 20:30:00 UTC",
  "weather": {
    "current_temp": "78°F",
    "humidity": "65%",
    "summary": "High 82°F, Low 64°F, Clear conditions"
  },
  "crypto": {
    "bitcoin": 45000,
    "ethereum": 2800
  },
  "stocks": {
    "AAPL": {"close": 180.50, "change": 2.1}
  }
}
```

## Troubleshooting

**Homepage shows wrong user**: Check `homepage_user` in `config.yaml` matches a username in `users.yaml`

**Weather not showing**: Verify city name format or use latitude/longitude coordinates

**Stocks missing**: Ensure tickers are valid US symbols from `data/stocks.txt`

**Crypto not showing**: Check coin IDs match those in `data/coins.txt`