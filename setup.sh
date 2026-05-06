#!/bin/bash
# setup.sh — Install requirements for rogue captive portal
# Run as root on Kali Linux

set -e

echo "[+] Updating packages..."
apt update -y

echo "[+] Installing dependencies..."
apt install -y hostapd dnsmasq python3 python3-pip python3-flask iptables net-tools

echo "[+] Installing Python packages..."
pip3 install flask

echo "[+] Disabling interfering services..."
systemctl stop NetworkManager 2>/dev/null || true
systemctl disable NetworkManager 2>/dev/null || true
systemctl stop systemd-resolved 2>/dev/null || true
systemctl disable systemd-resolved 2>/dev/null || true

echo "[+] Setup complete."
echo "[!] Run: python3 rogue_portal.py --interface wlan0 --ssid 'Free Airport WiFi'"