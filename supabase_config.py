"""
Supabase Configuration
Set your Supabase credentials here or use environment variables
"""
import os
from supabase import create_client, Client

# Try to load from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use environment variables or direct config

# Supabase configuration
# Get these from your Supabase project settings: https://app.supabase.com/project/_/settings/api
SUPABASE_URL = os.getenv('SUPABASE_URL', 'YOUR_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'YOUR_SUPABASE_ANON_KEY')

# Store original proxy settings if they exist (for potential restoration)
_original_proxy_vars = {}
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    if var in os.environ:
        _original_proxy_vars[var] = os.environ[var]

def get_supabase_client() -> Client:
    """Initialize and return Supabase client"""
    if SUPABASE_URL == 'YOUR_SUPABASE_URL' or SUPABASE_KEY == 'YOUR_SUPABASE_ANON_KEY':
        print("\n" + "="*60)
        print("ERROR: Supabase credentials not configured!")
        print("="*60)
        print("\nTo fix this, you have two options:\n")
        print("Option 1: Edit supabase_config.py directly")
        print("  - Replace 'YOUR_SUPABASE_URL' with your Supabase project URL")
        print("  - Replace 'YOUR_SUPABASE_ANON_KEY' with your Supabase anon key")
        print("\nOption 2: Create a .env file in the project root:")
        print("  SUPABASE_URL=https://your-project.supabase.co")
        print("  SUPABASE_KEY=your-anon-key-here")
        print("\nGet your credentials from:")
        print("  https://app.supabase.com/project/_/settings/api")
        print("="*60 + "\n")
        raise ValueError("Supabase credentials not configured. See error message above.")
    
    # Temporarily remove proxy environment variables that may cause issues
    # Older versions of supabase-py (2.3.4) have compatibility issues with gotrue
    # Newer versions (>=2.8.0) should handle this better, but we keep this as a safety measure
    proxy_vars_to_remove = []
    for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
        if var in os.environ:
            proxy_vars_to_remove.append(var)
            # Store value temporarily
            if var not in _original_proxy_vars:
                _original_proxy_vars[var] = os.environ[var]
            # Remove for Supabase client creation
            del os.environ[var]
    
    try:
        # Create client with only URL and key
        # Note: Upgrade to supabase>=2.8.0 to fix proxy compatibility issues
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Restore proxy variables if they were removed
        for var in proxy_vars_to_remove:
            if var in _original_proxy_vars:
                os.environ[var] = _original_proxy_vars[var]
        
        return client
    except (TypeError, ValueError) as e:
        # Restore proxy variables before handling error
        for var in proxy_vars_to_remove:
            if var in _original_proxy_vars:
                os.environ[var] = _original_proxy_vars[var]
        
        error_str = str(e).lower()
        if "proxy" in error_str or "unexpected keyword" in error_str:
            print(f"\nError: Supabase client proxy compatibility issue: {e}")
            print("This is likely due to using an older version of supabase-py.")
            print("Solution: Upgrade to supabase>=2.8.0 in requirements.txt")
            print("Run: pip install --upgrade supabase")
            raise RuntimeError(
                "Supabase client version incompatibility. Please upgrade supabase-py to >=2.8.0. "
                "Update requirements.txt and redeploy."
            ) from e
        else:
            raise
    except Exception as e:
        # Restore proxy variables before re-raising
        for var in proxy_vars_to_remove:
            if var in _original_proxy_vars:
                os.environ[var] = _original_proxy_vars[var]
        
        if "Invalid API key" in str(e) or "invalid" in str(e).lower():
            print("\n" + "="*60)
            print("ERROR: Invalid Supabase API key!")
            print("="*60)
            print("\nPlease verify your Supabase credentials:")
            print("  1. Check that SUPABASE_URL is correct")
            print("  2. Check that SUPABASE_KEY is the 'anon' or 'public' key (not service_role)")
            print("  3. Get fresh credentials from:")
            print("     https://app.supabase.com/project/_/settings/api")
            print("="*60 + "\n")
        raise

