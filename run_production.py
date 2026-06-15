#!/usr/bin/env python3
"""
Ruff Life Retreat - Production Server (IIS Reverse Proxy Mode)
Runs on localhost:8000 (HTTP only) - IIS handles SSL on port 443
This is the CORRECT script for use with IIS reverse proxy

Run with: python run_production.py
"""

import sys
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

from waitress import serve
from app import create_app

def main():
    """Start production WSGI server on localhost:8000"""
    
    # Create Flask app
    app = create_app()
    
    print("\n" + "="*70)
    print("Ruff Life Retreat - Production Server")
    print("="*70)
    print("Mode: HTTP (IIS handles HTTPS reverse proxy)")
    print("Binding: localhost:8000")
    print("Public URL: https://rufflife.app (via IIS)")
    print("="*70 + "\n")
    
    try:
        print("Starting Waitress server...")
        print("Press Ctrl+C to stop\n")
        
        # Start Waitress on localhost:8000 (no SSL)
        serve(
            app,
            host='127.0.0.1',
            port=8000,
            threads=4,
            _quiet=False
        )
    
    except PermissionError:
        print("ERROR: Permission denied on port 8000")
        sys.exit(1)
    
    except OSError as e:
        print(f"ERROR: Could not start server: {e}")
        print("\nCheck if port 8000 is in use:")
        print("  netstat -ano | findstr :8000")
        sys.exit(1)
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()