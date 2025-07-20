from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote
from datetime import datetime, timedelta
from typing import List
import subprocess
import yaml
import json
import os
import yfinance as yf
import gc
import psutil

app = FastAPI()

# ---- Caching Setup ----
ticker_cache = {}
CACHE_PATH = "ticker_cache.json"

def log_memory_usage(label=""):
    """Log current memory usage"""
    try:
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"Memory usage {label}: {memory_mb:.1f} MB")
    except:
        print(f"Memory check {label}: unable to measure")

def load_cache():
    global ticker_cache
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                ticker_cache = json.load(f)
        except Exception as e:
            print("Failed to load ticker cache:", e)
            ticker_cache = {}

def save_cache():
    with open(CACHE_PATH, "w") as f:
        json.dump(ticker_cache, f)

def fetch_company_info(ticker: str) -> dict:
    """Temporarily disabled yfinance API calls - using fallback data only"""
    if not ticker or not isinstance(ticker, str):
        return {"name": "Unknown", "industry": "Unknown"}

    ticker = ticker.upper()
    if ticker in ticker_cache:
        return ticker_cache[ticker]

    # TEMPORARILY DISABLED: Skip yfinance API calls for testing
    fallback = {"name": ticker, "industry": "General"}
    ticker_cache[ticker] = fallback
    save_cache()
    return fallback

def format_trade_size(amount_str):
    try:
        amount = float(amount_str)
    except (ValueError, TypeError):
        return "Unknown"

    if amount < 1_000:
        return "< 1K"
    elif amount < 15_000:
        return "1K–15K"
    elif amount < 50_000:
        return "15K–50K"
    elif amount < 100_000:
        return "50K–100K"
    elif amount < 250_000:
        return "100K–250K"
    elif amount < 500_000:
        return "250K–500K"
    elif amount < 1_000_000:
        return "500K–1M"
    elif amount < 5_000_000:
        return "1M–5M"
    elif amount < 25_000_000:
        return "5M–25M"
    elif amount < 50_000_000:
        return "25M–50M"
    else:
        return "50M+"

# Initialize global variables
congress_data = []
state_lookup = {}
bio_to_committees = {}

def get_committees(bioguide_id):
    return bio_to_committees.get(bioguide_id, [])

def load_current_legislators_only():
    """Load ONLY the current legislators file (smaller, safer)"""
    try:
        base_dir = os.path.dirname(__file__)
        filename = os.path.join(base_dir, "Backend/insider_dashboard/legislators-current.yaml")
        
        log_memory_usage("before current legislators")
        
        if os.path.exists(filename):
            file_size = os.path.getsize(filename) / 1024 / 1024  # MB
            print(f"Loading current legislators: {filename} ({file_size:.2f} MB)")
            
            with open(filename, "r") as f:
                data = yaml.safe_load(f)
                
            log_memory_usage("after loading current legislators")
            
            lookup = {}
            for person in data:
                bio_id = person.get("id", {}).get("bioguide")
                terms = person.get("terms", [])
                if bio_id and terms:
                    latest_term = terms[-1]
                    state = latest_term.get("state")
                    if state:
                        lookup[bio_id] = state
            
            # Clear loaded data immediately
            del data
            gc.collect()
            log_memory_usage("after processing current legislators")
            
            print(f"Loaded {len(lookup)} current legislators")
            return lookup
            
        else:
            print(f"Current legislators file not found: {filename}")
            return {}
            
    except Exception as e:
        print(f"Error loading current legislators: {e}")
        log_memory_usage("after error")
        return {}

@app.on_event("startup")
def startup_event():
    global congress_data, state_lookup, bio_to_committees
    
    log_memory_usage("startup begin")
    print("=== STARTUP WITH CURRENT LEGISLATORS ONLY ===")
    
    try:
        # Load cache
        load_cache()
        log_memory_usage("after cache")
        
        # Load ONLY current legislators (skip historical for now)
        state_lookup = load_current_legislators_only()
        log_memory_usage("after current legislators")
        
        # Keep everything else empty
        congress_data = []
        bio_to_committees = {}
        
        # Final cleanup
        gc.collect()
        log_memory_usage("final memory usage")
        
        print("=== STARTUP COMPLETE ===")
        
    except Exception as e:
        print(f"=== STARTUP ERROR: {e} ===")
        log_memory_usage("after error")
        congress_data = []
        state_lookup = {}
        bio_to_committees = {}

@app.on_event("shutdown")
def shutdown_event():
    save_cache()

@app.get("/")
def read_root():
    """Simple root endpoint for testing"""
    return {
        "message": "Congress Tracker API is running",
        "status": "success",
        "endpoints": {
            "health": "/health",
            "test": "/test",
            "docs": "/docs"
        }
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "message": "Service is running"}

