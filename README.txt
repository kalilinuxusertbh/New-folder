# 1. Clone / create the files above in a directory called rogue-portal/

# 2. Make scripts executable
chmod +x rogue_portal.py setup.sh

# 3. Run setup (install dependencies)
sudo ./setup.sh

# 4. Launch the attack
sudo python3 rogue_portal.py --interface wlan0 --ssid "Free Airport WiFi"

# 5. When you're done, Ctrl+C to clean up