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
    
    def render_page(self, title, content, depth=0, layout=None, breadcrumb=None):
        """Render a complete page using base template"""
        context = {
            'title': title,
            'content': content,
            'generated_at': self.generated_at,
            'asset_prefix': self.get_asset_prefix(depth),
            'layout': layout,
            'breadcrumb': breadcrumb
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
        """Build home page with live data tiles"""
        print("Building home page...")
        
        # Get sample data for preview tiles
        live_tiles_content = self.build_home_live_tiles()
        
        # Navigation cards
        nav_cards = f"""
        <div class="cards-grid">
            {self.render_card('home', 'Weather', 'City forecasts and conditions', 
                '<a href="city/index.html">Browse Cities →</a>')}
            {self.render_card('home', 'Cryptocurrency', 'Live crypto prices', 
                '<a href="crypto/index.html">View Crypto →</a>')}
            {self.render_card('home', 'Stocks', 'US stock market data', 
                '<a href="stocks/index.html">View Stocks →</a>')}
        </div>
        """
        
        content = live_tiles_content + nav_cards
        
        page_content = self.render_page("Home - Postcard Dashboard", content)
        with open(DIST_DIR / "index.html", 'w') as f:
            f.write(page_content)
    
    def build_home_live_tiles(self):
        """Build live preview tiles for homepage using configured user preferences"""
        tiles_html = '<div class="live-tiles">'
        
        # Get configured homepage user
        users = self.load_users()
        homepage_user = self.config.get('site', {}).get('homepage_user', 'demo')
        user_config = users.get(homepage_user)
        
        if not user_config:
            # Fallback to first user if configured user doesn't exist
            if users:
                homepage_user = list(users.keys())[0]
                user_config = users[homepage_user]
        
        if user_config:
            # Weather tile with user's preferred location
            weather_tile = self.build_home_weather_tile(user_config, homepage_user)
            if weather_tile:
                tiles_html += weather_tile
            
            # Personal movers tile with user's preferred stocks/crypto
            personal_movers_tile = self.build_home_personal_movers_tile(user_config, homepage_user)
            if personal_movers_tile:
                tiles_html += personal_movers_tile
        else:
            # Fallback to global data if no users configured
            global_movers_tile = self.build_home_movers_tile()
            if global_movers_tile:
                tiles_html += global_movers_tile
        
        tiles_html += '</div>'
        return tiles_html
    
    def build_home_weather_tile(self, user_config, username):
        """Build weather preview tile for homepage"""
        if not user_config or 'weather' not in user_config:
            return ""
        
        try:
            weather_config = user_config['weather']
            
            # Get coordinates
            if 'latitude' in weather_config and 'longitude' in weather_config:
                lat, lon = weather_config['latitude'], weather_config['longitude']
                location_name = f"{lat:.2f}, {lon:.2f}"
            elif 'city' in weather_config:
                geo_data = self.geocode_city(weather_config['city'])
                if not geo_data:
                    return ""
                lat, lon = geo_data['latitude'], geo_data['longitude']
                location_name = geo_data['name']
            else:
                return ""
            
            # Fetch weather
            units = weather_config.get('units', 'celsius')
            weather_data = self.fetch_weather(lat, lon, units)
            
            current_temp = weather_data.get('current_temp') or "—"
            summary = weather_data.get('summary', 'Weather data unavailable')
            
            content = f"""
            <div class="tile-content">
                <div class="tile-main">
                    <span class="tile-value">{current_temp}</span>
                    <span class="tile-location">{location_name}</span>
                </div>
                <div class="tile-summary">{summary}</div>
            </div>
            """
            
            title = f"{username.title()}'s Weather"
            return self.render_card('weather-tile', title, content=content)
            
        except Exception as e:
            print(f"Error building weather tile: {e}")
            return ""
    
    def build_home_personal_movers_tile(self, user_config, username):
        """Build personalized movers tile showing user's preferred stocks/crypto"""
        try:
            movers_list = []
            
            # Get user's crypto preferences
            if 'crypto' in user_config:
                user_coins = user_config['crypto'].get('coins', [])[:5]  # Limit to 5
                if user_coins:
                    crypto_prices = self.fetch_crypto_prices(user_coins)
                    
                    # Find best performer from user's coins
                    best_crypto = None
                    best_change = -999
                    for coin_id in user_coins:
                        if coin_id in crypto_prices:
                            change = crypto_prices[coin_id].get('price_change_24h')
                            if change is not None and change > best_change:
                                best_change = change
                                best_crypto = (coin_id, crypto_prices[coin_id])
                    
                    if best_crypto:
                        coin_id, coin_data = best_crypto
                        name = coin_data.get('name', coin_id.title())
                        change = coin_data.get('price_change_24h', 0)
                        if change is not None:
                            symbol = "🚀" if change > 0 else "📉" if change < 0 else "—"
                            movers_list.append(f"{symbol} {name}: {change:+.1f}%")
                        else:
                            movers_list.append(f"— {name}: no data")
            
            # Get user's stock preferences  
            if 'stocks' in user_config:
                user_tickers = user_config['stocks'].get('tickers', [])[:5]  # Limit to 5
                if user_tickers:
                    stock_prices = self.fetch_stock_prices(user_tickers)
                    
                    # Find best performer from user's stocks
                    best_stock = None
                    best_change_pct = -999
                    for ticker in user_tickers:
                        if ticker in stock_prices:
                            data = stock_prices[ticker]
                            change = data.get('change')
                            if change is not None and data.get('close'):
                                change_pct = (change / (data['close'] - change)) * 100 if (data['close'] - change) != 0 else 0
                                if abs(change_pct) > abs(best_change_pct):
                                    best_change_pct = change_pct
                                    best_stock = (ticker, data, change_pct)
                    
                    if best_stock:
                        ticker, stock_data, change_pct = best_stock
                        symbol = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "—"
                        movers_list.append(f"{symbol} {ticker}: {change_pct:+.1f}%")
            
            if not movers_list:
                movers_list = [f"{username.title()}'s portfolio loading..."]
            
            content = f"""
            <div class="tile-content">
                <div class="movers-preview">
                    {'<br>'.join(movers_list)}
                </div>
                <div class="tile-footer">
                    <a href="u/{username}/index.html">View {username.title()}'s dashboard →</a>
                </div>
            </div>
            """
            
            title = f"{username.title()}'s Top Movers"
            return self.render_card('movers-tile', title, content=content)
            
        except Exception as e:
            print(f"Error building personal movers tile: {e}")
            return ""
    
    def build_home_movers_tile(self):
        """Build top movers preview tile for homepage"""
        try:
            # Get sample of top coins and stocks
            coins = self.load_coins()[:10]  # Just top 10 for preview
            stocks = self.load_stocks()[:10]  # Just top 10 for preview
            
            # Fetch sample data (minimal API calls)
            crypto_prices = self.fetch_crypto_prices(coins)
            stock_prices = self.fetch_stock_prices(stocks)
            
            # Get top movers
            crypto_gainers, _ = self.get_crypto_top_movers(crypto_prices)
            
            # Get stock movers  
            stock_movers = []
            for ticker, data in stock_prices.items():
                change = data.get('change')
                if change is not None and data.get('close') and change != 0:
                    change_pct = (change / (data['close'] - change)) * 100 if (data['close'] - change) != 0 else 0
                    stock_movers.append((ticker, data, change_pct))
            
            stock_movers.sort(key=lambda x: abs(x[2]), reverse=True)  # Sort by absolute change
            
            # Build preview content
            movers_list = []
            
            # Add top crypto gainer
            if crypto_gainers:
                coin_id, coin_data = crypto_gainers[0]
                name = coin_data.get('name', coin_id.title())
                change = coin_data.get('price_change_24h', 0)
                movers_list.append(f"🚀 {name}: +{change:.1f}%")
            
            # Add top stock mover
            if stock_movers:
                ticker, stock_data, change_pct = stock_movers[0]
                symbol = "📈" if change_pct > 0 else "📉"
                movers_list.append(f"{symbol} {ticker}: {change_pct:+.1f}%")
            
            if not movers_list:
                movers_list = ["Market data loading..."]
            
            content = f"""
            <div class="tile-content">
                <div class="movers-preview">
                    {'<br>'.join(movers_list)}
                </div>
                <div class="tile-footer">
                    <a href="crypto/index.html">View all crypto →</a> | 
                    <a href="stocks/index.html">View all stocks →</a>
                </div>
            </div>
            """
            
            return self.render_card('movers-tile', 'Top Movers', content=content)
            
        except Exception as e:
            print(f"Error building movers tile: {e}")
            return ""
    
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
    
    def get_weather_cache_path(self, latitude, longitude):
        """Get cache file path for weather data"""
        cache_dir = DIST_DIR / "cache" / "weather"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{latitude}_{longitude}.json"
    
    def load_cached_weather(self, latitude, longitude):
        """Load cached weather data if available"""
        try:
            cache_path = self.get_weather_cache_path(latitude, longitude)
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                    # Check if cache is less than 6 hours old
                    cache_time = datetime.fromisoformat(cached_data.get('cached_at', ''))
                    age_hours = (datetime.now(timezone.utc) - cache_time).total_seconds() / 3600
                    if age_hours < 6:
                        return cached_data.get('data'), False  # Fresh cache
                    else:
                        return cached_data.get('data'), True   # Stale cache
            return None, False
        except Exception as e:
            print(f"Error loading weather cache: {e}")
            return None, False
    
    def save_weather_cache(self, latitude, longitude, weather_data):
        """Save weather data to cache"""
        try:
            cache_path = self.get_weather_cache_path(latitude, longitude)
            cache_data = {
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'data': weather_data
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"Error saving weather cache: {e}")
    
    def fetch_weather(self, latitude, longitude, units='celsius'):
        """Fetch weather data from Open-Meteo with caching and retry"""
        # Try cache first
        cached_data, is_stale = self.load_cached_weather(latitude, longitude)
        
        # Attempt to fetch fresh data with retry
        fresh_data = None
        for attempt in range(2):  # Try twice
            try:
                url = self.config['apis']['open_meteo_forecast']
                temp_unit = 'fahrenheit' if units == 'fahrenheit' else 'celsius'
                params = {
                    'latitude': latitude,
                    'longitude': longitude,
                    'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code',
                    'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
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
                
                # Enhanced weather data with precipitation and summary
                current_temp = current.get('temperature_2m')
                high_temp = daily.get('temperature_2m_max', [None])[0] if daily.get('temperature_2m_max') else None
                low_temp = daily.get('temperature_2m_min', [None])[0] if daily.get('temperature_2m_min') else None
                precip_prob = daily.get('precipitation_probability_max', [None])[0] if daily.get('precipitation_probability_max') else None
                
                # Format values
                current_temp_str = f"{current_temp:.0f}{temp_unit_symbol}" if current_temp is not None else None
                high_temp_str = f"{high_temp:.0f}{temp_unit_symbol}" if high_temp is not None else None
                low_temp_str = f"{low_temp:.0f}{temp_unit_symbol}" if low_temp is not None else None
                humidity_str = f"{current.get('relative_humidity_2m', 0):.0f}%" if current.get('relative_humidity_2m') is not None else None
                wind_str = f"{current.get('wind_speed_10m', 0):.0f} mph" if current.get('wind_speed_10m') is not None else None
                
                # Create summary
                summary_parts = []
                if high_temp_str and low_temp_str:
                    summary_parts.append(f"High {high_temp_str}, Low {low_temp_str}")
                if precip_prob is not None and precip_prob > 0:
                    summary_parts.append(f"Chance of rain {precip_prob:.0f}%")
                summary = ", ".join(summary_parts) if summary_parts else "Clear conditions"
                
                fresh_data = {
                    'current_temp': current_temp_str,
                    'humidity': humidity_str,
                    'wind_speed': wind_str,
                    'high_temp': high_temp_str,
                    'low_temp': low_temp_str,
                    'precipitation_prob': f"{precip_prob:.0f}%" if precip_prob is not None else "0%",
                    'summary': summary,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'is_stale': False
                }
                
                # Save to cache
                self.save_weather_cache(latitude, longitude, fresh_data)
                return fresh_data
                
            except Exception as e:
                print(f"Weather fetch attempt {attempt + 1} failed for {latitude}, {longitude}: {e}")
                if attempt == 0:  # First attempt failed, wait before retry
                    time.sleep(2)
        
        # Fresh fetch failed, use cache if available
        if cached_data:
            print(f"Using cached weather data for {latitude}, {longitude} ({'stale' if is_stale else 'fresh'})")
            cached_data['is_stale'] = is_stale
            return cached_data
        
        # No cache available, return placeholder data
        print(f"No weather data available for {latitude}, {longitude}, using placeholders")
        return {
            'current_temp': None,
            'humidity': None,
            'wind_speed': None,
            'high_temp': None,
            'low_temp': None,
            'precipitation_prob': None,
            'summary': "Weather data unavailable",
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'is_stale': False
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
        
        # Render weather card with better formatting
        def format_value(value, fallback="no data"):
            return value if value is not None else f'<span class="badge neu">{fallback}</span>'
        
        # Create subtitle with stale indicator
        subtitle = city.get('country', '')
        if weather_data.get('is_stale'):
            subtitle += ' • <span class="badge neu">stale</span>'
        
        weather_content = f"""
        <div class="weather-summary">
            <p>{weather_data.get('summary', 'Weather data unavailable')}</p>
        </div>
        <div class="weather-stats">
            <div class="weather-stat">
                <span class="value">{format_value(weather_data.get('current_temp'))}</span>
                <span class="label">Current</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_value(weather_data.get('high_temp'))}</span>
                <span class="label">High</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_value(weather_data.get('low_temp'))}</span>
                <span class="label">Low</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_value(weather_data.get('precipitation_prob'))}</span>
                <span class="label">Rain chance</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_value(weather_data.get('wind_speed'))}</span>
                <span class="label">Wind</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_value(weather_data.get('humidity'))}</span>
                <span class="label">Humidity</span>
            </div>
        </div>
        """
        
        card_content = self.render_card(
            'weather',
            title=city['name'],
            subtitle=subtitle,
            content=weather_content
        )
        
        breadcrumb = f'<a href="../../index.html">Home</a> <span class="separator">›</span> <a href="../index.html">Cities</a> <span class="separator">›</span> {city["name"]}'
        page_content = self.render_page(f"{city['name']} Weather", card_content, depth=2, breadcrumb=breadcrumb)
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
        
        # Get top movers
        top_gainers, top_losers = self.get_crypto_top_movers(prices)
        
        # Build top movers section
        def format_change_badge(change):
            if change is None or change == 0:
                return '<span class="badge neu">0.00%</span>'
            elif change > 0:
                return f'<span class="badge pos">+{change:.2f}%</span>'
            else:
                return f'<span class="badge neg">{change:.2f}%</span>'
        
        top_movers_html = ""
        if top_gainers or top_losers:
            gainers_rows = []
            for coin_id, data in top_gainers[:3]:  # Show top 3
                name = data.get('name', coin_id.title())
                price = f"${data['usd']:,.2f}" if data['usd'] else "—"
                change = format_change_badge(data.get('price_change_24h'))
                gainers_rows.append(f'<tr><td><a href="{coin_id}.html">{name}</a></td><td>{price}</td><td>{change}</td></tr>')
            
            losers_rows = []
            for coin_id, data in top_losers[:3]:  # Show top 3
                name = data.get('name', coin_id.title())
                price = f"${data['usd']:,.2f}" if data['usd'] else "—"
                change = format_change_badge(data.get('price_change_24h'))
                losers_rows.append(f'<tr><td><a href="{coin_id}.html">{name}</a></td><td>{price}</td><td>{change}</td></tr>')
            
            top_movers_html = f"""
            <div class="top-movers">
                <div class="movers-section">
                    <h3>🚀 Top Gainers (24h)</h3>
                    <table class="compact">
                        <thead><tr><th>Coin</th><th>Price</th><th>Change</th></tr></thead>
                        <tbody>{''.join(gainers_rows)}</tbody>
                    </table>
                </div>
                <div class="movers-section">
                    <h3>📉 Top Losers (24h)</h3>
                    <table class="compact">
                        <thead><tr><th>Coin</th><th>Price</th><th>Change</th></tr></thead>
                        <tbody>{''.join(losers_rows)}</tbody>
                    </table>
                </div>
            </div>
            """
        
        # Build main crypto table with only coins that have valid prices
        rows = []
        valid_coins = [(coin, prices[coin]) for coin in coins if coin in prices and prices[coin].get('usd', 0) > 0]
        
        # Sort by market cap rank if available, otherwise by price
        valid_coins.sort(key=lambda x: x[1].get('market_cap_rank') or 999)
        
        for coin, data in valid_coins:
            name = data.get('name', coin.title())
            symbol = data.get('symbol', coin.upper())
            price_usd = f"${data['usd']:,.2f}" if data['usd'] else "—"
            change_24h = format_change_badge(data.get('price_change_24h'))
            
            rows.append(f"""
                <tr>
                    <td><a href="{coin}.html">{name}</a> <small>({symbol})</small></td>
                    <td>{price_usd}</td>
                    <td>{change_24h}</td>
                </tr>
            """)
        
        table_content = f"""
        {top_movers_html}
        <table>
            <thead>
                <tr><th>Coin</th><th>Price (USD)</th><th>24h Change</th></tr>
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
        if not price_data:
            return  # Skip coins with no data
            
        name = price_data.get('name', coin.title())
        symbol = price_data.get('symbol', coin.upper())
        price_usd = f"${price_data['usd']:,.2f}" if price_data.get('usd') else "No price data"
        
        change_24h = price_data.get('price_change_24h', 0)
        change_7d = price_data.get('price_change_7d', 0)
        
        def format_change(change):
            if change is None:
                return '<span class="badge neu">no data</span>'
            elif change > 0:
                return f'<span class="badge pos">+{change:.2f}%</span>'
            elif change < 0:
                return f'<span class="badge neg">{change:.2f}%</span>'
            else:
                return '<span class="badge neu">0.00%</span>'
        
        market_cap = price_data.get('market_cap', 0)
        market_cap_str = f"${market_cap:,.0f}" if market_cap > 0 else "Unknown"
        
        content = f"""
        <div class="weather-stats">
            <div class="weather-stat">
                <span class="value">{price_usd}</span>
                <span class="label">Current Price</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_change(change_24h)}</span>
                <span class="label">24h Change</span>
            </div>
            <div class="weather-stat">
                <span class="value">{format_change(change_7d)}</span>
                <span class="label">7d Change</span>
            </div>
            <div class="weather-stat">
                <span class="value">{market_cap_str}</span>
                <span class="label">Market Cap</span>
            </div>
        </div>
        """
        
        subtitle = f"${symbol}" if symbol else ""
        if price_data.get('market_cap_rank'):
            subtitle += f" • Rank #{price_data['market_cap_rank']}"
        
        card_content = self.render_card(
            'crypto',
            title=name,
            subtitle=subtitle,
            content=content
        )
        
        breadcrumb = f'<a href="../index.html">Home</a> <span class="separator">›</span> <a href="index.html">Crypto</a> <span class="separator">›</span> {name}'
        page_content = self.render_page(f"{name} ({symbol}) Price", card_content, depth=1, breadcrumb=breadcrumb)
        crypto_path = DIST_DIR / "crypto" / f"{coin}.html"
        with open(crypto_path, 'w') as f:
            f.write(page_content)
    
    def fetch_crypto_prices(self, coins):
        """Fetch crypto prices with market data from CoinGecko API"""
        prices = {}
        chunk_size = min(self.config['build']['chunk_sizes']['crypto'], 250)  # CoinGecko markets limit
        
        for i in range(0, len(coins), chunk_size):
            chunk = coins[i:i + chunk_size]
            try:
                # Use markets endpoint for richer data
                url = "https://api.coingecko.com/api/v3/coins/markets"
                params = {
                    'vs_currency': 'usd',
                    'ids': ','.join(chunk),
                    'order': 'market_cap_desc',
                    'per_page': len(chunk),
                    'page': 1,
                    'sparkline': 'false',
                    'price_change_percentage': '24h,7d'
                }
                
                response = self.api_request(url, params=params)
                data = response.json()
                
                # Convert array response to dict keyed by coin ID
                for coin_data in data:
                    coin_id = coin_data['id']
                    # Filter out coins with zero or null prices
                    if coin_data.get('current_price') and coin_data['current_price'] > 0:
                        prices[coin_id] = {
                            'usd': coin_data['current_price'],
                            'market_cap': coin_data.get('market_cap', 0),
                            'price_change_24h': coin_data.get('price_change_percentage_24h', 0),
                            'price_change_7d': coin_data.get('price_change_percentage_7d', 0),
                            'symbol': coin_data.get('symbol', '').upper(),
                            'name': coin_data.get('name', ''),
                            'market_cap_rank': coin_data.get('market_cap_rank', 0)
                        }
                
                self.throttle()
            except Exception as e:
                print(f"Failed to fetch crypto market data for chunk {i//chunk_size + 1}: {e}")
        
        return prices
    
    def get_crypto_top_movers(self, prices_data):
        """Get top gainers and losers from crypto data"""
        # Convert to list of tuples for sorting
        coins_with_change = []
        for coin_id, data in prices_data.items():
            if data.get('price_change_24h') is not None:
                coins_with_change.append((coin_id, data))
        
        # Sort by 24h change percentage (with null safety)
        coins_with_change.sort(key=lambda x: x[1].get('price_change_24h', 0), reverse=True)
        
        # Get top 5 gainers and losers
        top_gainers = coins_with_change[:5]
        top_losers = coins_with_change[-5:]
        top_losers.reverse()  # Show worst first
        
        return top_gainers, top_losers
    
    def build_stocks(self):
        """Build stocks pages"""
        if not self.should_build_shard(2, 4):  # Stocks is shard 2
            return
            
        print("Building stocks pages...")
        tickers = self.load_stocks()
        
        # Fetch prices
        prices = self.fetch_stock_prices(tickers)
        
        # Get top movers for stocks
        def get_stock_top_movers(prices_data):
            stocks_with_change = []
            for ticker, data in prices_data.items():
                change = data.get('change')
                if change is not None and data.get('close'):
                    change_pct = (change / (data['close'] - change)) * 100 if (data['close'] - change) != 0 else 0
                    stocks_with_change.append((ticker, data, change_pct))
            
            stocks_with_change.sort(key=lambda x: x[2], reverse=True)
            
            top_gainers = stocks_with_change[:5]
            top_losers = stocks_with_change[-5:]
            top_losers.reverse()
            
            return top_gainers, top_losers
        
        top_gainers, top_losers = get_stock_top_movers(prices)
        
        # Market status based on current time (simplified)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        # US market is roughly 9:30 AM to 4 PM ET (13:30 to 20:00 UTC on weekdays)
        is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6
        current_hour_utc = now.hour
        market_open = 13 <= current_hour_utc < 20 and not is_weekend
        market_status = "Open" if market_open else "Closed"
        market_date = now.strftime("%b %d")
        
        # Build top movers section
        def format_stock_change_badge(change, change_pct):
            if change is None or change == 0:
                return '<span class="badge neu">0.00%</span>'
            elif change > 0:
                return f'<span class="badge pos">+{change_pct:.2f}%</span>'
            else:
                return f'<span class="badge neg">{change_pct:.2f}%</span>'
        
        top_movers_html = ""
        if top_gainers or top_losers:
            gainers_rows = []
            for ticker, data, change_pct in top_gainers[:3]:
                price = f"${data['close']:.2f}" if data.get('close') else "—"
                change_badge = format_stock_change_badge(data.get('change'), change_pct)
                gainers_rows.append(f'<tr><td><a href="{ticker}.html">{ticker}</a></td><td>{price}</td><td>{change_badge}</td></tr>')
            
            losers_rows = []
            for ticker, data, change_pct in top_losers[:3]:
                price = f"${data['close']:.2f}" if data.get('close') else "—"
                change_badge = format_stock_change_badge(data.get('change'), change_pct)
                losers_rows.append(f'<tr><td><a href="{ticker}.html">{ticker}</a></td><td>{price}</td><td>{change_badge}</td></tr>')
            
            top_movers_html = f"""
            <div class="market-status">
                <span class="badge {'pos' if market_open else 'neu'}">Market {market_status} • {market_date}</span>
            </div>
            <div class="top-movers">
                <div class="movers-section">
                    <h3>🚀 Top Gainers</h3>
                    <table class="compact">
                        <thead><tr><th>Stock</th><th>Price</th><th>Change</th></tr></thead>
                        <tbody>{''.join(gainers_rows)}</tbody>
                    </table>
                </div>
                <div class="movers-section">
                    <h3>📉 Top Losers</h3>
                    <table class="compact">
                        <thead><tr><th>Stock</th><th>Price</th><th>Change</th></tr></thead>
                        <tbody>{''.join(losers_rows)}</tbody>
                    </table>
                </div>
            </div>
            """
        
        # Build main stocks table
        rows = []
        valid_stocks = [(ticker, data) for ticker, data in prices.items() if data.get('close')]
        
        for ticker, data in valid_stocks:
            price = f"${data['close']:.2f}" if data.get('close') else "—"
            change = data.get('change', 0)
            close_price = data.get('close', 0)
            change_pct = (change / (close_price - change)) * 100 if (close_price - change) != 0 and change is not None else 0
            change_badge = format_stock_change_badge(change, change_pct)
            date = data.get('date', '—')
            
            rows.append(f"""
                <tr>
                    <td><a href="{ticker}.html">{ticker}</a></td>
                    <td>{price}</td>
                    <td>{change_badge}</td>
                    <td>{date}</td>
                </tr>
            """)
        
        table_content = f"""
        {top_movers_html}
        <table>
            <thead>
                <tr><th>Ticker</th><th>Close</th><th>Change</th><th>Date</th></tr>
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
        
        breadcrumb = f'<a href="../index.html">Home</a> <span class="separator">›</span> <a href="index.html">Stocks</a> <span class="separator">›</span> {ticker}'
        page_content = self.render_page(f"{ticker} Stock", card_content, depth=1, breadcrumb=breadcrumb)
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