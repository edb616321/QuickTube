#!/usr/bin/env python3
"""Export YouTube cookies from Firefox to a file for yt-dlp"""

import os
import sqlite3
import shutil
import json
import tempfile

SETTINGS_FILE = r'D:\QuickTube\settings.json'
TEMP_FOLDER = r'D:\QuickTube\temp'

def find_firefox_profile():
    """Find the Firefox profile directory with cookies"""
    profiles_dir = os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles')

    if not os.path.exists(profiles_dir):
        print(f"Firefox profiles directory not found: {profiles_dir}")
        return None

    # Find profile that has cookies.sqlite
    for folder in os.listdir(profiles_dir):
        full_path = os.path.join(profiles_dir, folder)
        if os.path.isdir(full_path):
            cookies_file = os.path.join(full_path, 'cookies.sqlite')
            if os.path.exists(cookies_file):
                return full_path

    return None

def export_cookies(profile_dir):
    """Export cookies from Firefox to Netscape format"""
    cookies_db = os.path.join(profile_dir, 'cookies.sqlite')

    if not os.path.exists(cookies_db):
        print(f"Cookies database not found: {cookies_db}")
        return None

    print(f"Found cookies database: {cookies_db}")

    # Copy database to temp location (Firefox may have it locked)
    temp_db = os.path.join(tempfile.gettempdir(), 'firefox_cookies_copy.sqlite')
    shutil.copy2(cookies_db, temp_db)

    # Read cookies
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Get ALL cookies (yt-dlp needs complete cookie jar)
    cursor.execute("""
        SELECT host, name, value, path, expiry, isSecure
        FROM moz_cookies
    """)

    cookies = cursor.fetchall()
    conn.close()
    os.remove(temp_db)

    print(f"Found {len(cookies)} YouTube/Google cookies")

    # Check for login cookies
    login_cookies = [c for c in cookies if c[1] in ['SID', 'SSID', 'HSID', 'APISID', 'SAPISID', 'LOGIN_INFO']]
    print(f"Login-related cookies: {len(login_cookies)}")

    if len(login_cookies) < 3:
        print("\nWARNING: You may not be logged into YouTube in Firefox!")
        print("Please open Firefox, go to youtube.com, and log in.")
        print("Then run this script again.\n")

    # Write to Netscape format
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    cookies_file = os.path.join(TEMP_FOLDER, 'youtube_cookies.txt')

    with open(cookies_file, 'w') as f:
        f.write('# Netscape HTTP Cookie File\n')
        f.write('# https://curl.haxx.se/rfc/cookie_spec.html\n')
        f.write('# This is a generated file! Do not edit.\n\n')

        for host, name, value, path, expiry, is_secure in cookies:
            # Ensure host starts with dot for domain cookies
            if not host.startswith('.') and not host.startswith('www'):
                host = '.' + host

            flag = 'TRUE' if host.startswith('.') else 'FALSE'
            secure = 'TRUE' if is_secure else 'FALSE'

            # Firefox stores expiry in seconds, but verify it's reasonable
            # If expiry is in milliseconds (> year 3000 in seconds), convert
            if expiry and expiry > 32503680000:  # Year 3000 in seconds
                expiry = expiry // 1000

            expiry_str = str(int(expiry)) if expiry else '0'

            f.write(f'{host}\t{flag}\t{path}\t{secure}\t{expiry_str}\t{name}\t{value}\n')

    print(f"Cookies exported to: {cookies_file}")
    return cookies_file

def update_settings(cookies_file):
    """Update QuickTube settings with cookies file path"""
    settings = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)

    settings['cookies_file'] = cookies_file

    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

    print(f"Updated {SETTINGS_FILE}")

def main():
    print('='*60)
    print('Firefox Cookie Exporter for QuickTube')
    print('='*60)
    print()

    profile = find_firefox_profile()
    if not profile:
        print("ERROR: Could not find Firefox profile")
        return

    print(f"Using profile: {profile}")

    cookies_file = export_cookies(profile)
    if cookies_file:
        update_settings(cookies_file)
        print()
        print('='*60)
        print('SUCCESS! Cookies exported.')
        print('You can now try downloading videos in QuickTube.')
        print('='*60)

if __name__ == '__main__':
    main()
