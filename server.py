#!/usr/bin/env python3
"""
server.py
---------
Lightweight local development server for the APEX CAL AI ECU Calibration Dashboard.
Automatically selects an available port, serves the dashboard, and launches your browser.
"""

import http.server
import os
import socket
import socketserver
import sys
import threading
import webbrowser

DEFAULT_PORT = 8080
FALLBACK_PORTS = [8080, 8081, 8082, 8000, 3000, 5000]


def is_port_available(port: int) -> bool:
    """Check if a TCP port is available on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", port))
            return True
        except OSError:
            return False


def find_available_port(preferred: int = DEFAULT_PORT) -> int:
    """Finds preferred port or first available fallback port."""
    if is_port_available(preferred):
        return preferred
    for p in FALLBACK_PORTS:
        if is_port_available(p):
            return p
    # Ephemeral port fallback
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class CustomHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler with correct MIME types and clean logging."""
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".csv": "text/csv; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".png": "image/png",
        ".html": "text/html; charset=utf-8",
    }

    def log_message(self, format, *args):
        # Keep terminal clean; only log errors or file requests
        if args and str(args[1]) not in ("200", "304"):
            sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]} - {args[1]}\n")


def start_server(port: int = None, open_browser: bool = True):
    # Change working directory to directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    if port is None:
        port = find_available_port(DEFAULT_PORT)

    url = f"http://localhost:{port}"

    print("\n" + "=" * 66)
    print("  🏁 APEX CAL // AI ECU CALIBRATION DASHBOARD (LOCAL DEMO)  ")
    print("=" * 66)
    print(f"  🌐 Local Server:  {url}")
    print(f"  📁 Serving From:  {script_dir}")
    print(f"  ⚡ Press Ctrl+C to terminate server")
    print("=" * 66 + "\n")

    if open_browser:
        def _open():
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Timer(0.6, _open).start()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), CustomHTTPHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped by user.")
            sys.exit(0)


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    start_server(port=port_arg, open_browser=True)
