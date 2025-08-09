#!/usr/bin/env python3
"""
Static site generator for Postcard Dashboard
Builds weather, stocks, crypto, and user-specific pages
"""

import os
import sys
import csv
import json
import time
import yaml
import requests
import shutil
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote
from jinja2 import Environment, FileSystemLoader
import markdown

# Configuration
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
TEMPLATES_DIR = SCRIPT_DIR / "templates"
STATIC_DIR = SCRIPT_DIR / "static"
DIST_DIR = SCRIPT_DIR / "dist"

class SiteBuilder:
    def __init__(self):
        self.config = self.load_config()
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        self.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Shard configuration from environment
        self.shard_index = int(os.environ.get('SHARD_INDEX', 0))
        self.shard_total = int(os.environ.get('SHARD_TOTAL', 1))
        
        # Session for API requests
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'PostcardDashboard/1.0'})
    
    def load_config(self):
        """Load configuration from config.yaml"""
        try:
            with open(SCRIPT_DIR / "config.yaml", 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load config.yaml: {e}")
            return self.get_default_config()
    
    def get_default_config(self):
        """Default configuration"""
        return {
            'build': {
                'throttle_ms': 400,
                'retry_delay_ms': 2000,
                'chunk_sizes': {'crypto': 100, 'stocks': 50}
            },
            'apis': {
                'open_meteo_geocoding': 'https://geocoding-api.open-meteo.com/v1/search',
                'open_meteo_forecast': 'https://api.open-meteo.com/v1/forecast',
                'stooq_base': 'https://stooq.com/q/l/?s={}&f=sd2t2ohlcv&h&e=csv',
                'coingecko_price': 'https://api.coingecko.com/api/v3/simple/price'
            },
            'site': {
                'title': 'Postcard Dashboard',
                'description': 'Static dashboard with weather, stocks, crypto, and transit data'
            }
        }
    
    def should_build_shard(self, index, total):
        """Determine if this item should be built in current shard"""
        if self.shard_total == 1:
            return True
        return index % self.shard_total == self.shard_index
    
    def throttle(self):
        """Throttle API requests"""
        time.sleep(self.config['build']['throttle_ms'] / 1000.0)
    
    def api_request(self, url, **kwargs):
        """Make API request with retry logic"""
        max_retries = 1
        retry_delay = self.config['build']['retry_delay_ms'] / 1000.0
        
        for attempt in range(max_retries + 1):
            try:
                response = self.session.get(url, timeout=10, **kwargs)
                if response.status_code == 429:  # Rate limited
                    if attempt < max_retries:
                        print(f"Rate limited, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise Exception(f"Rate limited (HTTP 429)")
                
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    print(f"Request failed, retrying: {e}")
                    time.sleep(retry_delay)
                else:
                    raise Exception(f"API request failed: {e}")
    
    def get_asset_prefix(self, depth):
        """Calculate asset prefix based on page depth"""
        return "../" * depth if depth > 0 else ""
    
    def render_template(self, template_name, context, output_path):
        """Render Jinja2 template to file"""
        template = self.jinja_env.get_template(template_name)
        content = template.render(**context)
        
        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def render_page(self, title, content, depth=0, layout=None):
        """Render a complete page using base template"""
        context = {
            'title': title,
            'content': content,
            'generated_at': self.generated_at,
            'asset_prefix': self.get_asset_prefix(depth),
            'layout': layout
        }
        return self.jinja_env.get_template('base.html').render(**context)
    
    def render_card(self, module_type, title=None, subtitle=None, content="", footer=None):
        """Render a module card"""
        context = {
            'module_type': module_type,
            'title': title,
            'subtitle': subtitle,
            'content': content,
            'footer': footer
        }
        return self.jinja_env.get_template('module_card.html').render(**context)
    
    def build_home(self):
        """Build home page"""
        print("Building home page...")
        
        content = f"""
        <div class="cards-grid">
            {self.render_card('home', 'Weather', 'City forecasts and conditions', 
                '<a href="city/index.html">Browse Cities →</a>')}
            {self.render_card('home', 'Cryptocurrency', 'Live crypto prices', 
                '<a href="crypto/index.html">View Crypto →</a>')}
            {self.render_card('home', 'Stocks', 'US stock market data', 
                '<a href="stocks/index.html">View Stocks →</a>')}
        </div>
        """
        
        page_content = self.render_page("Home - Postcard Dashboard", content)
        with open(DIST_DIR / "index.html", 'w') as f:
            f.write(page_content)
    
    def geocode_city(self, city_name):
        """Geocode city name to lat/lon using Open-Meteo"""
        try:
            url = self.config['apis']['open_meteo_geocoding']
            params = {'name': city_name, 'count': 1, 'language': 'en', 'format': 'json'}
            
            response = self.api_request(url, params=params)
            data = response.json()
            
            if data.get('results'):
                result = data['results'][0]
                return {
                    'latitude': result['latitude'],
                    'longitude': result['longitude'],
                    'name': result['name'],
                    'country': result.get('country', ''),
                }
            return None
        except Exception as e:
            print(f"Geocoding failed for {city_name}: {e}")
            return None
    
    def fetch_weather(self, latitude, longitude, units='celsius'):
        """Fetch weather data from Open-Meteo"""
        try:
            url = self.config['apis']['open_meteo_forecast']
            temp_unit = 'fahrenheit' if units == 'fahrenheit' else 'celsius'
            params = {
                'latitude': latitude,
                'longitude': longitude,
                'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code',
                'daily': 'temperature_2m_max,temperature_2m_min',
                'temperature_unit': temp_unit,
                'wind_speed_unit': 'mph',
                'precipitation_unit': 'inch',
                'timezone': 'auto'
            }
            
            response = self.api_request(url, params=params)
            data = response.json()
            
            current = data.get('current', {})
            daily = data.get('daily', {})
            
            temp_unit_symbol = '°F' if units == 'fahrenheit' else '°C'
            
            return {
                'current_temp': f"{current.get('temperature_2m', '—')}{temp_unit_symbol}",
                'humidity': f"{current.get('relative_humidity_2m', '—')}%",
                'wind_speed': f"{current.get('wind_speed_10m', '—')} mph",
                'high_temp': f"{daily.get('temperature_2m_max', ['—'])[0]}{temp_unit_symbol}",
                'low_temp': f"{daily.get('temperature_2m_min', ['—'])[0]}{temp_unit_symbol}",
            }
        except Exception as e:
            print(f"Weather fetch failed for {latitude}, {longitude}: {e}")
            return {
                'current_temp': '—',
                'humidity': '—',
                'wind_speed': '—',
                'high_temp': '—',
                'low_temp': '—'
            }
    
    def build_cities(self):
        """Build cities pages"""
        if not self.should_build_shard(0, 4):  # Cities are shard 0
            return
        
        print("Building cities pages...")
        cities = self.load_cities()
        
        # Build city index
        rows = []
        for i, city in enumerate(cities):
            if not self.should_build_shard(i, len(cities)):
                continue
            
            rows.append(f"""
                <tr>
                    <td><a href="{city['slug']}/index.html">{city['name']}</a></td>
                    <td>{city.get('country', '—')}</td>
                </tr>
            """)
        
        table_content = f"""
        <table>
            <thead>
                <tr><th>City</th><th>Country</th></tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """
        
        list_template = self.jinja_env.get_template('list.html')
        list_content = list_template.render(
            title="Cities",
            searchable=True,
            search_placeholder="cities",
            content=table_content
        )
        
        page_content = self.render_page("Cities - Postcard Dashboard", list_content, depth=1, layout='list')
        city_index_path = DIST_DIR / "city" / "index.html"
        city_index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(city_index_path, 'w') as f:
            f.write(page_content)
        
        # Build individual city pages
        for i, city in enumerate(cities):
            if not self.should_build_shard(i, len(cities)):
                continue
                
            self.build_city_page(city)
            self.throttle()
    
    def build_city_page(self, city):
        """Build individual city page"""
        # Geocode if needed
        if 'latitude' not in city or 'longitude' not in city:
            geo_data = self.geocode_city(f"{city['city']}, {city.get('country', '')}")
            if geo_data:
                city.update(geo_data)
        
        # Fetch weather
        weather_data = {}
        if 'latitude' in city and 'longitude' in city:
            weather_data = self.fetch_weather(city['latitude'], city['longitude'])
        
        # Render weather card
        weather_content = f"""
        <div class="weather-stat">
            <span class="value">{weather_data.get('current_temp', '—')}</span>
            <span class="label">Current</span>
        </div>
        <div class="weather-stat">
            <span class="value">{weather_data.get('high_temp', '—')}</span>
            <span class="label">High</span>
        </div>
        <div class="weather-stat">
            <span class="value">{weather_data.get('low_temp', '—')}</span>
            <span class="label">Low</span>
        </div>
        <div class="weather-stat">
            <span class="value">{weather_data.get('wind_speed', '—')}</span>
            <span class="label">Wind</span>
        </div>
        <div class="weather-stat">
            <span class="value">{weather_data.get('humidity', '—')}</span>
            <span class="label">Humidity</span>
        </div>
        """
        
        card_content = self.render_card(
            'weather',
            title=city['name'],
            subtitle=city.get('country', ''),
            content=weather_content
        )
        
        page_content = self.render_page(f"{city['name']} Weather", card_content, depth=2)
        city_path = DIST_DIR / "city" / city['slug'] / "index.html"
        city_path.parent.mkdir(parents=True, exist_ok=True)
        with open(city_path, 'w') as f:
            f.write(page_content)
    
    def build_crypto(self):
        """Build crypto pages"""
        if not self.should_build_shard(1, 4):  # Crypto is shard 1
            return
            
        print("Building crypto pages...")
        coins = self.load_coins()
        
        # Fetch prices in chunks
        prices = self.fetch_crypto_prices(coins)
        
        # Build crypto index
        rows = []
        for coin in coins:
            price = prices.get(coin, {})
            price_usd = price.get('usd', '—')
            if isinstance(price_usd, (int, float)):
                price_usd = f"${price_usd:,.2f}"
            
            rows.append(f"""
                <tr>
                    <td><a href="{coin}.html">{coin}</a></td>
                    <td>{price_usd}</td>
                </tr>
            """)
        
        table_content = f"""
        <table>
            <thead>
                <tr><th>Coin</th><th>Price (USD)</th></tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """
        
        list_template = self.jinja_env.get_template('list.html')
        list_content = list_template.render(
            title="Cryptocurrency",
            searchable=True,
            search_placeholder="coins",
            content=table_content
        )
        
        page_content = self.render_page("Crypto - Postcard Dashboard", list_content, depth=1, layout='list')
        crypto_index_path = DIST_DIR / "crypto" / "index.html"
        crypto_index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(crypto_index_path, 'w') as f:
            f.write(page_content)
        
        # Build individual coin pages
        for coin in coins:
            self.build_crypto_page(coin, prices.get(coin, {}))
    
    def build_crypto_page(self, coin, price_data):
        """Build individual crypto page"""
        price_usd = price_data.get('usd', '—')
        if isinstance(price_usd, (int, float)):
            price_usd = f"${price_usd:,.2f}"
        
        content = f"""
        <div class="weather-stat">
            <span class="value">{price_usd}</span>
            <span class="label">USD Price</span>
        </div>
        """
        
        card_content = self.render_card(
            'crypto',
            title=coin.title(),
            content=content
        )
        
        page_content = self.render_page(f"{coin.title()} Price", card_content, depth=1)
        crypto_path = DIST_DIR / "crypto" / f"{coin}.html"
        with open(crypto_path, 'w') as f:
            f.write(page_content)
    
    def fetch_crypto_prices(self, coins):
        """Fetch crypto prices from CoinGecko API"""
        prices = {}
        chunk_size = self.config['build']['chunk_sizes']['crypto']
        
        for i in range(0, len(coins), chunk_size):
            chunk = coins[i:i + chunk_size]
            try:
                url = self.config['apis']['coingecko_price']
                params = {
                    'ids': ','.join(chunk),
                    'vs_currencies': 'usd'
                }
                
                response = self.api_request(url, params=params)
                data = response.json()
                prices.update(data)
                
                self.throttle()
            except Exception as e:
                print(f"Failed to fetch crypto prices for chunk {i//chunk_size + 1}: {e}")
        
        return prices
    
    def build_stocks(self):
        """Build stocks pages"""
        if not self.should_build_shard(2, 4):  # Stocks is shard 2
            return
            
        print("Building stocks pages...")
        tickers = self.load_stocks()
        
        # Fetch prices
        prices = self.fetch_stock_prices(tickers)
        
        # Build stocks index
        rows = []
        for ticker in tickers:
            data = prices.get(ticker, {})
            price = data.get('close', '—')
            if isinstance(price, (int, float)):
                price = f"${price:.2f}"
            
            rows.append(f"""
                <tr>
                    <td><a href="{ticker}.html">{ticker}</a></td>
                    <td>{price}</td>
                    <td>{data.get('date', '—')}</td>
                </tr>
            """)
        
        table_content = f"""
        <table>
            <thead>
                <tr><th>Ticker</th><th>Close</th><th>Date</th></tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """
        
        list_template = self.jinja_env.get_template('list.html')
        list_content = list_template.render(
            title="Stocks",
            searchable=True,
            search_placeholder="stocks",
            content=table_content
        )
        
        page_content = self.render_page("Stocks - Postcard Dashboard", list_content, depth=1, layout='list')
        stocks_index_path = DIST_DIR / "stocks" / "index.html"
        stocks_index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(stocks_index_path, 'w') as f:
            f.write(page_content)
        
        # Build individual stock pages
        for ticker in tickers:
            self.build_stock_page(ticker, prices.get(ticker, {}))
    
    def build_stock_page(self, ticker, stock_data):
        """Build individual stock page"""
        close = stock_data.get('close', '—')
        if isinstance(close, (int, float)):
            close = f"${close:.2f}"
        
        change = stock_data.get('change', 0)
        change_class = 'pos' if change >= 0 else 'neg' if change < 0 else 'neu'
        change_text = f"+{change:.2f}" if change > 0 else f"{change:.2f}" if change < 0 else "0.00"
        
        content = f"""
        <div class="weather-stat">
            <span class="value">{close}</span>
            <span class="label">Close</span>
        </div>
        <div class="weather-stat">
            <span class="value">{stock_data.get('date', '—')}</span>
            <span class="label">Date</span>
        </div>
        <div class="weather-stat">
            <span class="value"><span class="badge {change_class}">{change_text}</span></span>
            <span class="label">Change</span>
        </div>
        """
        
        card_content = self.render_card(
            'stocks',
            title=ticker,
            content=content
        )
        
        page_content = self.render_page(f"{ticker} Stock", card_content, depth=1)
        stock_path = DIST_DIR / "stocks" / f"{ticker}.html"
        with open(stock_path, 'w') as f:
            f.write(page_content)
    
    def fetch_stock_prices(self, tickers):
        """Fetch stock prices from Stooq"""
        prices = {}
        chunk_size = self.config['build']['chunk_sizes']['stocks']
        
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i:i + chunk_size]
            
            for ticker in chunk:
                try:
                    # Map ticker to stooq format
                    stooq_ticker = ticker.lower()
                    if '.' not in stooq_ticker:
                        stooq_ticker += '.us'
                    
                    url = self.config['apis']['stooq_base'].format(stooq_ticker)
                    response = self.api_request(url)
                    
                    # Parse CSV response
                    lines = response.text.strip().split('\n')
                    if len(lines) >= 2:
                        headers = lines[0].split(',')
                        values = lines[1].split(',')
                        
                        data = dict(zip(headers, values))
                        
                        close_price = float(data.get('Close', 0))
                        open_price = float(data.get('Open', 0))
                        change = close_price - open_price
                        
                        prices[ticker] = {
                            'close': close_price,
                            'open': open_price,
                            'change': change,
                            'date': data.get('Date', '—'),
                            'volume': data.get('Volume', '—')
                        }
                    
                    self.throttle()
                except Exception as e:
                    print(f"Failed to fetch stock price for {ticker}: {e}")
                    prices[ticker] = {}
        
        return prices
    
    def build_users(self):
        """Build user-specific pages"""
        if not self.should_build_shard(3, 4):  # Users are shard 3
            return
            
        print("Building user pages...")
        users = self.load_users()
        
        for username, config in users.items():
            self.build_user_page(username, config)
            self.build_user_api(username, config)
            self.throttle()
    
    def build_user_page(self, username, user_config):
        """Build individual user page"""
        cards = []
        
        # Weather card
        if 'weather' in user_config:
            weather_card = self.build_user_weather_card(user_config['weather'])
            if weather_card:
                cards.append(weather_card)
        
        # Crypto card
        if 'crypto' in user_config:
            crypto_card = self.build_user_crypto_card(user_config['crypto'])
            if crypto_card:
                cards.append(crypto_card)
        
        # Stocks card
        if 'stocks' in user_config:
            stocks_card = self.build_user_stocks_card(user_config['stocks'])
            if stocks_card:
                cards.append(stocks_card)
        
        # Transit card
        if 'transit' in user_config and 'api_url' in user_config['transit']:
            transit_card = self.build_user_transit_card(user_config['transit'])
            if transit_card:
                cards.append(transit_card)
        
        content = f'<div class="cards-grid">{"".join(cards)}</div>'
        
        # Add transit script if needed
        if 'transit' in user_config and 'api_url' in user_config['transit']:
            content += f'''
            <script src="../../static/transit.js" 
                    data-target=".transit .card-content" 
                    data-api="{user_config['transit']['api_url']}"></script>
            '''
        
        page_content = self.render_page(f"{username.title()} Dashboard", content, depth=2)
        user_path = DIST_DIR / "u" / username / "index.html"
        user_path.parent.mkdir(parents=True, exist_ok=True)
        with open(user_path, 'w') as f:
            f.write(page_content)
    
    def build_user_weather_card(self, weather_config):
        """Build weather card for user"""
        try:
            # Get coordinates
            if 'latitude' in weather_config and 'longitude' in weather_config:
                lat, lon = weather_config['latitude'], weather_config['longitude']
                location_name = f"{lat:.2f}, {lon:.2f}"
            elif 'city' in weather_config:
                geo_data = self.geocode_city(weather_config['city'])
                if not geo_data:
                    return None
                lat, lon = geo_data['latitude'], geo_data['longitude']
                location_name = geo_data['name']
            else:
                return None
            
            # Fetch weather
            units = weather_config.get('units', 'celsius')
            weather_data = self.fetch_weather(lat, lon, units)
            
            content = f"""
            <div class="weather-stat">
                <span class="value">{weather_data.get('current_temp', '—')}</span>
                <span class="label">Current</span>
            </div>
            <div class="weather-stat">
                <span class="value">{weather_data.get('high_temp', '—')}</span>
                <span class="label">High</span>
            </div>
            <div class="weather-stat">
                <span class="value">{weather_data.get('low_temp', '—')}</span>
                <span class="label">Low</span>
            </div>
            <div class="weather-stat">
                <span class="value">{weather_data.get('wind_speed', '—')}</span>
                <span class="label">Wind</span>
            </div>
            """
            
            return self.render_card('weather', title='Weather', subtitle=location_name, content=content)
        except Exception as e:
            print(f"Error building weather card: {e}")
            return None
    
    def build_user_crypto_card(self, crypto_config):
        """Build crypto card for user"""
        try:
            coins = crypto_config.get('coins', [])
            if not coins:
                return None
            
            prices = self.fetch_crypto_prices(coins)
            vs_currency = crypto_config.get('vs_currency', 'usd').lower()
            
            rows = []
            for coin in coins:
                price_data = prices.get(coin, {})
                price = price_data.get(vs_currency, '—')
                if isinstance(price, (int, float)):
                    symbol = '$' if vs_currency == 'usd' else vs_currency.upper()
                    price = f"{symbol}{price:,.2f}"
                
                rows.append(f"<tr><td>{coin}</td><td>{price}</td></tr>")
            
            content = f"""
            <table>
                <thead><tr><th>Coin</th><th>Price</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
            """
            
            return self.render_card('crypto', title='Cryptocurrency', content=content)
        except Exception as e:
            print(f"Error building crypto card: {e}")
            return None
    
    def build_user_stocks_card(self, stocks_config):
        """Build stocks card for user"""
        try:
            tickers = stocks_config.get('tickers', [])
            if not tickers:
                return None
            
            prices = self.fetch_stock_prices(tickers)
            
            rows = []
            for ticker in tickers:
                data = prices.get(ticker, {})
                close = data.get('close', '—')
                if isinstance(close, (int, float)):
                    close = f"${close:.2f}"
                
                change = data.get('change', 0)
                change_class = 'pos' if change >= 0 else 'neg' if change < 0 else 'neu'
                change_text = f"+{change:.2f}" if change > 0 else f"{change:.2f}" if change < 0 else "0.00"
                
                rows.append(f"""
                    <tr>
                        <td>{ticker}</td>
                        <td>{close}</td>
                        <td><span class="badge {change_class}">{change_text}</span></td>
                    </tr>
                """)
            
            content = f"""
            <table>
                <thead><tr><th>Ticker</th><th>Close</th><th>Change</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
            """
            
            return self.render_card('stocks', title='Stocks', content=content)
        except Exception as e:
            print(f"Error building stocks card: {e}")
            return None
    
    def build_user_transit_card(self, transit_config):
        """Build transit card for user"""
        content = '<div class="transit-loading">Loading transit data...</div>'
        return self.render_card('transit', title='Transit', content=content)
    
    def build_user_api(self, username, user_config):
        """Build user API JSON feed"""
        api_data = {'updated_at': self.generated_at}
        
        # Weather data
        if 'weather' in user_config:
            try:
                if 'latitude' in user_config['weather'] and 'longitude' in user_config['weather']:
                    lat, lon = user_config['weather']['latitude'], user_config['weather']['longitude']
                elif 'city' in user_config['weather']:
                    geo_data = self.geocode_city(user_config['weather']['city'])
                    if geo_data:
                        lat, lon = geo_data['latitude'], geo_data['longitude']
                    else:
                        lat, lon = None, None
                else:
                    lat, lon = None, None
                
                if lat and lon:
                    units = user_config['weather'].get('units', 'celsius')
                    weather_data = self.fetch_weather(lat, lon, units)
                    api_data['weather'] = weather_data
            except Exception as e:
                print(f"Error fetching weather for API: {e}")
        
        # Crypto data
        if 'crypto' in user_config:
            try:
                coins = user_config['crypto'].get('coins', [])
                if coins:
                    prices = self.fetch_crypto_prices(coins)
                    vs_currency = user_config['crypto'].get('vs_currency', 'usd')
                    api_data['crypto'] = {coin: prices.get(coin, {}).get(vs_currency) for coin in coins}
            except Exception as e:
                print(f"Error fetching crypto for API: {e}")
        
        # Stocks data
        if 'stocks' in user_config:
            try:
                tickers = user_config['stocks'].get('tickers', [])
                if tickers:
                    prices = self.fetch_stock_prices(tickers)
                    api_data['stocks'] = {ticker: prices.get(ticker, {}) for ticker in tickers}
            except Exception as e:
                print(f"Error fetching stocks for API: {e}")
        
        # Todo data
        try:
            todo_file = DATA_DIR / "todo.json"
            if todo_file.exists():
                with open(todo_file, 'r') as f:
                    api_data['todo'] = json.load(f)
        except Exception as e:
            print(f"Error loading todo data: {e}")
        
        api_path = DIST_DIR / "api" / f"{username}.json"
        api_path.parent.mkdir(parents=True, exist_ok=True)
        with open(api_path, 'w') as f:
            json.dump(api_data, f, indent=2)
    
    def copy_static_assets(self):
        """Copy static assets to dist directory"""
        print("Copying static assets...")
        static_dist = DIST_DIR / "static"
        if static_dist.exists():
            shutil.rmtree(static_dist)
        shutil.copytree(STATIC_DIR, static_dist)
    
    def load_cities(self):
        """Load cities from CSV"""
        cities = []
        try:
            with open(DATA_DIR / "cities.csv", 'r') as f:
                reader = csv.DictReader(f)
                cities = list(reader)
        except Exception as e:
            print(f"Error loading cities: {e}")
        return cities
    
    def load_coins(self):
        """Load coin IDs from text file"""
        coins = []
        try:
            with open(DATA_DIR / "coins.txt", 'r') as f:
                coins = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error loading coins: {e}")
        return coins
    
    def load_stocks(self):
        """Load stock tickers from text file"""
        stocks = []
        try:
            with open(DATA_DIR / "stocks.txt", 'r') as f:
                stocks = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error loading stocks: {e}")
        return stocks
    
    def load_users(self):
        """Load users from YAML"""
        try:
            with open(DATA_DIR / "users.yaml", 'r') as f:
                data = yaml.safe_load(f)
                return data.get('users', {})
        except Exception as e:
            print(f"Error loading users: {e}")
            return {}
    
    def build(self):
        """Build the entire site"""
        print("Starting build...")
        print(f"Shard {self.shard_index + 1} of {self.shard_total}")
        
        # Create dist directory
        DIST_DIR.mkdir(exist_ok=True)
        
        # Copy static assets (only in shard 0 or when not sharded)
        if self.shard_index == 0:
            self.copy_static_assets()
        
        # Build pages
        if self.shard_index == 0 or self.shard_total == 1:
            self.build_home()
        
        self.build_cities()
        self.build_crypto()
        self.build_stocks()
        self.build_users()
        
        print("Build complete!")

def main():
    builder = SiteBuilder()
    try:
        builder.build()
        return 0
    except KeyboardInterrupt:
        print("\nBuild interrupted")
        return 1
    except Exception as e:
        print(f"Build failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())