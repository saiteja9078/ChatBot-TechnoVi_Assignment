# Environment configuration loader and validator for API keys and server settings.
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_NAMING = os.getenv("GEMINI_API_KEY_NAMING") or GEMINI_API_KEY

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5001))

def validate_config():
    required_vars = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }
    
    missing = [key for key, value in required_vars.items() if not value or value.startswith("your_")]
    
    if missing:
        raise ValueError(f"Missing or invalid environment variables: {', '.join(missing)}")
    
    return True
