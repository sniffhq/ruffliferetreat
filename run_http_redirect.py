#!/usr/bin/env python3
"""
Ruff Life Retreat - HTTP to HTTPS Redirect Server
Listens on port 80 and redirects all traffic to HTTPS (port 443)

Run with: python run_http_redirect.py

Note: This should run alongside your main HTTPS server on port 443
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Add app directory to path
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

from waitress import serve

def redirect_app(environ, start_response):
    """
    WSGI application that redirects HTTP requests to HTTPS
    """
    
    # Get the original request information
    scheme = environ.get('wsgi.url_scheme', 'http')
    server_name = environ.get('SERVER_NAME', 'rufflife.app')
    path = environ.get('PATH_INFO', '/')
    query_string = environ.get('QUERY_STRING', '')
    
    # Build the HTTPS URL
    https_url = f"https://{server_name}{path}"
    if query_string:
        https_url += f"?{query_string}"
    
    # HTTP 301 Permanent Redirect
    status = '301 Moved Permanently'
    response_headers = [
        ('Location', https_url),
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Content-Length', '0')
    ]
    
    start_response(status, response_headers)
    return [b'']

def main():
    """Start HTTP redirect server"""
    
    print("\n" + "="*70)
    print("Ruff Life Retreat - HTTP to HTTPS Redirect Server")
    print("="*70)
    print(f"HTTP Server: http://0.0.0.0:80")
    print(f"Redirects to: https://rufflife.app")
    print(f"Binding: 0.0.0.0:80")
    print("="*70 + "\n")
    
    print("ℹ️  This server redirects all HTTP traffic to HTTPS")
    print("ℹ️  Make sure your HTTPS server is also running on port 443\n")
    
    try:
        # Start Waitress redirect server
        serve(
            redirect_app,
            host='0.0.0.0',
            port=80,
            threads=4,
            _quiet=False
        )
    except PermissionError:
        print("ERROR: Port 80 requires administrator privileges!")
        print("Please run this script as Administrator.")
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: Could not bind to port 80: {e}")
        print("Port 80 may be in use by another application.")
        print("Check with: netstat -ano | findstr :80")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()