@app.get("/test")
def test_endpoint():
    """Test endpoint showing loaded data"""
    return {
        "status": "success", 
        "message": "Congress tracker with current legislators only",
        "data_loaded": {
            "congress_records": len(congress_data) if congress_data else 0,
            "current_legislators": len(state_lookup) if state_lookup else 0,
            "committees": len(bio_to_committees) if bio_to_committees else 0
        },
        "sample_states": dict(list(state_lookup.items())[:5]) if state_lookup else {},
        "note": "Loading current legislators only to avoid memory issues"
    }

# Add this function after your other functions:

def load_congress_trading_data():
    """Load congress trading data with memory optimization"""
    try:
        log_memory_usage("before congress API call")
        
        # Set API token as environment variable for security
        api_token = os.getenv("QUIVER_API_TOKEN", "d95376201ee52332b90d7ab3e527076011921658")
        
        curl_command = [
            "curl",
            "-s",
            "--max-time", "45",  # Longer timeout for large dataset
            "--request", "GET",
            "--url", "https://api.quiverquant.com/beta/bulk/congresstrading",
            "--header", "Accept: application/json",
            "--header", f"Authorization: Bearer {api_token}"
        ]
        
        print("Fetching congress trading data from API...")
        result = subprocess.run(curl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
        
        if result.returncode != 0:
            print(f"API call failed with return code {result.returncode}")
            print(f"Error: {result.stderr}")
            return []
        
        log_memory_usage("after API call, before parsing")
        
        # Parse JSON
        try:
            full_data = json.loads(result.stdout)
            print(f"Raw API response: {len(full_data)} total records")
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            print(f"Response preview: {result.stdout[:500]}")
            return []
        
        log_memory_usage("after JSON parsing")
        
        # Filter to recent data only (last 2 years) to save memory
        cutoff_date = datetime.now() - timedelta(days=730)
        filtered_data = []
        
        for item in full_data:
            try:
                traded_str = item.get("Traded", "")
                if traded_str:
                    traded_date = datetime.strptime(traded_str, "%Y-%m-%d")
                    if traded_date >= cutoff_date:
                        filtered_data.append(item)
            except (ValueError, TypeError):
                continue  # Skip records with invalid dates
        
        # Clear the full dataset from memory immediately
        del full_data
        gc.collect()
        
        log_memory_usage("after filtering and cleanup")
        
        print(f"Filtered to {len(filtered_data)} records from last 2 years")
        return filtered_data
        
    except subprocess.TimeoutExpired:
        print("API call timed out after 45 seconds")
        return []
    except Exception as e:
        print(f"Error loading congress data: {e}")
        log_memory_usage("after error")
        return []

# Update your startup_event function:
@app.on_event("startup")
def startup_event():
    global congress_data, state_lookup, bio_to_committees
    
    log_memory_usage("startup begin")
    print("=== STARTUP WITH CONGRESS TRADING DATA ===")
    
    try:
        # Load cache
        load_cache()
        log_memory_usage("after cache")
        
        # Load current legislators
        state_lookup = load_current_legislators_only()
        log_memory_usage("after legislators")
        
        # NEW: Load congress trading data
        congress_data = load_congress_trading_data()
        log_memory_usage("after congress data")
        
        # Keep committees empty for now
        bio_to_committees = {}
        
        # Final cleanup
        gc.collect()
        log_memory_usage("final memory usage")
        
        print(f"=== STARTUP COMPLETE ===")
        print(f"Loaded: {len(state_lookup)} legislators, {len(congress_data)} trades")
        
    except Exception as e:
        print(f"=== STARTUP ERROR: {e} ===")
        log_memory_usage("after error")
        congress_data = []
        state_lookup = {}
        bio_to_committees = {}

# Update your test endpoint:
@app.get("/test")
def test_endpoint():
    """Test endpoint showing all loaded data"""
    # Get some sample trade data
    sample_trades = congress_data[:3] if congress_data else []
    
    # Get unique politicians from trades
    politicians = set()
    for trade in congress_data[:100]:  # Check first 100 trades
        name = trade.get("Name", "")
        if name:
            politicians.add(name)
    
    return {
        "status": "success", 
        "message": "Congress tracker with trading data",
        "data_loaded": {
            "congress_records": len(congress_data),
            "current_legislators": len(state_lookup),
            "committees": len(bio_to_committees),
            "unique_politicians_trading": len(politicians)
        },
        "sample_states": dict(list(state_lookup.items())[:3]),
        "sample_trades": sample_trades,
        "note": "Last 2 years of trading data loaded"
    }
