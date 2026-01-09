"""
QuickTube - YouTube Downloader with Search
Paste URL, search for music, or download entire channels.
Includes codec detection and conversion for maximum compatibility.
"""

import customtkinter as ctk
import os
import json
import threading
import subprocess
import re
import socket
import sqlite3
import shutil
import tempfile
import logging
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
import pyperclip
from tkinter import messagebox
from typing import List, Dict, Optional
from io import BytesIO
import urllib.request

# For thumbnail display
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[QuickTube] Warning: PIL not available, thumbnails disabled")

# For embedded video playback
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False
    print("[QuickTube] Warning: python-vlc not available, preview will use external player")

# For automated YouTube login using undetected-chromedriver
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    print("[QuickTube] Warning: undetected-chromedriver not available, manual login required")

# Import codec utilities for compatibility checking
try:
    from codec_utils import (
        detect_codecs, convert_for_compatibility, is_mobile_compatible,
        MediaInfo, CompatibilityLevel, ConversionProgress
    )
    CODEC_UTILS_AVAILABLE = True
except ImportError:
    CODEC_UTILS_AVAILABLE = False
    print("[QuickTube] Warning: codec_utils not available, codec detection disabled")

# Constants
DOWNLOAD_FOLDER = r"D:\stacher_downloads"
TEMP_FOLDER = r"D:\QuickTube\temp"
LOG_FOLDER = r"D:\QuickTube\logs"
SETTINGS_FILE = "settings.json"
HISTORY_FILE = "download_history.json"
POT_SERVER_PATH = r"D:\QuickTube\pot-provider\server"
POT_SERVER_PORT = 4416

# Setup logging system
def setup_logging():
    """Setup persistent logging with automatic cleanup of old logs"""
    os.makedirs(LOG_FOLDER, exist_ok=True)

    # Clean up logs older than 7 days
    try:
        cutoff = datetime.now() - timedelta(days=7)
        for log_file in Path(LOG_FOLDER).glob("quicktube_*.log"):
            if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
                log_file.unlink()
    except Exception as e:
        print(f"[QuickTube] Warning: Could not clean old logs: {e}")

    # Create log file with today's date
    log_file = os.path.join(LOG_FOLDER, f"quicktube_{datetime.now().strftime('%Y%m%d')}.log")

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also print to console
        ]
    )

    logger = logging.getLogger('QuickTube')
    logger.info("=" * 60)
    logger.info("QuickTube started")
    logger.info(f"Log file: {log_file}")
    return logger

# Initialize logger
logger = setup_logging()

# Colors - Match CCL theme
COLORS = {
    "bg_dark": "#001A4D",
    "card_bg": "#0047AB",
    "card_hover": "#0066FF",
    "text": "#FFFFFF",
    "accent": "#00BFFF",
    "accent_hover": "#1E90FF",
    "progress_bg": "#003380",
    "success": "#00FF00",
    "error": "#FF3333",
    "warning": "#FFA500",
}


class QuickTubeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window setup
        self.title("QuickTube - YouTube Downloader")
        self.geometry("1000x800")
        self.configure(bg=COLORS["bg_dark"])

        # State
        self.download_queue = []
        self.current_download = None
        self.is_downloading = False
        self.search_results: List[Dict] = []
        self.search_checkboxes: Dict[str, ctk.CTkCheckBox] = {}
        self.search_vars: Dict[str, ctk.BooleanVar] = {}
        self.thumbnail_cache: Dict[str, any] = {}  # Cache for thumbnail images

        # Load settings and history
        self.settings = self.load_settings()
        self.history = self.load_history()

        # Ensure temp folder exists
        os.makedirs(TEMP_FOLDER, exist_ok=True)

        # Check for valid cookies and auto-login if needed
        self._auto_login_if_needed()

        # Start POT server if not running (for YouTube bot detection bypass)
        self.pot_server_process = None
        self._ensure_pot_server()

        # Create UI
        self.create_ui()

        # Bind keyboard shortcuts
        self.bind("<Control-v>", lambda e: self.url_entry.event_generate('<<Paste>>'))

        # Protocol for window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _is_pot_server_running(self) -> bool:
        """Check if POT server is running on the configured port"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', POT_SERVER_PORT))
                return result == 0
        except:
            return False

    def _ensure_pot_server(self):
        """Start POT server if not already running"""
        if self._is_pot_server_running():
            print("[QuickTube] POT server already running on port", POT_SERVER_PORT)
            return

        server_script = os.path.join(POT_SERVER_PATH, "build", "main.js")
        if not os.path.exists(server_script):
            print("[QuickTube] Warning: POT server not found. Some YouTube downloads may fail.")
            print(f"[QuickTube] Expected: {server_script}")
            return

        try:
            # Start POT server in background
            print("[QuickTube] Starting POT server...")
            self.pot_server_process = subprocess.Popen(
                ["node", server_script],
                cwd=POT_SERVER_PATH,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            # Wait briefly for server to start
            import time
            time.sleep(2)
            if self._is_pot_server_running():
                print("[QuickTube] POT server started successfully on port", POT_SERVER_PORT)
            else:
                print("[QuickTube] Warning: POT server may not have started properly")
        except Exception as e:
            print(f"[QuickTube] Warning: Could not start POT server: {e}")

    def _auto_login_if_needed(self):
        """Automatically login to YouTube on startup if not authenticated"""
        logger.info("[AUTO-LOGIN] Checking authentication status...")

        # Check if we have valid auth cookies in the default location
        cookies_file = os.path.join(TEMP_FOLDER, "youtube_cookies.txt")
        has_auth = False

        if os.path.exists(cookies_file):
            try:
                with open(cookies_file, 'r') as f:
                    content = f.read()
                    auth_cookies = ['LOGIN_INFO', 'SID', 'HSID', 'SSID', '__Secure-1PSID', 'SAPISID']
                    has_auth = any(cookie in content for cookie in auth_cookies)
                    if has_auth:
                        logger.info(f"[AUTO-LOGIN] Found auth cookies in {cookies_file}")
            except:
                pass

        if has_auth:
            logger.info("[AUTO-LOGIN] Already authenticated - skipping login")
            return

        logger.info("[AUTO-LOGIN] Not authenticated - performing automatic login...")

        # Run undetected-chromedriver login automatically (no prompts)
        if UC_AVAILABLE:
            try:
                self._uc_youtube_login()
            except Exception as e:
                logger.error(f"[AUTO-LOGIN] Failed: {e}")
        else:
            logger.warning("[AUTO-LOGIN] undetected-chromedriver not available - manual login required")

    def _slow_type(self, element, text, delay=0.08):
        """Type text slowly like a human to avoid bot detection"""
        import time
        for char in text:
            element.send_keys(char)
            time.sleep(delay)

    def _uc_youtube_login(self):
        """Perform automatic YouTube login using undetected-chromedriver"""
        import time

        email = self.settings.get("youtube_email", "joeb00399@gmail.com")
        password = self.settings.get("youtube_password", "#CLSadmin09")

        logger.info(f"[UC-LOGIN] Starting login for {email}")

        # Create undetected Chrome instance
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")

        # Use a persistent user data directory
        user_data_dir = os.path.join(os.path.dirname(__file__), "chrome_profile")
        os.makedirs(user_data_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")

        driver = uc.Chrome(options=options, version_main=None)
        wait = WebDriverWait(driver, 20)

        try:
            # Navigate to YouTube
            logger.info("[UC-LOGIN] Loading YouTube...")
            driver.get("https://www.youtube.com")
            time.sleep(5)

            # Check if already logged in
            page_source = driver.page_source
            if "Sign in" not in page_source and "avatar" in page_source.lower():
                logger.info("[UC-LOGIN] Already logged in!")
                self._export_uc_cookies(driver)
                return True

            # Navigate to Google sign-in
            logger.info("[UC-LOGIN] Navigating to Google sign-in...")
            driver.get("https://accounts.google.com/signin/v2/identifier?service=youtube")
            time.sleep(5)

            # Wait for email field and enter email slowly
            logger.info("[UC-LOGIN] Waiting for email field...")
            email_input = wait.until(EC.presence_of_element_located((By.ID, "identifierId")))
            time.sleep(2)

            logger.info("[UC-LOGIN] Entering email slowly...")
            self._slow_type(email_input, email)
            time.sleep(2)

            # Click Next
            logger.info("[UC-LOGIN] Clicking Next...")
            next_button = driver.find_element(By.ID, "identifierNext")
            next_button.click()
            time.sleep(5)

            # Check for blocks
            page_source = driver.page_source
            if "couldn't sign you in" in page_source.lower():
                logger.error("[UC-LOGIN] BLOCKED by Google")
                return False

            # Wait for password field
            logger.info("[UC-LOGIN] Waiting for password field...")
            password_input = wait.until(EC.presence_of_element_located((By.NAME, "Passwd")))
            time.sleep(2)

            # Enter password slowly
            logger.info("[UC-LOGIN] Entering password slowly...")
            self._slow_type(password_input, password)
            time.sleep(2)

            # Click password Next
            logger.info("[UC-LOGIN] Clicking password Next...")
            password_next = driver.find_element(By.ID, "passwordNext")
            password_next.click()
            time.sleep(8)

            # Check for success
            current_url = driver.current_url
            logger.info(f"[UC-LOGIN] Current URL: {current_url}")

            if "youtube.com" in current_url:
                logger.info("[UC-LOGIN] SUCCESS! Redirected to YouTube!")
                self._export_uc_cookies(driver)
                time.sleep(3)
                return True
            elif "challenge" in current_url or "signin" in current_url:
                logger.warning("[UC-LOGIN] 2FA or challenge may be required")
                time.sleep(30)  # Wait for manual intervention
                self._export_uc_cookies(driver)
                return True
            else:
                logger.warning(f"[UC-LOGIN] Unknown state: {current_url}")
                return False

        except Exception as e:
            logger.error(f"[UC-LOGIN] Error: {e}")
            return False

        finally:
            logger.info("[UC-LOGIN] Closing browser...")
            driver.quit()

    def _export_uc_cookies(self, driver):
        """Export cookies from undetected-chromedriver session"""
        cookies = driver.get_cookies()
        cookie_file = os.path.join(TEMP_FOLDER, "youtube_cookies.txt")
        os.makedirs(TEMP_FOLDER, exist_ok=True)

        with open(cookie_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# Auto-generated by QuickTube undetected-chromedriver login\n\n")
            for cookie in cookies:
                domain = cookie.get('domain', '')
                flag = "TRUE" if domain.startswith('.') else "FALSE"
                path = cookie.get('path', '/')
                secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                expiry = str(int(cookie.get('expiry', 0)))
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")

        auth_cookies = [c for c in cookies if c['name'] in ['SID', 'SSID', 'HSID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID']]
        logger.info(f"[UC-LOGIN] Saved {len(cookies)} cookies ({len(auth_cookies)} auth cookies) to {cookie_file}")

        # Update settings to use this cookie file
        self.settings["cookies_file"] = cookie_file
        self.save_settings()

    def _playwright_youtube_login_silent(self):
        """Perform fully automatic YouTube login using Playwright - NO user interaction"""
        email = self.settings.get("youtube_email", "joeb00399@gmail.com")
        password = self.settings.get("youtube_password", "#clsADMIN09")

        logger.info(f"[AUTO-LOGIN] Starting silent login for {email}")

        try:
            with sync_playwright() as p:
                # Launch browser - headless for speed, but can show if needed
                logger.info("[AUTO-LOGIN] Launching browser...")
                browser = p.chromium.launch(headless=False)  # Use Chromium, show window for any CAPTCHA
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                # Go directly to YouTube to set initial cookies
                logger.info("[AUTO-LOGIN] Loading YouTube...")
                page.goto("https://www.youtube.com", wait_until="networkidle")
                page.wait_for_timeout(2000)

                # Click sign in button
                try:
                    sign_in = page.locator('a[href*="accounts.google.com"]').first
                    if sign_in.is_visible(timeout=5000):
                        sign_in.click()
                        page.wait_for_timeout(2000)
                except:
                    # Try direct login URL
                    page.goto("https://accounts.google.com/signin/v2/identifier?service=youtube&hl=en")

                page.wait_for_load_state("networkidle")

                # Enter email
                logger.info("[AUTO-LOGIN] Entering email...")
                email_input = page.locator('input[type="email"]')
                if email_input.is_visible(timeout=10000):
                    email_input.fill(email)
                    page.wait_for_timeout(500)
                    # Click Next button
                    page.locator('#identifierNext').click()
                    page.wait_for_timeout(3000)

                # Enter password
                logger.info("[AUTO-LOGIN] Entering password...")
                password_input = page.locator('input[type="password"]')
                if password_input.is_visible(timeout=10000):
                    password_input.fill(password)
                    page.wait_for_timeout(500)
                    # Click Next button
                    page.locator('#passwordNext').click()
                    logger.info("[AUTO-LOGIN] Password submitted, waiting for redirect...")
                    page.wait_for_timeout(5000)

                # Wait for YouTube redirect or handle any prompts
                try:
                    # Wait up to 60 seconds for redirect to YouTube
                    page.wait_for_url("**youtube.com**", timeout=60000)
                    logger.info("[AUTO-LOGIN] Successfully redirected to YouTube!")
                except:
                    logger.warning("[AUTO-LOGIN] Timeout - may need manual intervention for 2FA/CAPTCHA")

                # Navigate to YouTube to ensure all cookies are set
                page.goto("https://www.youtube.com")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)

                # Save all cookies
                cookies = context.cookies()
                self._save_cookies_to_file(cookies)

                # Count auth cookies saved
                auth_count = len([c for c in cookies if c.get('name') in ['LOGIN_INFO', 'SID', 'HSID', 'SSID', '__Secure-1PSID', 'SAPISID']])
                logger.info(f"[AUTO-LOGIN] Saved {len(cookies)} cookies ({auth_count} auth cookies)")

                browser.close()
                logger.info("[AUTO-LOGIN] Login complete!")

        except Exception as e:
            logger.error(f"[AUTO-LOGIN] Error: {e}")
            raise

    def _save_cookies_to_file(self, cookies):
        """Save cookies to Netscape format file for yt-dlp"""
        cookies_file = os.path.join(TEMP_FOLDER, "youtube_cookies.txt")
        os.makedirs(TEMP_FOLDER, exist_ok=True)

        with open(cookies_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# Auto-generated by QuickTube\n\n")
            for cookie in cookies:
                domain = cookie.get('domain', '')
                if not domain.startswith('.') and not domain.startswith('www'):
                    domain = '.' + domain
                flag = "TRUE" if domain.startswith('.') else "FALSE"
                path = cookie.get('path', '/')
                secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                expires = str(int(cookie.get('expires', 0))) if cookie.get('expires') else "0"
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")

        self.settings["cookies_file"] = cookies_file
        self.save_settings()
        logger.info(f"[AUTO-LOGIN] Cookies saved to {cookies_file}")

    def _check_youtube_login(self) -> bool:
        """Check if we have valid YouTube authentication cookies"""
        # First check our saved cookies file for authentication cookies
        cookies_file = self.settings.get("cookies_file")
        if cookies_file and os.path.exists(cookies_file):
            try:
                with open(cookies_file, 'r') as f:
                    content = f.read()
                    # Check for key authentication cookies
                    auth_cookies = ['LOGIN_INFO', 'SID', 'HSID', 'SSID', '__Secure-1PSID', 'SAPISID']
                    has_auth = any(cookie in content for cookie in auth_cookies)
                    if has_auth:
                        logger.info("[AUTH] Found authentication cookies in cookies file")
                        return True
                    else:
                        logger.warning("[AUTH] Cookies file exists but no auth cookies found")
            except Exception as e:
                logger.warning(f"[AUTH] Error reading cookies file: {e}")

        # Fallback: try yt-dlp with browser cookies
        try:
            logger.info("[AUTH] Checking YouTube login via yt-dlp...")
            result = subprocess.run(
                ["yt-dlp", "--cookies-from-browser", "firefox", "--dump-json",
                 "--skip-download", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
                capture_output=True, text=True, timeout=30
            )
            # Check for bot detection errors
            if "Sign in to confirm" in result.stderr or "bot" in result.stderr.lower():
                logger.warning("[AUTH] YouTube detected as bot - login required")
                return False
            if result.returncode == 0:
                logger.info("[AUTH] yt-dlp auth check passed")
                return True
            logger.warning(f"[AUTH] yt-dlp returned code {result.returncode}")
            return False
        except Exception as e:
            logger.warning(f"[AUTH] Auth check failed: {e}")
            return False

    def _prompt_youtube_login(self):
        """Use Playwright to automate YouTube login"""
        if not PLAYWRIGHT_AVAILABLE:
            # Fallback to manual login
            self._manual_youtube_login()
            return

        # Show starting message
        messagebox.showinfo(
            "YouTube Login",
            "A browser window will open for YouTube login.\n\n"
            "The email will be filled automatically.\n"
            "You may need to:\n"
            "- Enter your password\n"
            "- Complete any verification (2FA, CAPTCHA)\n\n"
            "The window will close automatically when done."
        )

        try:
            # Run Playwright login in a thread to not block UI
            thread = threading.Thread(target=self._playwright_youtube_login)
            thread.start()
            thread.join(timeout=300)  # 5 minute timeout
        except Exception as e:
            messagebox.showerror("Login Error", f"Failed to open browser: {e}")

    def _playwright_youtube_login(self):
        """Perform YouTube login using Playwright with stored credentials"""
        # Get credentials from settings
        email = self.settings.get("youtube_email", "joeb00399@gmail.com")
        password = self.settings.get("youtube_password", "#clsADMIN09")

        logger.info(f"[LOGIN] Starting YouTube login for {email}")

        try:
            with sync_playwright() as p:
                # Launch Firefox (visible so user can handle 2FA/CAPTCHA if needed)
                logger.info("[LOGIN] Launching Firefox browser...")
                browser = p.firefox.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()

                # Navigate to YouTube login
                logger.info("[LOGIN] Navigating to Google sign-in...")
                page.goto("https://accounts.google.com/signin/v2/identifier?service=youtube&hl=en")
                page.wait_for_load_state("networkidle")

                # Fill in email
                logger.info("[LOGIN] Entering email...")
                email_input = page.locator('input[type="email"]')
                if email_input.is_visible():
                    email_input.fill(email)
                    page.click('button:has-text("Next")')
                    page.wait_for_timeout(3000)  # Wait for password page to load

                # Wait for password field
                logger.info("[LOGIN] Entering password...")
                password_input = page.locator('input[type="password"]')
                if password_input.is_visible(timeout=15000):
                    password_input.fill(password)
                    page.wait_for_timeout(500)
                    page.click('button:has-text("Next")')
                    logger.info("[LOGIN] Password submitted, waiting for authentication...")
                else:
                    logger.warning("[LOGIN] Password field not found - may need manual intervention")

                # Wait for login to complete or user to handle 2FA
                # Check for YouTube homepage or redirect
                try:
                    # Wait up to 3 minutes for 2FA/CAPTCHA completion
                    page.wait_for_url("**youtube.com**", timeout=180000)
                    logger.info("[LOGIN] Redirected to YouTube - login successful!")

                    # Navigate to YouTube to get all cookies
                    page.goto("https://www.youtube.com")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(3000)  # Extra time to ensure cookies are set

                except Exception as e:
                    logger.warning(f"[LOGIN] Timeout waiting for YouTube redirect: {e}")
                    # Try to continue anyway - user may have completed login manually

                # Export cookies
                cookies = context.cookies()
                youtube_cookies = [c for c in cookies if 'youtube' in c.get('domain', '') or 'google' in c.get('domain', '')]
                logger.info(f"[LOGIN] Captured {len(youtube_cookies)} YouTube/Google cookies")

                if youtube_cookies:
                    self._save_cookies_to_firefox(cookies)
                    logger.info("[LOGIN] Cookies saved successfully!")
                else:
                    logger.warning("[LOGIN] No YouTube cookies captured - login may have failed")

                browser.close()
                logger.info("[LOGIN] Browser closed")

        except Exception as e:
            logger.error(f"[LOGIN] Playwright login error: {e}")
            print(f"[QuickTube] Playwright login error: {e}")

    def _save_cookies_to_firefox(self, cookies):
        """Save Playwright cookies in a format yt-dlp can use"""
        # Save cookies to a Netscape format file for yt-dlp
        cookies_file = os.path.join(TEMP_FOLDER, "youtube_cookies.txt")
        os.makedirs(TEMP_FOLDER, exist_ok=True)

        with open(cookies_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in cookies:
                domain = cookie.get('domain', '')
                if not domain.startswith('.'):
                    domain = '.' + domain
                flag = "TRUE" if domain.startswith('.') else "FALSE"
                path = cookie.get('path', '/')
                secure = "TRUE" if cookie.get('secure', False) else "FALSE"
                expires = str(int(cookie.get('expires', 0)))
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")

        # Update settings to use cookie file
        self.settings["cookies_file"] = cookies_file
        self.save_settings()

    def _manual_youtube_login(self):
        """Fallback manual login if Playwright not available"""
        firefox_path = self._find_firefox()
        if firefox_path:
            subprocess.Popen([firefox_path, "https://www.youtube.com"])
        else:
            import webbrowser
            webbrowser.open("https://www.youtube.com")

        messagebox.showinfo(
            "YouTube Login Required",
            "Firefox has been opened to YouTube.\n\n"
            "Please:\n"
            "1. Sign in to your Google/YouTube account\n"
            "2. Play any video to confirm you're logged in\n"
            "3. Come back here and try downloading again\n\n"
            "This is a one-time setup - your login will be remembered."
        )

    def _find_firefox(self) -> str:
        """Find Firefox executable path"""
        possible_paths = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    def _find_node_path(self) -> str:
        """Find Node.js executable path for yt-dlp JavaScript runtime"""
        possible_paths = [
            r"D:\Program Files\nodejs\node.exe",
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
            os.path.expandvars(r"%APPDATA%\nvm\current\node.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\node\node.exe"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        # Try to find via where command
        try:
            result = subprocess.run(["where", "node"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0]
        except:
            pass
        return None

    def _ensure_youtube_login(self) -> bool:
        """Ensure user is logged into YouTube, prompt if not"""
        if self._check_youtube_login():
            return True

        self._prompt_youtube_login()

        # Check again after login attempt
        import time
        time.sleep(2)
        return self._check_youtube_login()

    def _force_youtube_login(self):
        """Force a new YouTube login (button handler)"""
        logger.info("[LOGIN] User requested YouTube login...")
        self.login_status.configure(text="Logging in...", text_color=COLORS["accent"])
        self.update()

        # Delete existing cookies to force fresh login
        cookies_file = self.settings.get("cookies_file")
        if cookies_file and os.path.exists(cookies_file):
            try:
                os.remove(cookies_file)
                logger.info("[LOGIN] Removed old cookies file")
            except Exception as e:
                logger.warning(f"[LOGIN] Could not remove old cookies: {e}")

        # Trigger login
        self._prompt_youtube_login()

        # Update status after login attempt
        self.after(5000, self._update_login_status)

    def _update_login_status(self):
        """Update the login status indicator"""
        def check_async():
            is_logged_in = self._check_youtube_login()
            # Schedule UI update on main thread
            self.after(0, lambda: self._set_login_status(is_logged_in))

        # Run check in background thread
        thread = threading.Thread(target=check_async, daemon=True)
        thread.start()

    def _set_login_status(self, is_logged_in: bool):
        """Set the login status label (called from main thread)"""
        if is_logged_in:
            self.login_status.configure(text="✓ Logged in", text_color="#00FF00")
            logger.info("[AUTH] Login status: Authenticated")
        else:
            self.login_status.configure(text="✗ Not logged in", text_color="#FF6666")
            logger.warning("[AUTH] Login status: Not authenticated")

    def _refresh_firefox_cookies(self):
        """Auto-refresh cookies from Firefox on startup"""
        try:
            # Find Firefox profile with cookies
            profiles_dir = os.path.join(os.environ.get('APPDATA', ''), 'Mozilla', 'Firefox', 'Profiles')
            if not os.path.exists(profiles_dir):
                return

            profile_dir = None
            for folder in os.listdir(profiles_dir):
                full_path = os.path.join(profiles_dir, folder)
                if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, 'cookies.sqlite')):
                    profile_dir = full_path
                    break

            if not profile_dir:
                return

            # Copy and read cookies database
            cookies_db = os.path.join(profile_dir, 'cookies.sqlite')
            temp_db = os.path.join(tempfile.gettempdir(), 'firefox_cookies_copy.sqlite')
            shutil.copy2(cookies_db, temp_db)

            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT host, name, value, path, expiry, isSecure FROM moz_cookies")
            cookies = cursor.fetchall()
            conn.close()
            os.remove(temp_db)

            # Write cookies file
            cookies_file = os.path.join(TEMP_FOLDER, 'youtube_cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write('# Netscape HTTP Cookie File\n')
                for host, name, value, path, expiry, is_secure in cookies:
                    if not host.startswith('.') and not host.startswith('www'):
                        host = '.' + host
                    flag = 'TRUE' if host.startswith('.') else 'FALSE'
                    secure = 'TRUE' if is_secure else 'FALSE'
                    if expiry and expiry > 32503680000:
                        expiry = expiry // 1000
                    expiry_str = str(int(expiry)) if expiry else '0'
                    f.write(f'{host}\t{flag}\t{path}\t{secure}\t{expiry_str}\t{name}\t{value}\n')

            self.settings['cookies_file'] = cookies_file
            self.save_settings()
            print(f"[QuickTube] Refreshed {len(cookies)} cookies from Firefox")

        except Exception as e:
            print(f"[QuickTube] Cookie refresh failed: {e}")

    def _get_cookie_args(self) -> list:
        """Get the appropriate cookie arguments for yt-dlp

        Uses --cookies with a cookie file exported by undetected-chromedriver login.
        This bypasses browser cookie encryption issues on Windows.
        """
        cookies_file = os.path.join(TEMP_FOLDER, "youtube_cookies.txt")

        if os.path.exists(cookies_file):
            logger.info(f"[COOKIES] Using --cookies {cookies_file}")
            return ["--cookies", cookies_file]
        else:
            # Fallback to browser cookies if no file exists
            browser = self.settings.get("browser", "firefox")
            logger.info(f"[COOKIES] Cookie file not found, using --cookies-from-browser {browser}")
            return ["--cookies-from-browser", browser]

    def load_settings(self):
        """Load settings from JSON file"""
        defaults = {
            "video_quality": "best",  # best, 1080p, 720p, 480p
            "audio_only": False,
            "download_folder": DOWNLOAD_FOLDER,
            "output_format": "mp4",  # mp4 or webm
            "check_compatibility": True,  # Check codecs after download
            "auto_convert": False,  # Auto-convert incompatible files
            "prefer_h264": True,  # Prefer H.264 codec when downloading
            "browser": "chrome",  # Browser for cookies: chrome, firefox, edge, brave, etc.
        }

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    return {**defaults, **json.load(f)}
            except:
                return defaults
        return defaults

    def save_settings(self):
        """Save settings to JSON file"""
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def load_history(self):
        """Load download history"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_history(self):
        """Save download history"""
        with open(HISTORY_FILE, 'w') as f:
            json.dump(self.history[:20], f, indent=2)  # Keep only last 20

    def add_to_history(self, title, url, filename):
        """Add download to history"""
        entry = {
            "title": title,
            "url": url,
            "filename": filename,
            "timestamp": datetime.now().isoformat()
        }
        # Remove duplicates
        self.history = [h for h in self.history if h.get('url') != url]
        self.history.insert(0, entry)
        self.save_history()
        self.update_history_display()

    def create_ui(self):
        """Create the main UI"""
        # Header
        header = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=10)
        header.pack(fill="x", padx=20, pady=(20, 10))

        title = ctk.CTkLabel(
            header,
            text="🎬 QuickTube",
            font=("Arial", 32, "bold"),
            text_color=COLORS["text"]
        )
        title.pack(side="left", padx=20, pady=10)

        folder_label = ctk.CTkLabel(
            header,
            text=f"📁 {DOWNLOAD_FOLDER}",
            font=("Arial", 14),
            text_color=COLORS["accent"]
        )
        folder_label.pack(side="left", padx=10, pady=10)

        # Browser indicator (shows which browser is used for cookies)
        browser = self.settings.get("browser", "chrome")
        browser_label = ctk.CTkLabel(
            header,
            text=f"🌐 {browser.title()}",
            font=("Arial", 12),
            text_color=COLORS["accent"]
        )
        browser_label.pack(side="right", padx=10, pady=10)

        # Tab buttons
        tab_frame = ctk.CTkFrame(self, fg_color="transparent")
        tab_frame.pack(fill="x", padx=20, pady=(5, 0))

        self.url_tab_btn = ctk.CTkButton(
            tab_frame,
            text="📋 URL Download",
            command=lambda: self.switch_tab("url"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=40
        )
        self.url_tab_btn.pack(side="left", padx=5)

        self.search_tab_btn = ctk.CTkButton(
            tab_frame,
            text="🔍 Search Music",
            command=lambda: self.switch_tab("search"),
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=40
        )
        self.search_tab_btn.pack(side="left", padx=5)

        # Open Folder button (always visible)
        open_folder_btn = ctk.CTkButton(
            tab_frame,
            text="📁 Open Folder",
            command=self.open_download_folder,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=140,
            height=40
        )
        open_folder_btn.pack(side="left", padx=5)

        # Container for tab content
        self.tab_container = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_container.pack(fill="both", expand=True, padx=20, pady=10)

        # Create both tab frames
        self._create_url_tab()
        self._create_search_tab()

        # Show URL tab by default
        self.current_tab = "url"
        self.url_tab_frame.pack(fill="both", expand=True)

    def _create_url_tab(self):
        """Create the URL download tab"""
        self.url_tab_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")

        # URL Input section
        input_frame = ctk.CTkFrame(self.url_tab_frame, fg_color=COLORS["card_bg"], corner_radius=10)
        input_frame.pack(fill="x", pady=10)

        # URL label with folder button
        url_header = ctk.CTkFrame(input_frame, fg_color="transparent")
        url_header.pack(fill="x", padx=20, pady=(15, 5))

        url_label = ctk.CTkLabel(
            url_header,
            text="Paste URL (video or channel):",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text"]
        )
        url_label.pack(side="left")

        quick_folder_btn = ctk.CTkButton(
            url_header,
            text="📁 Open Folder",
            command=self.open_download_folder,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 12, "bold"),
            width=130,
            height=30
        )
        quick_folder_btn.pack(side="right")

        self.url_entry = ctk.CTkEntry(
            input_frame,
            font=("Arial", 14),
            height=45,
            placeholder_text="https://youtube.com/watch?v=... or https://youtube.com/@channel"
        )
        self.url_entry.pack(fill="x", padx=20, pady=(0, 15))

        # Button frame
        button_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        button_frame.pack(pady=(0, 15))

        download_video_btn = ctk.CTkButton(
            button_frame,
            text="🎬 Download Video",
            command=self.download_video,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 16, "bold"),
            width=200,
            height=50
        )
        download_video_btn.pack(side="left", padx=10)

        download_channel_btn = ctk.CTkButton(
            button_frame,
            text="📺 Download Channel",
            command=self.download_channel,
            fg_color=COLORS["card_hover"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 16, "bold"),
            width=200,
            height=50
        )
        download_channel_btn.pack(side="left", padx=10)

        paste_btn = ctk.CTkButton(
            button_frame,
            text="📋 Paste URL",
            command=self.paste_url,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=50
        )
        paste_btn.pack(side="left", padx=10)

        clear_btn = ctk.CTkButton(
            button_frame,
            text="🗑️ Clear",
            command=self.clear_url,
            fg_color=COLORS["error"],
            hover_color="#CC0000",
            font=("Arial", 14, "bold"),
            width=120,
            height=50
        )
        clear_btn.pack(side="left", padx=10)

        # Progress section (shared between tabs) - in URL tab
        progress_frame = ctk.CTkFrame(self.url_tab_frame, fg_color=COLORS["card_bg"], corner_radius=10)
        progress_frame.pack(fill="both", expand=True, pady=10)

        progress_title = ctk.CTkLabel(
            progress_frame,
            text="📋 Download Progress",
            font=("Arial", 18, "bold"),
            text_color=COLORS["text"]
        )
        progress_title.pack(anchor="w", padx=15, pady=(10, 5))

        # Progress display (scrollable)
        self.progress_display = ctk.CTkTextbox(
            progress_frame,
            font=("Courier New", 11),
            fg_color=COLORS["progress_bg"],
            wrap="word",
            height=200
        )
        self.progress_display.pack(fill="both", expand=True, padx=15, pady=(5, 10))

        # History section
        history_container = ctk.CTkFrame(self.url_tab_frame, fg_color=COLORS["card_bg"], corner_radius=10)
        history_container.pack(fill="x", pady=10)

        history_title = ctk.CTkLabel(
            history_container,
            text="📝 Recent Downloads",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text"]
        )
        history_title.pack(anchor="w", padx=15, pady=(10, 5))

        self.history_frame = ctk.CTkScrollableFrame(
            history_container,
            fg_color=COLORS["progress_bg"],
            height=120
        )
        self.history_frame.pack(fill="both", padx=10, pady=(0, 10))

        self.update_history_display()

    def _create_search_tab(self):
        """Create the search tab for finding music"""
        self.search_tab_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")

        # Search input section
        search_input_frame = ctk.CTkFrame(self.search_tab_frame, fg_color=COLORS["card_bg"], corner_radius=10)
        search_input_frame.pack(fill="x", pady=10)

        search_header = ctk.CTkFrame(search_input_frame, fg_color="transparent")
        search_header.pack(fill="x", padx=20, pady=(15, 10))

        search_label = ctk.CTkLabel(
            search_header,
            text="🔍 Search YouTube for Music:",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text"]
        )
        search_label.pack(side="left")

        # Search entry
        search_entry_frame = ctk.CTkFrame(search_input_frame, fg_color="transparent")
        search_entry_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.search_entry = ctk.CTkEntry(
            search_entry_frame,
            font=("Arial", 14),
            height=45,
            placeholder_text="Enter genre, artist, or song (e.g., 'jazz music', '80s rock', 'chill lofi')"
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.search_youtube())

        search_btn = ctk.CTkButton(
            search_entry_frame,
            text="🔍 Search",
            command=self.search_youtube,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=120,
            height=45
        )
        search_btn.pack(side="right")

        # Quick genre buttons
        genre_frame = ctk.CTkFrame(search_input_frame, fg_color="transparent")
        genre_frame.pack(fill="x", padx=20, pady=(0, 15))

        genre_label = ctk.CTkLabel(
            genre_frame,
            text="Quick search:",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        genre_label.pack(side="left", padx=(0, 10))

        genres = ["Jazz", "Rock", "Classical", "Lo-Fi", "80s Hits", "Blues", "Country", "Electronic"]
        for genre in genres:
            btn = ctk.CTkButton(
                genre_frame,
                text=genre,
                command=lambda g=genre: self._quick_search(g),
                fg_color=COLORS["card_bg"],
                hover_color=COLORS["card_hover"],
                font=("Arial", 11),
                width=80,
                height=30
            )
            btn.pack(side="left", padx=2)

        # Results section with two columns (results + preview)
        results_container = ctk.CTkFrame(self.search_tab_frame, fg_color="transparent")
        results_container.pack(fill="x", pady=10)

        # Left column: Results list
        results_frame = ctk.CTkFrame(results_container, fg_color=COLORS["card_bg"], corner_radius=10)
        results_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        results_header = ctk.CTkFrame(results_frame, fg_color="transparent")
        results_header.pack(fill="x", padx=15, pady=(10, 5))

        self.results_label = ctk.CTkLabel(
            results_header,
            text="📋 Search Results (select videos to download):",
            font=("Arial", 14, "bold"),
            text_color=COLORS["text"]
        )
        self.results_label.pack(side="left")

        # Select all / None buttons
        select_frame = ctk.CTkFrame(results_header, fg_color="transparent")
        select_frame.pack(side="right")

        select_all_btn = ctk.CTkButton(
            select_frame,
            text="Select All",
            command=self._select_all_results,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 11),
            width=80,
            height=25
        )
        select_all_btn.pack(side="left", padx=2)

        select_none_btn = ctk.CTkButton(
            select_frame,
            text="Select None",
            command=self._select_none_results,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 11),
            width=80,
            height=25
        )
        select_none_btn.pack(side="left", padx=2)

        # Results list (scrollable with fixed height)
        self.results_scroll = ctk.CTkScrollableFrame(
            results_frame,
            fg_color=COLORS["progress_bg"],
            height=280
        )
        self.results_scroll.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # Placeholder text
        self.results_placeholder = ctk.CTkLabel(
            self.results_scroll,
            text="Enter a search term and click Search to find videos",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        self.results_placeholder.pack(pady=50)

        # Right column: Preview panel (fixed height to show all buttons)
        self.preview_frame = ctk.CTkFrame(results_container, fg_color=COLORS["card_bg"], corner_radius=10, width=320, height=380)
        self.preview_frame.pack(side="right", fill="y", padx=(5, 0))
        self.preview_frame.pack_propagate(False)

        preview_header = ctk.CTkLabel(
            self.preview_frame,
            text="🎬 Video Preview",
            font=("Arial", 14, "bold"),
            text_color=COLORS["text"]
        )
        preview_header.pack(pady=(10, 5))

        # Large thumbnail/video area
        self.preview_thumb_frame = ctk.CTkFrame(self.preview_frame, fg_color=COLORS["progress_bg"], width=280, height=158)
        self.preview_thumb_frame.pack(padx=15, pady=5)
        self.preview_thumb_frame.pack_propagate(False)

        self.preview_thumb_label = ctk.CTkLabel(
            self.preview_thumb_frame,
            text="Click '👁 Preview'\non a video",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        self.preview_thumb_label.pack(expand=True)

        # VLC player setup (if available)
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_video_frame = None
        if VLC_AVAILABLE:
            try:
                self.vlc_instance = vlc.Instance('--no-xlib', '--quiet')
                self.vlc_player = self.vlc_instance.media_player_new()
            except Exception as e:
                logger.warning(f"Failed to initialize VLC: {e}")
                self.vlc_instance = None
                self.vlc_player = None

        # Preview video title
        self.preview_title = ctk.CTkLabel(
            self.preview_frame,
            text="",
            font=("Arial", 11, "bold"),
            text_color=COLORS["text"],
            wraplength=280
        )
        self.preview_title.pack(padx=10, pady=(5, 2))

        # Preview video details
        self.preview_details = ctk.CTkLabel(
            self.preview_frame,
            text="",
            font=("Arial", 10),
            text_color=COLORS["accent"],
            wraplength=280
        )
        self.preview_details.pack(padx=10, pady=(0, 5))

        # Preview buttons
        preview_buttons = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        preview_buttons.pack(pady=5)

        # Play 30s preview button (main action)
        self.preview_play_btn = ctk.CTkButton(
            preview_buttons,
            text="▶ Play 30s Preview",
            command=self._play_preview_clip,
            fg_color=COLORS["success"],
            hover_color="#00AA55",
            font=("Arial", 12, "bold"),
            width=160,
            height=35,
            state="disabled"
        )
        self.preview_play_btn.pack(pady=2)

        self.preview_watch_btn = ctk.CTkButton(
            preview_buttons,
            text="🔗 Watch on YouTube",
            command=self._watch_preview_video,
            fg_color=COLORS["error"],
            hover_color="#CC0000",
            font=("Arial", 11, "bold"),
            width=160,
            height=30,
            state="disabled"
        )
        self.preview_watch_btn.pack(pady=2)

        self.preview_channel_btn = ctk.CTkButton(
            preview_buttons,
            text="📺 Visit Channel",
            command=self._visit_preview_channel,
            fg_color=COLORS["warning"],
            hover_color="#CC8800",
            font=("Arial", 11, "bold"),
            width=160,
            height=30,
            state="disabled"
        )
        self.preview_channel_btn.pack(pady=2)

        # Store current preview video info
        self.preview_video = None

        # Download button
        download_frame = ctk.CTkFrame(self.search_tab_frame, fg_color="transparent")
        download_frame.pack(fill="x", pady=10)

        self.download_selected_btn = ctk.CTkButton(
            download_frame,
            text="⬇️ Download Selected (0)",
            command=self.download_selected,
            fg_color=COLORS["success"],
            hover_color="#00AA55",
            font=("Arial", 16, "bold"),
            width=250,
            height=50,
            state="disabled"
        )
        self.download_selected_btn.pack(side="left", padx=10)

        # Search progress display (larger for detailed output)
        progress_frame = ctk.CTkFrame(self.search_tab_frame, fg_color=COLORS["bg_dark"])
        progress_frame.pack(fill="both", expand=True, pady=(10, 0))

        progress_label = ctk.CTkLabel(
            progress_frame,
            text="Download Progress:",
            font=("Arial", 12, "bold"),
            text_color=COLORS["text"]
        )
        progress_label.pack(anchor="w", padx=10)

        self.search_progress = ctk.CTkTextbox(
            progress_frame,
            font=("Courier New", 10),
            fg_color=COLORS["progress_bg"],
            wrap="word",
            height=200
        )
        self.search_progress.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def switch_tab(self, tab_name: str):
        """Switch between URL and Search tabs"""
        if tab_name == self.current_tab:
            return

        # Hide current tab
        if self.current_tab == "url":
            self.url_tab_frame.pack_forget()
            self.url_tab_btn.configure(fg_color=COLORS["card_bg"])
        else:
            self.search_tab_frame.pack_forget()
            self.search_tab_btn.configure(fg_color=COLORS["card_bg"])

        # Show new tab
        if tab_name == "url":
            self.url_tab_frame.pack(fill="both", expand=True)
            self.url_tab_btn.configure(fg_color=COLORS["accent"])
        else:
            self.search_tab_frame.pack(fill="both", expand=True)
            self.search_tab_btn.configure(fg_color=COLORS["accent"])

        self.current_tab = tab_name

    def _quick_search(self, genre: str):
        """Quick search for a genre"""
        self.search_entry.delete(0, 'end')
        self.search_entry.insert(0, f"{genre} music")
        self.search_youtube()

    def search_youtube(self):
        """Search YouTube for videos"""
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showwarning("No Query", "Please enter a search term")
            return

        # Clear previous results
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        self.search_results = []
        self.search_checkboxes = {}
        self.search_vars = {}

        # Show searching message
        searching_label = ctk.CTkLabel(
            self.results_scroll,
            text=f"🔍 Searching for '{query}'...",
            font=("Arial", 12),
            text_color=COLORS["accent"]
        )
        searching_label.pack(pady=50)

        # Search in thread
        thread = threading.Thread(target=self._search_thread, args=(query,))
        thread.daemon = True
        thread.start()

    def _search_thread(self, query: str):
        """Perform YouTube search in background thread"""
        try:
            # Use yt-dlp to search YouTube
            cmd = [
                "yt-dlp",
                f"ytsearch20:{query}",  # Search for 20 results
                "--flat-playlist",
                "--print", "%(id)s|%(title)s|%(duration_string)s|%(channel)s|%(view_count)s",
                "--no-warnings"
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            results = []
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                parts = line.split("|")
                if len(parts) >= 4:
                    video_id = parts[0]
                    title = parts[1]
                    duration = parts[2] if len(parts) > 2 else "N/A"
                    channel = parts[3] if len(parts) > 3 else "Unknown"
                    views = parts[4] if len(parts) > 4 else "0"

                    # Format views
                    try:
                        view_count = int(views) if views and views != "NA" else 0
                        if view_count >= 1000000:
                            views_str = f"{view_count / 1000000:.1f}M"
                        elif view_count >= 1000:
                            views_str = f"{view_count / 1000:.1f}K"
                        else:
                            views_str = str(view_count)
                    except:
                        views_str = "N/A"

                    results.append({
                        "id": video_id,
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "title": title,
                        "duration": duration,
                        "channel": channel,
                        "views": views_str
                    })

            process.wait()

            # Update UI on main thread
            self.after(0, lambda: self._display_search_results(results, query))

        except Exception as e:
            self.after(0, lambda: self._search_error(str(e)))

    def _display_search_results(self, results: List[Dict], query: str):
        """Display search results in the UI"""
        # Clear loading message
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

        if not results:
            no_results = ctk.CTkLabel(
                self.results_scroll,
                text=f"No results found for '{query}'",
                font=("Arial", 12),
                text_color=COLORS["text"]
            )
            no_results.pack(pady=50)
            return

        self.search_results = results
        self.results_label.configure(text=f"📋 Found {len(results)} results for '{query}':")

        # Create result items
        for i, result in enumerate(results):
            self._create_result_item(i, result)

        self._update_download_button()

    def _create_result_item(self, index: int, result: Dict):
        """Create a single result item with checkbox and thumbnail"""
        item_frame = ctk.CTkFrame(self.results_scroll, fg_color=COLORS["card_bg"], corner_radius=5)
        item_frame.pack(fill="x", pady=3, padx=5)

        # Checkbox
        var = ctk.BooleanVar(value=False)
        self.search_vars[result["id"]] = var

        checkbox = ctk.CTkCheckBox(
            item_frame,
            text="",
            variable=var,
            width=20,
            command=self._update_download_button
        )
        checkbox.pack(side="left", padx=(10, 5), pady=10)
        self.search_checkboxes[result["id"]] = checkbox

        # Thumbnail frame (placeholder initially)
        thumb_frame = ctk.CTkFrame(item_frame, fg_color=COLORS["progress_bg"], width=120, height=68)
        thumb_frame.pack(side="left", padx=5, pady=5)
        thumb_frame.pack_propagate(False)

        # Placeholder label while loading
        thumb_label = ctk.CTkLabel(
            thumb_frame,
            text="Loading...",
            font=("Arial", 9),
            text_color=COLORS["text"]
        )
        thumb_label.pack(expand=True)

        # Load thumbnail in background
        if PIL_AVAILABLE:
            thread = threading.Thread(
                target=self._load_thumbnail,
                args=(result["id"], thumb_label, thumb_frame)
            )
            thread.daemon = True
            thread.start()

        # Info frame
        info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, pady=5, padx=5)

        # Title (truncate if too long)
        title = result["title"]
        if len(title) > 55:
            title = title[:52] + "..."

        title_label = ctk.CTkLabel(
            info_frame,
            text=f"{index + 1}. {title}",
            font=("Arial", 12, "bold"),
            text_color=COLORS["text"],
            anchor="w"
        )
        title_label.pack(anchor="w")

        # Details
        details = f"{result['duration']} | {result['channel']} | {result['views']} views"
        details_label = ctk.CTkLabel(
            info_frame,
            text=details,
            font=("Arial", 10),
            text_color=COLORS["accent"],
            anchor="w"
        )
        details_label.pack(anchor="w")

        # YouTube links frame
        links_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        links_frame.pack(anchor="w", pady=(2, 0))

        # Video link button
        video_url = f"https://www.youtube.com/watch?v={result['id']}"
        video_link_btn = ctk.CTkButton(
            links_frame,
            text="🔗 Video",
            command=lambda url=video_url: webbrowser.open(url),
            fg_color="transparent",
            hover_color=COLORS["card_hover"],
            text_color=COLORS["success"],
            font=("Arial", 10, "underline"),
            width=60,
            height=20,
            cursor="hand2"
        )
        video_link_btn.pack(side="left", padx=(0, 5))

        # Channel link button (if channel_id available)
        channel_name = result.get('channel', 'Channel')
        channel_id = result.get('channel_id', '')
        if channel_id:
            channel_url = f"https://www.youtube.com/channel/{channel_id}"
        else:
            # Fallback to search for channel
            channel_url = f"https://www.youtube.com/results?search_query={channel_name.replace(' ', '+')}"

        channel_link_btn = ctk.CTkButton(
            links_frame,
            text=f"📺 {channel_name[:20]}",
            command=lambda url=channel_url: webbrowser.open(url),
            fg_color="transparent",
            hover_color=COLORS["card_hover"],
            text_color=COLORS["warning"],
            font=("Arial", 10, "underline"),
            width=120,
            height=20,
            cursor="hand2"
        )
        channel_link_btn.pack(side="left")

        # Preview button - loads video in preview panel
        preview_btn = ctk.CTkButton(
            links_frame,
            text="👁 Preview",
            command=lambda r=result: self._set_preview_video(r),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 10, "bold"),
            width=70,
            height=20,
            cursor="hand2"
        )
        preview_btn.pack(side="left", padx=(10, 0))

    def _load_thumbnail(self, video_id: str, label: ctk.CTkLabel, frame: ctk.CTkFrame):
        """Load thumbnail from YouTube in background thread"""
        try:
            # Check cache first
            if video_id in self.thumbnail_cache:
                ctk_image = self.thumbnail_cache[video_id]
                self.after(0, lambda: self._display_thumbnail(label, frame, ctk_image))
                return

            # YouTube thumbnail URL (medium quality - 320x180)
            thumb_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"

            # Download thumbnail
            with urllib.request.urlopen(thumb_url, timeout=5) as response:
                data = response.read()

            # Create PIL image and resize
            pil_image = Image.open(BytesIO(data))
            pil_image = pil_image.resize((120, 68), Image.Resampling.LANCZOS)

            # Create CTkImage (works with both light and dark mode)
            ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(120, 68))

            # Cache the image
            self.thumbnail_cache[video_id] = ctk_image

            # Update UI on main thread
            self.after(0, lambda: self._display_thumbnail(label, frame, ctk_image))

        except Exception as e:
            # On error, just show "No thumb"
            self.after(0, lambda: label.configure(text="No thumb"))

    def _display_thumbnail(self, label: ctk.CTkLabel, frame: ctk.CTkFrame, ctk_image):
        """Display thumbnail image in the label"""
        try:
            label.configure(image=ctk_image, text="")
        except:
            pass  # Widget may have been destroyed

    def _search_error(self, error: str):
        """Handle search error"""
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

        error_label = ctk.CTkLabel(
            self.results_scroll,
            text=f"Error: {error}",
            font=("Arial", 12),
            text_color=COLORS["error"]
        )
        error_label.pack(pady=50)

    def _select_all_results(self):
        """Select all search results"""
        for var in self.search_vars.values():
            var.set(True)
        self._update_download_button()

    def _select_none_results(self):
        """Deselect all search results"""
        for var in self.search_vars.values():
            var.set(False)
        self._update_download_button()

    def _set_preview_video(self, result: Dict):
        """Set the preview panel to show the selected video"""
        self.preview_video = result

        # Update title
        title = result.get('title', 'Unknown')
        if len(title) > 60:
            title = title[:57] + "..."
        self.preview_title.configure(text=title)

        # Update details
        details = f"{result.get('duration', '')} | {result.get('channel', '')} | {result.get('views', '')} views"
        self.preview_details.configure(text=details)

        # Enable all buttons
        self.preview_play_btn.configure(state="normal")
        self.preview_watch_btn.configure(state="normal")
        self.preview_channel_btn.configure(state="normal")

        # Load larger thumbnail
        if PIL_AVAILABLE:
            thread = threading.Thread(
                target=self._load_preview_thumbnail,
                args=(result["id"],)
            )
            thread.daemon = True
            thread.start()

    def _load_preview_thumbnail(self, video_id: str):
        """Load larger thumbnail for preview panel"""
        try:
            # YouTube thumbnail URL (high quality - 480x360)
            thumb_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

            # Download thumbnail
            with urllib.request.urlopen(thumb_url, timeout=5) as response:
                data = response.read()

            # Create PIL image and resize to fit preview area
            pil_image = Image.open(BytesIO(data))
            pil_image = pil_image.resize((280, 158), Image.Resampling.LANCZOS)

            # Create CTkImage
            ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(280, 158))

            # Update UI on main thread
            self.after(0, lambda: self._display_preview_thumbnail(ctk_image))

        except Exception as e:
            self.after(0, lambda: self.preview_thumb_label.configure(text="Could not load\nthumbnail", image=None))

    def _display_preview_thumbnail(self, ctk_image):
        """Display the preview thumbnail"""
        try:
            self.preview_thumb_label.configure(image=ctk_image, text="")
        except Exception:
            pass

    def _watch_preview_video(self):
        """Open the preview video on YouTube"""
        if self.preview_video:
            video_url = f"https://www.youtube.com/watch?v={self.preview_video['id']}"
            webbrowser.open(video_url)

    def _visit_preview_channel(self):
        """Visit the channel of the preview video"""
        if self.preview_video:
            channel_id = self.preview_video.get('channel_id', '')
            channel_name = self.preview_video.get('channel', 'Channel')
            if channel_id:
                channel_url = f"https://www.youtube.com/channel/{channel_id}"
            else:
                channel_url = f"https://www.youtube.com/results?search_query={channel_name.replace(' ', '+')}"
            webbrowser.open(channel_url)

    def _play_preview_clip(self):
        """Download and play a 30-second preview clip"""
        if not self.preview_video:
            return

        # Disable button while downloading
        self.preview_play_btn.configure(state="disabled", text="⏳ Loading...")

        # Run in background thread
        thread = threading.Thread(target=self._download_and_play_preview)
        thread.daemon = True
        thread.start()

    def _download_and_play_preview(self):
        """Download 30-second clip and play it"""
        try:
            video_id = self.preview_video['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # Create temp file for preview
            preview_file = os.path.join(TEMP_FOLDER, f"preview_{video_id}.mp4")

            # If preview already exists and is recent, just play it
            if os.path.exists(preview_file):
                self.after(0, lambda: self._play_video_file(preview_file))
                return

            # Download 30 seconds starting from 10 seconds in (to skip intros)
            # Using yt-dlp with download-sections
            cmd = [
                "yt-dlp",
                "--download-sections", "*10-40",  # 30 seconds from 10s to 40s
                "-f", "bv*[height<=480]+ba/b[height<=480]/b",  # Lower quality for quick preview
                "-o", preview_file,
                "--no-playlist",
                "--quiet",
                "--no-warnings",
            ]
            cmd.extend(self._get_cookie_args())
            cmd.append(video_url)

            logger.info(f"Downloading preview clip: {' '.join(cmd)}")

            # Run yt-dlp
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0 and os.path.exists(preview_file):
                self.after(0, lambda: self._play_video_file(preview_file))
            else:
                # Fallback: open in browser at 10 second mark
                logger.warning(f"Preview download failed, opening in browser. Error: {result.stderr}")
                fallback_url = f"https://www.youtube.com/watch?v={video_id}&t=10"
                self.after(0, lambda: webbrowser.open(fallback_url))

        except subprocess.TimeoutExpired:
            logger.error("Preview download timed out")
            # Fallback to browser
            fallback_url = f"https://www.youtube.com/watch?v={self.preview_video['id']}&t=10"
            self.after(0, lambda: webbrowser.open(fallback_url))
        except Exception as e:
            logger.error(f"Preview error: {e}")
            # Fallback to browser
            fallback_url = f"https://www.youtube.com/watch?v={self.preview_video['id']}&t=10"
            self.after(0, lambda: webbrowser.open(fallback_url))
        finally:
            # Re-enable button
            self.after(0, lambda: self.preview_play_btn.configure(state="normal", text="▶ Play 30s Preview"))

    def _play_video_file(self, filepath):
        """Play a video file in the embedded VLC player"""
        try:
            if not os.path.exists(filepath):
                messagebox.showerror("Error", "Preview file not found")
                return

            # Use embedded VLC if available
            if VLC_AVAILABLE and self.vlc_player:
                self._play_in_embedded_vlc(filepath)
            else:
                # Fallback to external player
                os.startfile(filepath)
        except Exception as e:
            logger.error(f"Failed to play video: {e}")
            messagebox.showerror("Error", f"Could not play video: {e}")

    def _play_in_embedded_vlc(self, filepath):
        """Play video in the embedded VLC player inside the preview panel"""
        try:
            # Stop any currently playing video
            if self.vlc_player.is_playing():
                self.vlc_player.stop()

            # Hide thumbnail label and show video frame
            self.preview_thumb_label.pack_forget()

            # Create video frame if not exists
            if not self.vlc_video_frame:
                import tkinter as tk
                self.vlc_video_frame = tk.Frame(self.preview_thumb_frame, bg='black', width=280, height=158)
                self.vlc_video_frame.pack(fill='both', expand=True)
                self.vlc_video_frame.update()

                # Get the window handle and set VLC to use it
                handle = self.vlc_video_frame.winfo_id()
                self.vlc_player.set_hwnd(handle)

            # Make sure video frame is visible
            self.vlc_video_frame.pack(fill='both', expand=True)

            # Create media and play
            media = self.vlc_instance.media_new(filepath)
            self.vlc_player.set_media(media)
            self.vlc_player.play()

            logger.info(f"Playing preview in embedded VLC: {filepath}")

        except Exception as e:
            logger.error(f"Embedded VLC playback failed: {e}")
            # Fallback to external player
            os.startfile(filepath)

    def _stop_preview_playback(self):
        """Stop the embedded video playback and show thumbnail again"""
        try:
            if self.vlc_player and self.vlc_player.is_playing():
                self.vlc_player.stop()

            # Hide video frame and show thumbnail
            if self.vlc_video_frame:
                self.vlc_video_frame.pack_forget()

            self.preview_thumb_label.pack(expand=True)
        except Exception as e:
            logger.error(f"Error stopping preview: {e}")

    def _update_download_button(self):
        """Update the download button text and state"""
        selected_count = sum(1 for var in self.search_vars.values() if var.get())
        self.download_selected_btn.configure(text=f"⬇️ Download Selected ({selected_count})")

        if selected_count > 0:
            self.download_selected_btn.configure(state="normal")
        else:
            self.download_selected_btn.configure(state="disabled")

    def download_selected(self):
        """Download all selected videos"""
        selected = [r for r in self.search_results if self.search_vars.get(r["id"], ctk.BooleanVar()).get()]

        if not selected:
            messagebox.showwarning("No Selection", "Please select at least one video to download")
            return

        # Check YouTube login first
        if not self._ensure_youtube_login():
            return

        # Confirm download
        response = messagebox.askyesno(
            "Download Videos",
            f"Download {len(selected)} selected video(s)?\n\n"
            f"Files will be saved to:\n{DOWNLOAD_FOLDER}"
        )
        if not response:
            return

        # Start download in thread
        thread = threading.Thread(target=self._download_selected_thread, args=(selected,))
        thread.daemon = True
        thread.start()

    def _download_selected_thread(self, videos: List[Dict]):
        """Download selected videos in background"""
        total = len(videos)
        successful = 0
        failed = 0

        # Clear progress and start fresh
        self._clear_search_progress()
        self._append_search_progress(f"Starting download of {total} video(s)...\n")
        self._append_search_progress(f"Save folder: {DOWNLOAD_FOLDER}\n\n")

        for i, video in enumerate(videos, 1):
            title_short = video['title'][:60] + "..." if len(video['title']) > 60 else video['title']
            self._append_search_progress(f"[{i}/{total}] {title_short}\n")
            self._append_search_progress(f"    URL: {video['url']}\n")

            try:
                node_path = self._find_node_path()
                cmd = [
                    "yt-dlp",
                    "-o", f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
                    "--no-playlist",
                    "--merge-output-format", self.settings.get("output_format", "mp4"),
                    "--newline",  # Better progress output
                    # YouTube extraction requires JavaScript runtime
                    "--js-runtimes", f"node:{node_path}" if node_path else "node",
                                    ]
                cmd.extend(self._get_cookie_args())
                cmd.append(video["url"])

                # Add quality options
                if self.settings.get("audio_only"):
                    cmd.extend(["-f", "bestaudio", "-x", "--audio-format", "mp3"])
                else:
                    quality = self.settings.get("video_quality", "best")
                    if quality == "best":
                        cmd.extend(["-f", "bv*+ba/b"])  # Best video+audio, or best combined
                        cmd.extend(["-S", "res,vcodec:h264"])
                    else:
                        cmd.extend(["-f", f"bv*[height<={quality}]+ba/b"])  # Best video at quality+audio, or best combined

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )

                # Stream output line by line
                last_progress = ""
                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    # Show download progress or important messages
                    if "[download]" in line and "%" in line:
                        # Update progress in place
                        if "100%" in line or last_progress == "":
                            self._append_search_progress(f"    {line}\n")
                            last_progress = line
                    elif "[Merger]" in line or "Destination:" in line:
                        self._append_search_progress(f"    {line}\n")
                    elif "ERROR" in line or "error" in line.lower():
                        self._append_search_progress(f"    ERROR: {line}\n")
                    elif "has already been downloaded" in line:
                        self._append_search_progress(f"    Already exists, skipping\n")

                process.wait()

                if process.returncode == 0:
                    self._append_search_progress(f"    ✓ SUCCESS\n\n")
                    successful += 1
                    self.after(0, lambda v=video: self.add_to_history(v["title"], v["url"], f"{v['title']}.mp4"))
                else:
                    self._append_search_progress(f"    ✗ FAILED (exit code {process.returncode})\n\n")
                    failed += 1

            except Exception as e:
                self._append_search_progress(f"    ✗ ERROR: {e}\n\n")
                failed += 1

        self._append_search_progress(f"{'='*50}\n")
        self._append_search_progress(f"COMPLETE: {successful} successful, {failed} failed\n")
        self._append_search_progress(f"Files saved to: {DOWNLOAD_FOLDER}")

    def _log_search_progress(self, message: str):
        """Log message to search progress display (replaces content)"""
        def update():
            self.search_progress.configure(state="normal")
            self.search_progress.delete("1.0", "end")
            self.search_progress.insert("end", message)
            self.search_progress.configure(state="disabled")
        self.after(0, update)

    def _clear_search_progress(self):
        """Clear search progress display"""
        def update():
            self.search_progress.configure(state="normal")
            self.search_progress.delete("1.0", "end")
            self.search_progress.configure(state="disabled")
        self.after(0, update)

    def _append_search_progress(self, message: str):
        """Append message to search progress display"""
        def update():
            self.search_progress.configure(state="normal")
            self.search_progress.insert("end", message)
            self.search_progress.see("end")  # Auto-scroll to bottom
            self.search_progress.configure(state="disabled")
        self.after(0, update)

    def paste_url(self):
        """Paste URL from clipboard"""
        try:
            url = pyperclip.paste()
            if url:
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, url)
        except Exception as e:
            self.log_message(f"[ERROR] Could not paste: {e}")

    def clear_url(self):
        """Clear the URL entry field"""
        self.url_entry.delete(0, 'end')
        self.url_entry.focus()

    def log_message(self, message):
        """Add message to progress display (thread-safe)"""
        def update():
            self.progress_display.configure(state="normal")
            self.progress_display.insert("end", f"{message}\n")
            self.progress_display.see("end")
            self.progress_display.configure(state="disabled")

        # Schedule update on main thread
        self.after(0, update)

    def download_video(self):
        """Download single video"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste a YouTube URL first")
            return

        if not self.validate_url(url):
            messagebox.showerror("Invalid URL", "Please enter a valid YouTube URL")
            return

        # Check YouTube login first
        if not self._ensure_youtube_login():
            return

        # Start download in thread
        thread = threading.Thread(target=self._download_video_thread, args=(url,))
        thread.daemon = True
        thread.start()

    def download_channel(self):
        """Download all videos from channel"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste a YouTube channel URL first")
            return

        # Check YouTube login first
        if not self._ensure_youtube_login():
            return

        # Confirm channel download
        response = messagebox.askyesno(
            "Download Channel",
            "This will download ALL videos from the channel. This may take a long time. Continue?"
        )
        if not response:
            return

        # Start download in thread
        thread = threading.Thread(target=self._download_channel_thread, args=(url,))
        thread.daemon = True
        thread.start()

    def validate_url(self, url):
        """Validate YouTube URL"""
        patterns = [
            r'youtube\.com/watch\?v=',
            r'youtu\.be/',
            r'youtube\.com/@',
            r'youtube\.com/channel/',
            r'youtube\.com/c/',
            r'youtube\.com/user/',
        ]
        return any(re.search(pattern, url) for pattern in patterns)

    def _cleanup_old_temp_files(self, max_age_hours=24):
        """Clean up old video files from temp folder to prevent cache confusion"""
        try:
            import time
            cutoff_time = time.time() - (max_age_hours * 3600)
            cleaned = 0
            for f in os.listdir(TEMP_FOLDER):
                if f.endswith(('.mp4', '.webm', '.mkv', '.m4a')):
                    filepath = os.path.join(TEMP_FOLDER, f)
                    if os.path.getmtime(filepath) < cutoff_time:
                        try:
                            os.remove(filepath)
                            cleaned += 1
                            logger.info(f"Cleaned old temp file: {f}")
                        except Exception as e:
                            logger.warning(f"Could not remove old temp file {f}: {e}")
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old temp files")
        except Exception as e:
            logger.warning(f"Temp cleanup failed: {e}")

    def _download_video_thread(self, url):
        """Download video in separate thread - downloads to temp first, then moves to final location"""
        temp_file = None
        all_output = []  # Capture all output for logging
        try:
            self.is_downloading = True

            # Clean up old cached files to prevent wrong file being moved
            self._cleanup_old_temp_files(max_age_hours=24)

            self.log_message(f"\n[START] Downloading video...")
            self.log_message(f"[URL] {url}")
            self.log_message(f"[TEMP] Downloading to temp folder first...\n")

            # Build yt-dlp command - download to TEMP folder
            # Find node.exe path for yt-dlp JavaScript runtime
            node_path = self._find_node_path()
            logger.info(f"Node.js path: {node_path}")

            cmd = [
                "yt-dlp",
                "-o", f"{TEMP_FOLDER}/%(title)s.%(ext)s",
                "--no-playlist",  # IMPORTANT: Download ONLY this video, not the whole playlist
                "--progress",
                "--newline",
                "--no-colors",
                "--merge-output-format", self.settings.get("output_format", "mp4"),  # Force mp4 output
                # YouTube extraction requires JavaScript runtime (node or deno)
                "--js-runtimes", f"node:{node_path}" if node_path else "node",
                            ]
            cmd.extend(self._get_cookie_args())

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bv*+ba/b"])  # Best video+audio, or best combined
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bv*[height<={quality}]+ba/b"])  # Best video at quality+audio, or best combined

            # Add URL at the end (must be last argument)
            cmd.append(url)

            # Log the full command
            logger.info(f"Download URL: {url}")
            logger.info(f"Full command: {' '.join(cmd)}")

            # Run yt-dlp
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Capture output
            video_title = "Video"
            temp_file_path = None
            last_percent = 0

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                # Log ALL lines to file for debugging
                all_output.append(line)
                logger.debug(f"yt-dlp: {line}")

                # Log errors and warnings prominently
                if "ERROR" in line or "error" in line.lower():
                    logger.error(f"yt-dlp ERROR: {line}")
                    self.log_message(f"[ERROR] {line}")
                    continue

                if "WARNING" in line or "warning" in line.lower():
                    logger.warning(f"yt-dlp WARNING: {line}")
                    continue

                # Extract temp file path from Destination line
                if "[download] Destination:" in line:
                    match = re.search(r'Destination: (.+)', line)
                    if match:
                        temp_file_path = match.group(1)
                        # Remove format codes like .f399, .f251, etc.
                        stem = Path(temp_file_path).stem
                        # Strip format codes (e.g., ".f399" at the end)
                        clean_title = re.sub(r'\.f\d+$', '', stem)
                        if video_title == "Video":  # Only set on first occurrence
                            video_title = clean_title
                            self.log_message(f"[VIDEO] {video_title}")
                            logger.info(f"Video title: {video_title}")
                    continue

                # Extract file path from "has already been downloaded" line (for cached files)
                if "has already been downloaded" in line:
                    match = re.search(r'\[download\] (.+) has already been downloaded', line)
                    if match:
                        cached_file_path = match.group(1)
                        temp_file_path = cached_file_path  # Store the actual cached file path
                        stem = Path(cached_file_path).stem
                        clean_title = re.sub(r'\.f\d+$', '', stem)
                        if video_title == "Video":
                            video_title = clean_title
                            self.log_message(f"[VIDEO] {video_title} (cached)")
                            logger.info(f"Video title from cache: {video_title}")
                    continue

                # Handle completion - only show once when reaching 100%
                if "100%" in line and "[download]" in line and last_percent < 100:
                    last_percent = 100
                    self.log_message(f"[SUCCESS] Download complete!")
                    continue

                # Show download progress (but not 100% since we handle that above)
                if "%" in line and "[download]" in line and "100%" not in line:
                    # Extract percentage
                    percent_match = re.search(r'(\d+\.\d+)%', line)
                    if percent_match:
                        current = float(percent_match.group(1))
                        # Only log every 10% to reduce spam
                        if int(current / 10) > int(last_percent / 10):
                            self.log_message(f"[PROGRESS] {current:.1f}%")
                            last_percent = current
                    continue

                # Show merging/post-processing
                if line.startswith("[Merger]") or line.startswith("[ExtractAudio]"):
                    self.log_message(f"[PROCESSING] Merging streams...")
                    continue

            process.wait()
            logger.info(f"yt-dlp exit code: {process.returncode}")

            # Check if download was successful
            if process.returncode != 0 and last_percent < 99:
                self.log_message(f"\n[FAILED] Download failed with error code {process.returncode}\n")
                logger.error(f"Download failed for {url} with exit code {process.returncode}")
                logger.error(f"Full yt-dlp output:\n" + "\n".join(all_output[-50:]))  # Last 50 lines
                return

            # Find the downloaded file
            # PRIORITY 1: Use temp_file_path if we got it from yt-dlp output
            if temp_file_path and os.path.exists(temp_file_path):
                temp_file = temp_file_path
                logger.info(f"Using file path from yt-dlp output: {temp_file}")
            else:
                # PRIORITY 2: Search for the file by title
                all_files = os.listdir(TEMP_FOLDER)

                # First try exact match
                merged_files = [f for f in all_files
                               if f.startswith(video_title)
                               and not re.search(r'\.f\d+\.(webm|mp4|m4a)$', f)]

                # If no exact match, try fuzzy match (first 20 chars, handles special characters)
                if not merged_files:
                    # Use first 20 characters for matching (handles : vs ： differences)
                    title_prefix = video_title[:20] if len(video_title) > 20 else video_title
                    merged_files = [f for f in all_files
                                   if f[:20].replace('：', ' ').replace(':', ' ').strip() == title_prefix.strip()
                                   and not re.search(r'\.f\d+\.(webm|mp4|m4a)$', f)]

                # PRIORITY 3: Fallback to NEWEST mp4/webm file (sorted by modification time)
                if not merged_files:
                    video_files = [f for f in all_files
                                   if f.endswith(('.mp4', '.webm', '.mkv'))
                                   and not re.search(r'\.f\d+\.(webm|mp4|m4a)$', f)]
                    if video_files:
                        # Sort by modification time (newest first)
                        video_files.sort(key=lambda f: os.path.getmtime(os.path.join(TEMP_FOLDER, f)), reverse=True)
                        merged_files = [video_files[0]]  # Take the newest one
                        logger.warning(f"Using fallback: newest file {merged_files[0]} (no title match found)")
                        self.log_message(f"[WARN] Using newest file as fallback")

                if not merged_files:
                    self.log_message(f"\n[ERROR] Merged file not found. Files in temp: {all_files}\n")
                    self.log_message(f"[DEBUG] Looking for files starting with: {video_title}\n")
                    return

                # Get the merged file
                temp_file = os.path.join(TEMP_FOLDER, merged_files[0])
            file_extension = Path(temp_file).suffix

            # Use the actual filename from the temp file (handles special characters correctly)
            actual_filename = Path(temp_file).stem

            # Clean up partial stream files (.f399, .f251, etc.)
            all_files = os.listdir(TEMP_FOLDER)
            for f in all_files:
                if re.search(r'\.f\d+\.(webm|mp4|m4a)$', f):
                    try:
                        os.remove(os.path.join(TEMP_FOLDER, f))
                    except:
                        pass

            # Target file in final download folder (use actual filename)
            target_file = os.path.join(DOWNLOAD_FOLDER, f"{actual_filename}{file_extension}")

            # Check if file already exists in download folder
            if os.path.exists(target_file):
                self.log_message(f"\n[NOTICE] File already exists in download folder\n")
                # Ask user what to do (must be called from main thread)
                # IMPORTANT: Clear temp_file variable so finally block doesn't delete it
                temp_file_for_dialog = temp_file
                temp_file = None  # Prevent finally block from deleting
                self.after(0, lambda t=temp_file_for_dialog, v=actual_filename, e=file_extension:
                          self.show_file_exists_dialog_with_temp(t, v, e, url))
                return

            # Move file from temp to final location
            self.log_message(f"[MOVING] Moving to download folder...")
            import shutil
            shutil.move(temp_file, target_file)
            temp_file = None  # Clear so we don't delete it in finally

            self.log_message(f"\n[DONE] Successfully downloaded: {actual_filename}\n")
            self.log_message(f"[SAVED] {target_file}\n")
            self.add_to_history(actual_filename, url, f"{actual_filename}{file_extension}")

            # Check codec compatibility if enabled
            if self.settings.get("check_compatibility", True) and CODEC_UTILS_AVAILABLE:
                self._check_and_handle_compatibility(target_file, actual_filename)

        except Exception as e:
            self.log_message(f"\n[ERROR] Download failed: {e}\n")
            logger.exception(f"Download exception for {url}: {e}")
            if all_output:
                logger.error(f"Last yt-dlp output before error:\n" + "\n".join(all_output[-30:]))
        finally:
            # Clean up temp file if it still exists
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            self.is_downloading = False

    def _download_channel_thread(self, url):
        """Download entire channel in separate thread"""
        try:
            self.is_downloading = True
            self.log_message(f"\n[START] Downloading channel...")
            self.log_message(f"[URL] {url}")
            self.log_message(f"[FOLDER] {DOWNLOAD_FOLDER}")
            self.log_message(f"[INFO] This may take a while...\n")

            # Build yt-dlp command for channel
            node_path = self._find_node_path()
            cmd = [
                "yt-dlp",
                "-o", f"{DOWNLOAD_FOLDER}/%(uploader)s/%(title)s.%(ext)s",
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                "--yes-playlist",
                "--merge-output-format", self.settings.get("output_format", "mp4"),  # Force mp4 output
                # YouTube extraction requires JavaScript runtime
                "--js-runtimes", f"node:{node_path}" if node_path else "node",
                            ]
            cmd.extend(self._get_cookie_args())
            cmd.append(url)

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bv*+ba/b"])  # Best video+audio, or best combined
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bv*[height<={quality}]+ba/b"])  # Best video at quality+audio, or best combined

            # Run yt-dlp
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Capture output
            video_count = 0
            current_item_number = 0
            total_items = 0
            shown_video_title = False

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                # Detect new video starting - extract item number
                if "[download] Downloading item" in line or "[download] Downloading video" in line:
                    # Extract numbers like "item 5 of 385"
                    item_match = re.search(r'item (\d+) of (\d+)', line)
                    if item_match:
                        new_item = int(item_match.group(1))
                        total_items = int(item_match.group(2))

                        # If item number changed, mark previous video as complete
                        if current_item_number > 0 and new_item > current_item_number:
                            self.log_message(f"[SUCCESS] Video #{current_item_number} of {total_items} complete!\n")

                        current_item_number = new_item
                        shown_video_title = False
                        self.log_message(f"[DOWNLOADING] Video {current_item_number} of {total_items}...")
                    continue

                # Show video title only ONCE per video (not for each stream)
                if "[download] Destination:" in line and not shown_video_title:
                    match = re.search(r'Destination: (.+)', line)
                    if match:
                        dest = match.group(1)
                        # Extract just the base title (without format codes)
                        title = Path(dest).stem
                        # Remove format codes like .f248, .f251, etc
                        title = re.sub(r'\.[f\d]+$', '', title)
                        if title and not shown_video_title:
                            self.log_message(f"[VIDEO] {title}")
                            shown_video_title = True
                    continue

                # Skip "100% of X.XMiB" lines - these are stream completions, not video completions
                if "100% of" in line and "MiB" in line:
                    continue

                # Show download progress (percentage only)
                if "%" in line and "[download]" in line and "of" not in line:
                    # Only show actual download progress, not "100% of XMiB" messages
                    percent_match = re.search(r'(\d+\.\d+)%', line)
                    if percent_match:
                        current = float(percent_match.group(1))
                        # Only log every 20% to reduce spam for channels
                        if int(current / 20) > 0 and current < 100:
                            self.log_message(f"[PROGRESS] {current:.1f}%")
                    continue

                # Show sleeping messages (rate limiting)
                if "Sleeping" in line:
                    self.log_message(f"[WAIT] {line}")
                    continue

                # Show merging/post-processing
                if line.startswith("[Merger]") or line.startswith("[ExtractAudio]"):
                    self.log_message(f"[PROCESSING] Merging streams...")
                    continue

            # Mark final video as complete
            if current_item_number > 0:
                self.log_message(f"[SUCCESS] Video #{current_item_number} of {total_items} complete!\n")
                video_count = current_item_number

            process.wait()

            if process.returncode == 0:
                self.log_message(f"\n[DONE] Successfully downloaded {video_count} videos from channel!\n")
            else:
                self.log_message(f"\n[FAILED] Channel download failed with error code {process.returncode}\n")

        except Exception as e:
            self.log_message(f"\n[ERROR] Channel download failed: {e}\n")
        finally:
            self.is_downloading = False

    def _download_video_as_copy_thread(self, url, original_title):
        """Download video with (2) suffix"""
        try:
            self.is_downloading = True
            self.log_message(f"\n[START] Downloading copy...")
            self.log_message(f"[URL] {url}\n")

            # Generate unique filename by adding (2), (3), etc.
            base_name = re.sub(r'_\d{8}_\d{6}$', '', original_title)  # Remove timestamp if exists
            counter = 2
            unique_name = f"{base_name} ({counter})"

            # Check if file with (2) already exists, increment if needed
            while os.path.exists(os.path.join(DOWNLOAD_FOLDER, f"{unique_name}.mp4")) or \
                  os.path.exists(os.path.join(DOWNLOAD_FOLDER, f"{unique_name}.webm")) or \
                  os.path.exists(os.path.join(DOWNLOAD_FOLDER, f"{unique_name}.mkv")):
                counter += 1
                unique_name = f"{base_name} ({counter})"

            # Build command with custom output template
            node_path = self._find_node_path()
            cmd = [
                "yt-dlp",
                "-o", f"{DOWNLOAD_FOLDER}/{unique_name}.%(ext)s",
                "--no-playlist",
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                "--js-runtimes", f"node:{node_path}" if node_path else "node",
                                url
            ]

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bv*+ba/b"])  # Best video+audio, or best combined
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bv*[height<={quality}]+ba/b"])  # Best video at quality+audio, or best combined

            # Run download
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            last_percent = 0
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                # Show progress every 10% to reduce spam
                if "%" in line and "[download]" in line and "100% of" not in line:
                    percent_match = re.search(r'(\d+\.\d+)%', line)
                    if percent_match:
                        current = float(percent_match.group(1))
                        if int(current / 10) > int(last_percent / 10):
                            self.log_message(f"[PROGRESS] {current:.1f}%")
                            last_percent = current

            process.wait()

            # Success if returncode is 0 OR if download completed
            if process.returncode == 0 or last_percent >= 99:
                self.log_message(f"\n[DONE] Downloaded as: {unique_name}\n")
                self.add_to_history(unique_name, url, f"{unique_name}.mp4")
            else:
                self.log_message(f"\n[FAILED] Download failed (error code {process.returncode})\n")

        except Exception as e:
            self.log_message(f"\n[ERROR] Download failed: {e}\n")
        finally:
            self.is_downloading = False

    def _download_video_replace_thread(self, url):
        """Download video and replace existing file"""
        try:
            self.is_downloading = True
            self.log_message(f"\n[START] Re-downloading to replace existing file...")
            self.log_message(f"[URL] {url}\n")

            # Build command with force overwrite
            node_path = self._find_node_path()
            cmd = [
                "yt-dlp",
                "-o", f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
                "--no-playlist",
                "--force-overwrites",  # Replace existing file
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                "--js-runtimes", f"node:{node_path}" if node_path else "node",
                                url
            ]

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bv*+ba/b"])  # Best video+audio, or best combined
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bv*[height<={quality}]+ba/b"])  # Best video at quality+audio, or best combined

            # Run download
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            video_title = "Video"
            last_percent = 0

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                if "[download] Destination:" in line:
                    match = re.search(r'Destination: (.+)', line)
                    if match:
                        video_title = Path(match.group(1)).stem
                        self.log_message(f"[VIDEO] {video_title}")
                    continue

                # Show progress every 10% to reduce spam
                if "%" in line and "[download]" in line and "100% of" not in line:
                    percent_match = re.search(r'(\d+\.\d+)%', line)
                    if percent_match:
                        current = float(percent_match.group(1))
                        if int(current / 10) > int(last_percent / 10):
                            self.log_message(f"[PROGRESS] {current:.1f}%")
                            last_percent = current

            process.wait()

            # Success if returncode is 0 OR if download completed
            if process.returncode == 0 or last_percent >= 99:
                self.log_message(f"\n[DONE] Replaced: {video_title}\n")
                self.add_to_history(video_title, url, f"{video_title}.mp4")
            else:
                self.log_message(f"\n[FAILED] Download failed (error code {process.returncode})\n")

        except Exception as e:
            self.log_message(f"\n[ERROR] Download failed: {e}\n")
        finally:
            self.is_downloading = False

    # ========================================================================
    # Codec Detection and Conversion Methods
    # ========================================================================

    def _check_and_handle_compatibility(self, file_path, video_title):
        """Check codec compatibility and handle accordingly"""
        if not CODEC_UTILS_AVAILABLE:
            return

        try:
            self.log_message(f"\n[CODEC] Checking compatibility...")
            info = detect_codecs(file_path)

            # Log codec information
            self.log_message(f"[CODEC] Video: {info.video_codec.value} ({info.video_profile})")
            self.log_message(f"[CODEC] Audio: {info.audio_codec.value}")
            self.log_message(f"[CODEC] Compatibility: {info.compatibility.value}")

            if info.needs_conversion:
                # Log issues
                for issue in info.compatibility_issues:
                    self.log_message(f"[WARNING] {issue}")

                if self.settings.get("auto_convert", False):
                    # Auto-convert
                    self.log_message(f"\n[CONVERT] Auto-converting for compatibility...")
                    self._convert_video(file_path, info)
                else:
                    # Show dialog on main thread
                    self.after(0, lambda: self._show_compatibility_dialog(file_path, video_title, info))
            else:
                self.log_message(f"[OK] File is compatible with all devices")

        except Exception as e:
            self.log_message(f"[CODEC ERROR] {e}")

    def _show_compatibility_dialog(self, file_path, video_title, info):
        """Show dialog asking user if they want to convert"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Codec Compatibility Issue")
        dialog.geometry("700x400")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (350)
        y = (dialog.winfo_screenheight() // 2) - (200)
        dialog.geometry(f"+{x}+{y}")

        # Title
        title_label = ctk.CTkLabel(
            dialog,
            text="⚠️ Compatibility Issues Detected",
            font=("Arial", 22, "bold"),
            text_color=COLORS["warning"]
        )
        title_label.pack(pady=15)

        # Video name
        name_label = ctk.CTkLabel(
            dialog,
            text=video_title[:60] + "..." if len(video_title) > 60 else video_title,
            font=("Arial", 14),
            text_color=COLORS["text"]
        )
        name_label.pack(pady=5)

        # Issues frame
        issues_frame = ctk.CTkFrame(dialog, fg_color=COLORS["card_bg"])
        issues_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            issues_frame,
            text=f"Video Codec: {info.video_codec.value}  |  Audio Codec: {info.audio_codec.value}",
            font=("Arial", 12),
            text_color=COLORS["text"]
        ).pack(pady=5)

        for issue in info.compatibility_issues:
            ctk.CTkLabel(
                issues_frame,
                text=f"• {issue}",
                font=("Arial", 11),
                text_color=COLORS["warning"],
                anchor="w"
            ).pack(padx=20, pady=2, anchor="w")

        # Explanation
        explain_label = ctk.CTkLabel(
            dialog,
            text="This file may not play on mobile devices or PLEX.\nConvert to AAC audio for maximum compatibility.",
            font=("Arial", 12),
            text_color=COLORS["text"]
        )
        explain_label.pack(pady=10)

        # Buttons frame
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)

        def convert():
            dialog.destroy()
            threading.Thread(target=self._convert_video, args=(file_path, info), daemon=True).start()

        def skip():
            dialog.destroy()
            self.log_message(f"[SKIP] Keeping original file (may not play on all devices)")

        convert_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 Convert Now",
            command=convert,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=40
        )
        convert_btn.pack(side="left", padx=10)

        skip_btn = ctk.CTkButton(
            btn_frame,
            text="Skip",
            command=skip,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 14),
            width=100,
            height=40
        )
        skip_btn.pack(side="left", padx=10)

    def _convert_video(self, file_path, info):
        """Convert video for compatibility"""
        try:
            self.log_message(f"\n[CONVERT] Converting audio to AAC...")

            # Determine what to convert
            convert_video = info.video_needs_conversion if hasattr(info, 'video_needs_conversion') else False
            convert_audio = info.audio_needs_conversion if hasattr(info, 'audio_needs_conversion') else True

            # Generate output path
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_compatible.mp4"

            # Progress callback
            def progress_callback(progress):
                self.after(0, lambda: self.log_message(f"[CONVERT] {progress.percent:.1f}% - {progress.speed}"))

            # Run conversion
            success = convert_for_compatibility(
                input_path=file_path,
                output_path=output_path,
                convert_video=convert_video,
                convert_audio=convert_audio,
                progress_callback=progress_callback
            )

            if success:
                # Get file sizes for comparison
                original_size = os.path.getsize(file_path)
                new_size = os.path.getsize(output_path)

                self.log_message(f"\n[SUCCESS] Conversion complete!")
                self.log_message(f"[INFO] Original: {original_size / 1024 / 1024:.1f} MB")
                self.log_message(f"[INFO] Converted: {new_size / 1024 / 1024:.1f} MB")
                self.log_message(f"[SAVED] {output_path}")

                # Ask if user wants to delete original
                self.after(0, lambda: self._ask_delete_original(file_path, output_path))
            else:
                self.log_message(f"\n[FAILED] Conversion failed")

        except Exception as e:
            self.log_message(f"\n[ERROR] Conversion error: {e}")

    def _ask_delete_original(self, original_path, converted_path):
        """Ask user if they want to delete the original file"""
        result = messagebox.askyesno(
            "Delete Original?",
            f"Conversion successful!\n\nWould you like to delete the original file?\n\n"
            f"Original: {os.path.basename(original_path)}\n"
            f"Converted: {os.path.basename(converted_path)}"
        )

        if result:
            try:
                os.remove(original_path)
                # Rename converted file to original name
                os.rename(converted_path, original_path)
                self.log_message(f"[CLEANUP] Original replaced with converted version")
            except Exception as e:
                self.log_message(f"[ERROR] Could not delete original: {e}")

    def update_history_display(self):
        """Update the recent downloads display"""
        # Clear existing
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        if not self.history:
            empty_label = ctk.CTkLabel(
                self.history_frame,
                text="No downloads yet",
                font=("Arial", 12),
                text_color=COLORS["text"]
            )
            empty_label.pack(pady=10)
            return

        # Add each history item
        for entry in self.history[:10]:  # Show last 10
            item_frame = ctk.CTkFrame(self.history_frame, fg_color=COLORS["card_bg"])
            item_frame.pack(fill="x", pady=2, padx=5)

            title_label = ctk.CTkLabel(
                item_frame,
                text=f"✓ {entry.get('title', 'Unknown')}",
                font=("Arial", 12),
                text_color=COLORS["success"],
                anchor="w"
            )
            title_label.pack(side="left", padx=10, pady=5, fill="x", expand=True)

            # Open file button
            if entry.get('filename'):
                filepath = os.path.join(DOWNLOAD_FOLDER, entry['filename'])
                if os.path.exists(filepath):
                    open_btn = ctk.CTkButton(
                        item_frame,
                        text="📂 Open",
                        command=lambda fp=filepath: os.startfile(fp),
                        fg_color=COLORS["card_bg"],
                        hover_color=COLORS["card_hover"],
                        width=80,
                        height=30,
                        font=("Arial", 11, "bold")
                    )
                    open_btn.pack(side="right", padx=5)

    def open_download_folder(self):
        """Open downloads folder in Windows Explorer"""
        try:
            if os.path.exists(DOWNLOAD_FOLDER):
                os.startfile(DOWNLOAD_FOLDER)
            else:
                # Create folder if it doesn't exist
                os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
                os.startfile(DOWNLOAD_FOLDER)
        except Exception as e:
            logger.error(f"Failed to open folder: {e}")
            # Fallback: try subprocess
            try:
                subprocess.Popen(['explorer', DOWNLOAD_FOLDER])
            except Exception as e2:
                messagebox.showerror("Error", f"Could not open folder: {e2}")

    def show_file_exists_dialog(self, url, title):
        """Show dialog when file already exists"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("File Already Exists")
        dialog.geometry("650x300")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (650 // 2)
        y = (dialog.winfo_screenheight() // 2) - (300 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Title
        title_label = ctk.CTkLabel(
            dialog,
            text="⚠️ File Already Exists",
            font=("Arial", 24, "bold"),
            text_color=COLORS["warning"]
        )
        title_label.pack(pady=20)

        # Message
        message_frame = ctk.CTkFrame(dialog, fg_color=COLORS["card_bg"])
        message_frame.pack(fill="x", padx=30, pady=10)

        message_label = ctk.CTkLabel(
            message_frame,
            text=f"'{title}' already exists.\n\nWhat would you like to do?",
            font=("Arial", 14),
            text_color=COLORS["text"],
            justify="center"
        )
        message_label.pack(pady=20, padx=20)

        # Button frame
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=20)

        def skip():
            self.log_message(f"[SKIPPED] User chose to skip existing file\n")
            dialog.destroy()
            self.is_downloading = False

        def download_copy():
            dialog.destroy()
            self.log_message(f"[REDOWNLOAD] Downloading as copy with (2) suffix...\n")
            # Start new download with unique filename
            thread = threading.Thread(target=self._download_video_as_copy_thread, args=(url, title))
            thread.daemon = True
            thread.start()

        def replace():
            dialog.destroy()
            self.log_message(f"[REPLACE] Re-downloading to replace existing file...\n")
            # Start new download with force overwrite
            thread = threading.Thread(target=self._download_video_replace_thread, args=(url,))
            thread.daemon = True
            thread.start()

        # Buttons
        skip_btn = ctk.CTkButton(
            button_frame,
            text="⏭️ Skip",
            command=skip,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=50
        )
        skip_btn.pack(side="left", padx=10)

        copy_btn = ctk.CTkButton(
            button_frame,
            text="📋 Download as (2)",
            command=download_copy,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=180,
            height=50
        )
        copy_btn.pack(side="left", padx=10)

        replace_btn = ctk.CTkButton(
            button_frame,
            text="🔄 Replace",
            command=replace,
            fg_color=COLORS["warning"],
            hover_color="#CC8800",
            font=("Arial", 14, "bold"),
            width=150,
            height=50
        )
        replace_btn.pack(side="left", padx=10)

    def show_file_exists_dialog_with_temp(self, temp_file, video_title, file_extension, url):
        """Show dialog when file already exists - handles temp file cleanup/move"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("File Already Exists")
        dialog.geometry("650x300")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self)
        dialog.grab_set()

        # Handle dialog close (X button) - clean up temp file
        def on_dialog_close():
            self.log_message(f"[CANCELLED] User closed dialog - deleting temp file\n")
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    self.log_message(f"[CLEANUP] Temp file deleted\n")
            except Exception as e:
                self.log_message(f"[ERROR] Could not delete temp file: {e}\n")
            self.is_downloading = False
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (650 // 2)
        y = (dialog.winfo_screenheight() // 2) - (300 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Title
        title_label = ctk.CTkLabel(
            dialog,
            text="File Already Exists",
            font=("Arial", 24, "bold"),
            text_color=COLORS["warning"]
        )
        title_label.pack(pady=20)

        # Message
        message_frame = ctk.CTkFrame(dialog, fg_color=COLORS["card_bg"])
        message_frame.pack(fill="x", padx=30, pady=10)

        message_label = ctk.CTkLabel(
            message_frame,
            text=f"'{video_title}' already exists.\n\nWhat would you like to do?",
            font=("Arial", 14),
            text_color=COLORS["text"],
            justify="center"
        )
        message_label.pack(pady=20, padx=20)

        # Button frame
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=20)

        def skip():
            self.log_message(f"[SKIPPED] User chose to skip - deleting temp file\n")
            dialog.destroy()
            # Delete temp file
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    self.log_message(f"[CLEANUP] Temp file deleted\n")
            except Exception as e:
                self.log_message(f"[ERROR] Could not delete temp file: {e}\n")
            self.is_downloading = False

        def download_copy():
            dialog.destroy()
            self.log_message(f"[COPY] Renaming as (2) and moving to download folder...\n")
            # Rename temp file with (2) suffix
            try:
                # Check if temp file still exists
                if not os.path.exists(temp_file):
                    self.log_message(f"[ERROR] Temp file no longer exists: {temp_file}\n")
                    self.is_downloading = False
                    return

                # Find next available number
                counter = 2
                target_file = os.path.join(DOWNLOAD_FOLDER, f"{video_title} ({counter}){file_extension}")
                while os.path.exists(target_file):
                    counter += 1
                    target_file = os.path.join(DOWNLOAD_FOLDER, f"{video_title} ({counter}){file_extension}")

                self.log_message(f"[DEBUG] Moving from: {temp_file}\n")
                self.log_message(f"[DEBUG] Moving to: {target_file}\n")

                # Move temp file to target
                import shutil
                shutil.move(temp_file, target_file)
                self.log_message(f"[DONE] Saved as: {Path(target_file).name}\n")
                self.add_to_history(f"{video_title} ({counter})", url, Path(target_file).name)
            except Exception as e:
                import traceback
                self.log_message(f"[ERROR] Could not move file: {e}\n")
                self.log_message(f"[ERROR] Traceback: {traceback.format_exc()}\n")
            self.is_downloading = False

        def replace():
            dialog.destroy()
            self.log_message(f"[REPLACE] Replacing existing file...\n")
            try:
                # Check if temp file still exists
                if not os.path.exists(temp_file):
                    self.log_message(f"[ERROR] Temp file no longer exists: {temp_file}\n")
                    self.is_downloading = False
                    return

                target_file = os.path.join(DOWNLOAD_FOLDER, f"{video_title}{file_extension}")
                # Delete old file
                if os.path.exists(target_file):
                    os.remove(target_file)
                    self.log_message(f"[DELETED] Removed old file\n")

                self.log_message(f"[DEBUG] Moving from: {temp_file}\n")
                self.log_message(f"[DEBUG] Moving to: {target_file}\n")

                # Move temp file to target
                import shutil
                shutil.move(temp_file, target_file)
                self.log_message(f"[DONE] File replaced successfully\n")
                self.add_to_history(video_title, url, f"{video_title}{file_extension}")
            except Exception as e:
                import traceback
                self.log_message(f"[ERROR] Could not replace file: {e}\n")
                self.log_message(f"[ERROR] Traceback: {traceback.format_exc()}\n")
            self.is_downloading = False

        # Buttons
        skip_btn = ctk.CTkButton(
            button_frame,
            text="Skip",
            command=skip,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=50
        )
        skip_btn.pack(side="left", padx=10)

        copy_btn = ctk.CTkButton(
            button_frame,
            text="Download as (2)",
            command=download_copy,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=180,
            height=50
        )
        copy_btn.pack(side="left", padx=10)

        replace_btn = ctk.CTkButton(
            button_frame,
            text="Replace",
            command=replace,
            fg_color=COLORS["warning"],
            hover_color="#CC8800",
            font=("Arial", 14, "bold"),
            width=150,
            height=50
        )
        replace_btn.pack(side="left", padx=10)

    def open_settings(self):
        """Open settings dialog"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("600x550")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (550 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Title
        title = ctk.CTkLabel(
            dialog,
            text="⚙️ Settings",
            font=("Arial", 24, "bold"),
            text_color=COLORS["text"]
        )
        title.pack(pady=20)

        # Settings frame
        settings_frame = ctk.CTkFrame(dialog, fg_color=COLORS["card_bg"])
        settings_frame.pack(fill="both", expand=True, padx=30, pady=10)

        # Video quality
        quality_label = ctk.CTkLabel(
            settings_frame,
            text="Video Quality:",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text"]
        )
        quality_label.pack(pady=(20, 10), padx=20, anchor="w")

        quality_var = ctk.StringVar(value=self.settings.get("video_quality", "best"))

        for quality in ["best", "1080p", "720p", "480p"]:
            radio = ctk.CTkRadioButton(
                settings_frame,
                text=quality.upper(),
                variable=quality_var,
                value=quality,
                font=("Arial", 14),
                text_color=COLORS["text"]
            )
            radio.pack(pady=5, padx=40, anchor="w")

        # Audio only
        audio_var = ctk.BooleanVar(value=self.settings.get("audio_only", False))

        audio_check = ctk.CTkCheckBox(
            settings_frame,
            text="Download audio only (MP3)",
            variable=audio_var,
            font=("Arial", 14),
            text_color=COLORS["text"]
        )
        audio_check.pack(pady=20, padx=20, anchor="w")

        # Output format
        format_label = ctk.CTkLabel(
            settings_frame,
            text="Output Format:",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text"]
        )
        format_label.pack(pady=(20, 10), padx=20, anchor="w")

        format_var = ctk.StringVar(value=self.settings.get("output_format", "mp4"))

        for fmt in ["mp4", "webm"]:
            radio = ctk.CTkRadioButton(
                settings_frame,
                text=fmt.upper(),
                variable=format_var,
                value=fmt,
                font=("Arial", 14),
                text_color=COLORS["text"]
            )
            radio.pack(pady=5, padx=40, anchor="w")

        # Save button
        def save_settings():
            self.settings["video_quality"] = quality_var.get()
            self.settings["audio_only"] = audio_var.get()
            self.settings["output_format"] = format_var.get()
            self.save_settings()
            dialog.destroy()
            messagebox.showinfo("Settings", "Settings saved successfully!")

        save_btn = ctk.CTkButton(
            dialog,
            text="✅ Save Settings",
            command=save_settings,
            fg_color=COLORS["success"],
            hover_color="#00CC00",
            font=("Arial", 16, "bold"),
            width=200,
            height=45
        )
        save_btn.pack(pady=20)

    def on_closing(self):
        """Handle window close"""
        if self.is_downloading:
            response = messagebox.askyesno(
                "Download in Progress",
                "A download is currently in progress. Are you sure you want to quit?"
            )
            if not response:
                return
        self.destroy()


def main():
    """Main entry point"""
    # Verify download folder exists
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    # Set appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create and run app
    app = QuickTubeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
