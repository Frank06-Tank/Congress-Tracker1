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

def load_state_lookup_from_yaml():
    """Load state lookup data with error handling"""
    try:
        lookup = {}
        base_dir = os.path.dirname(__file__)
        
        # Try to load both files
        files_to_try = [
            os.path.join(base_dir, "Backend/insider_dashboard/legislators-current.yaml"),
            os.path.join(base_dir, "Backend/insider_dashboard/legislators-historical.yaml")
        ]
        
        for filename in files_to_try:
            if os.path.exists(filename):
                print(f"Loading: {filename}")
                with open(filename, "r") as f:
                    data = yaml.safe_load(f)
                    for person in data:
                        bio_id = person.get("id", {}).get("bioguide")
                        terms = person.get("terms", [])
                        if bio_id and terms:
                            latest_term = terms[-1]
                            state = latest_term.get("state")
                            if state:
                                lookup[bio_id] = state
            else:
                print(f"File not found: {filename}")
        
        return lookup
    except Exception as e:
        print(f"Error loading state lookup: {e}")
        return {}

@app.on_event("startup")
def startup_event():
    global congress_data, state_lookup, bio_to_committees
    
    print("=== STARTUP WITH DATA LOADING ===")
    
    try:
        # Load cache (small operation)
        load_cache()
        print("Cache loaded successfully")
        
        # Load state lookup (small file)
        state_lookup = load_state_lookup_from_yaml()
        print(f"State lookup loaded: {len(state_lookup)} entries")
        
        # Keep congress data empty for now
        congress_data = []
        bio_to_committees = {}
        print("Congress data and committees: empty (will add later)")
        
        print("=== STARTUP COMPLETE ===")
        
    except Exception as e:
        print(f"=== STARTUP ERROR: {e} ===")
        # Fallback to empty data
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
        "message": "Congress tracker is running",
        "data_loaded": {
            "congress_records": len(congress_data) if congress_data else 0,
            "state_lookup": len(state_lookup) if state_lookup else 0,
            "committees": len(bio_to_committees) if bio_to_committees else 0
        },
        "sample_states": dict(list(state_lookup.items())[:5]) if state_lookup else {}
    }

# Temporarily comment out all the complex endpoints that require templates and data
# We'll add these back once basic deployment works

# @app.get("/", response_class=HTMLResponse)
# def homepage(request: Request, page: int = 1, name: str = "", party: str = "", state: str = "", committee: str = ""):
#     # This endpoint requires templates and data, skip for now
#     pass

# @app.get("/politician/{name}", response_class=HTMLResponse) 
# def profile(request: Request, name: str, page: int = 1):
#     # This endpoint requires templates and data, skip for now
#     pass

# @app.get("/dashboard", response_class=HTMLResponse)
# def dashboard(request: Request, page: int = 1, name: str = "", party: str = "", state: str = "", industry: List[str] = Query(default=[]), committee: List[str] = Query(default=[]), transaction: str = "", range: str = "", after: str = ""):
#     # This endpoint requires templates and data, skip for now
#     pass
