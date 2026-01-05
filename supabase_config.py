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
    # The Supabase client doesn't support proxy parameter
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
        # Create client with only URL and key (no proxy support)
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Restore proxy variables if they were removed
        for var in proxy_vars_to_remove:
            if var in _original_proxy_vars:
                os.environ[var] = _original_proxy_vars[var]
        
        return client
    except TypeError as e:
        # Restore proxy variables before re-raising
        for var in proxy_vars_to_remove:
            if var in _original_proxy_vars:
                os.environ[var] = _original_proxy_vars[var]
        
        if "proxy" in str(e).lower() or "unexpected keyword" in str(e).lower():
            print(f"\nWarning: Proxy-related error detected: {e}")
            print("Proxy environment variables have been temporarily removed.")
            print("If this error persists, please check your Supabase client version.")
            # Try one more time without proxy vars
            try:
                client = create_client(SUPABASE_URL, SUPABASE_KEY)
                return client
            except Exception as retry_error:
                print(f"Error creating Supabase client after proxy removal: {retry_error}")
                raise
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

