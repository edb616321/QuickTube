"""
QuickTube - Simple YouTube Downloader
Paste URL, download video or channel - that's it!
Includes codec detection and conversion for maximum compatibility.
"""

import customtkinter as ctk
import os
import json
import threading
import subprocess
import re
from datetime import datetime
from pathlib import Path
import pyperclip
from tkinter import messagebox

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
SETTINGS_FILE = "settings.json"
HISTORY_FILE = "download_history.json"

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

        # Load settings and history
        self.settings = self.load_settings()
        self.history = self.load_history()

        # Ensure temp folder exists
        os.makedirs(TEMP_FOLDER, exist_ok=True)

        # Create UI
        self.create_ui()

        # Bind keyboard shortcuts
        self.bind("<Control-v>", lambda e: self.url_entry.event_generate('<<Paste>>'))

        # Protocol for window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

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

        # URL Input section
        input_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=10)
        input_frame.pack(fill="x", padx=20, pady=10)

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

        # Progress section
        progress_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=10)
        progress_frame.pack(fill="both", expand=True, padx=20, pady=10)

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
            height=300
        )
        self.progress_display.pack(fill="both", expand=True, padx=15, pady=(5, 10))

        # History section
        history_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=10)
        history_frame.pack(fill="x", padx=20, pady=10)

        history_title = ctk.CTkLabel(
            history_frame,
            text="📝 Recent Downloads",
            font=("Arial", 16, "bold"),
            text_color=COLORS["text"]
        )
        history_title.pack(anchor="w", padx=15, pady=(10, 5))

        self.history_frame = ctk.CTkScrollableFrame(
            history_frame,
            fg_color=COLORS["progress_bg"],
            height=200
        )
        self.history_frame.pack(fill="both", padx=10, pady=(0, 10))

        self.update_history_display()

        # Bottom buttons
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=20, pady=(0, 20))

        open_folder_btn = ctk.CTkButton(
            bottom_frame,
            text="📁 Open Downloads Folder",
            command=self.open_download_folder,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=("Arial", 14, "bold"),
            width=200,
            height=40
        )
        open_folder_btn.pack(side="left", padx=5)

        settings_btn = ctk.CTkButton(
            bottom_frame,
            text="⚙️ Settings",
            command=self.open_settings,
            fg_color=COLORS["card_bg"],
            hover_color=COLORS["card_hover"],
            font=("Arial", 14, "bold"),
            width=150,
            height=40
        )
        settings_btn.pack(side="left", padx=5)

        close_btn = ctk.CTkButton(
            bottom_frame,
            text="❌ Close",
            command=self.on_closing,
            fg_color=COLORS["error"],
            hover_color="#CC0000",
            font=("Arial", 14, "bold"),
            width=150,
            height=40
        )
        close_btn.pack(side="right", padx=5)

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

    def _download_video_thread(self, url):
        """Download video in separate thread - downloads to temp first, then moves to final location"""
        temp_file = None
        try:
            self.is_downloading = True
            self.log_message(f"\n[START] Downloading video...")
            self.log_message(f"[URL] {url}")
            self.log_message(f"[TEMP] Downloading to temp folder first...\n")

            # Build yt-dlp command - download to TEMP folder
            cmd = [
                "yt-dlp",
                "-o", f"{TEMP_FOLDER}/%(title)s.%(ext)s",
                "--no-playlist",  # IMPORTANT: Download ONLY this video, not the whole playlist
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                "--merge-output-format", self.settings.get("output_format", "mp4"),  # Force mp4 output
                url
            ]

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bestvideo*+bestaudio/best"])
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bestvideo[height<={quality}]+bestaudio/best"])

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

                # Extract temp file path
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

            # Check if download was successful
            if process.returncode != 0 and last_percent < 99:
                self.log_message(f"\n[FAILED] Download failed with error code {process.returncode}\n")
                return

            # Find the merged file (without format codes like .f399, .f251)
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

            # If still no match, just get any mp4/webm file (not a stream file)
            if not merged_files:
                merged_files = [f for f in all_files
                               if f.endswith(('.mp4', '.webm', '.mkv'))
                               and not re.search(r'\.f\d+\.(webm|mp4|m4a)$', f)]

            if not merged_files:
                self.log_message(f"\n[ERROR] Merged file not found. Files in temp: {all_files}\n")
                self.log_message(f"[DEBUG] Looking for files starting with: {video_title}\n")
                return

            # Get the merged file (should be only one)
            temp_file = os.path.join(TEMP_FOLDER, merged_files[0])
            file_extension = Path(temp_file).suffix

            # Use the actual filename from the merged file (handles special characters correctly)
            actual_filename = Path(merged_files[0]).stem

            # Clean up partial stream files (.f399, .f251, etc.)
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
            cmd = [
                "yt-dlp",
                "-o", f"{DOWNLOAD_FOLDER}/%(uploader)s/%(title)s.%(ext)s",
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                "--yes-playlist",
                "--merge-output-format", self.settings.get("output_format", "mp4"),  # Force mp4 output
                url
            ]

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bestvideo*+bestaudio/best"])
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bestvideo[height<={quality}]+bestaudio/best"])

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
            cmd = [
                "yt-dlp",
                "-o", f"{DOWNLOAD_FOLDER}/{unique_name}.%(ext)s",
                "--no-playlist",
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                url
            ]

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bestvideo*+bestaudio/best"])
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bestvideo[height<={quality}]+bestaudio/best"])

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
            cmd = [
                "yt-dlp",
                "-o", f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
                "--no-playlist",
                "--force-overwrites",  # Replace existing file
                "--progress",
                "--newline",
                "--no-colors",
                "--console-title", "",
                url
            ]

            # Add quality options
            if self.settings.get("audio_only"):
                cmd.extend(["-f", "bestaudio", "-x"])
            else:
                quality = self.settings.get("video_quality", "best")
                if quality == "best":
                    # Get the absolute highest quality video and audio
                    cmd.extend(["-f", "bestvideo*+bestaudio/best"])
                    # Ensure we prefer higher resolution
                    cmd.extend(["-S", "res,vcodec:h264"])
                else:
                    cmd.extend(["-f", f"bestvideo[height<={quality}]+bestaudio/best"])

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
        os.startfile(DOWNLOAD_FOLDER)

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
