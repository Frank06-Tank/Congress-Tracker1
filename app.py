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

# Temporarily disable templates for testing
# templates = Jinja2Templates(directory="Frontend/src/templates")
# templates.env.filters["format_trade_size"] = format_trade_size

def get_committees(bioguide_id):
    return bio_to_committees.get(bioguide_id, [])

def load_state_lookup_minimal():
    """Try to load just ONE small YAML file to test memory"""
    try:
        base_dir = os.path.dirname(__file__)
        filename = os.path.join(base_dir, "Backend/insider_dashboard/legislators-current.yaml")
        
        log_memory_usage("before YAML load")
        
        if os.path.exists(filename):
            print(f"Found file: {filename}")
            # Check file size first
            file_size = os.path.getsize(filename) / 1024 / 1024  # MB
            print(f"File size: {file_size:.2f} MB")
            
            if file_size > 50:  # If larger than 50MB, skip
                print("File too large, skipping")
                return {}
            
            with open(filename, "r") as f:
                data = yaml.safe_load(f)
                log_memory_usage("after YAML load")
                
                # Process only first 100 entries to test
                lookup = {}
                count = 0
                for person in data:
                    if count >= 100:  # Limit to first 100 for testing
                        break
                    bio_id = person.get("id", {}).get("bioguide")
                    terms = person.get("terms", [])
                    if bio_id and terms:
                        latest_term = terms[-1]
                        state = latest_term.get("state")
                        if state:
                            lookup[bio_id] = state
                            count += 1
                
                log_memory_usage("after processing")
                return lookup
        else:
            print(f"File not found: {filename}")
            return {}
            
    except Exception as e:
        print(f"Error in minimal load: {e}")
        log_memory_usage("after error")
        return {}

@app.on_event("startup")
def startup_event():
    global congress_data, state_lookup, bio_to_committees
    
    log_memory_usage("startup begin")
    print("=== MINIMAL STARTUP WITH MEMORY TESTING ===")
    
    try:
        # Load cache (should be tiny)
        load_cache()
        log_memory_usage("after cache")
        
        # Try minimal YAML loading
        state_lookup = load_state_lookup_minimal()
        print(f"Loaded {len(state_lookup)} state entries (limited for testing)")
        log_memory_usage("after minimal YAML")
        
        # Keep everything else empty
        congress_data = []
        bio_to_committees = {}
        
        # Force garbage collection
        gc.collect()
        log_memory_usage("after gc")
        
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
        "message": "Congress tracker is running (memory debug mode)",
        "data_loaded": {
            "congress_records": len(congress_data) if congress_data else 0,
            "state_lookup": len(state_lookup) if state_lookup else 0,
            "committees": len(bio_to_committees) if bio_to_committees else 0
        },
        "sample_states": dict(list(state_lookup.items())[:3]) if state_lookup else {}
    }
