# QuickTube Progress Display Fixes

## CRITICAL FIX: Temp Folder Architecture (2025-11-05)

**Problem:** Downloading directly to D:\stacher_downloads caused errors when files already existed. yt-dlp would return error code 1, causing confusion and failed downloads.

**Solution:** Implemented temp folder download architecture:

### How It Works Now:

1. **Download Phase:**
   - All videos download to `D:\QuickTube\temp` first
   - No file conflicts during download
   - Clean progress tracking without interruption

2. **Check Phase:**
   - After download completes, check if file exists in `D:\stacher_downloads`
   - If file doesn't exist → move directly to download folder
   - If file exists → show user dialog with 3 options

3. **User Choice:**
   - **Skip**: Delete temp file, don't save
   - **Download as (2)**: Rename with number suffix, move to download folder
   - **Replace**: Delete old file, move new file from temp

### Benefits:

- ✓ No more yt-dlp file conflict errors
- ✓ Clean downloads every time
- ✓ User has full control over duplicates
- ✓ Automatic temp folder cleanup
- ✓ No partial files in download folder

### Code Changes:

```python
# Temp folder constant
TEMP_FOLDER = r"D:\QuickTube\temp"

# Download to temp first
cmd = [
    "yt-dlp",
    "-o", f"{TEMP_FOLDER}/%(title)s.%(ext)s",  # Temp folder!
    "--no-playlist",
    url
]

# After download, check and move
if os.path.exists(target_file):
    # Show dialog - let user decide
    self.show_file_exists_dialog_with_temp(temp_file, video_title, ext, url)
else:
    # Move directly to download folder
    shutil.move(temp_file, target_file)
```

## Issues Fixed (2025-11-05)

### 1. Progress Logic Order Bug
**Problem:** The code checked for lines containing "%" before checking for "100%", so completion messages never appeared.

**Fix:** Reordered checks to look for "100%" BEFORE generic "%"

```python
# BEFORE (broken):
if "[download]" in line and "%" in line:
    self.log_message(f"[PROGRESS] {line}")
elif "[download]" in line and "100%" in line:  # Never reached!
    self.log_message(f"[SUCCESS] Download complete!")

# AFTER (fixed):
if "100%" in line and "[download]" in line:  # Check first!
    self.log_message(f"[SUCCESS] Download complete!")
elif "%" in line and "[download]" in line:
    self.log_message(line)
```

### 2. Thread Safety
**Problem:** UI updates were called directly from background thread, which is unsafe in Tkinter.

**Fix:** Use `self.after(0, update)` to schedule UI updates on main thread

```python
def log_message(self, message):
    """Add message to progress display (thread-safe)"""
    def update():
        self.progress_display.configure(state="normal")
        self.progress_display.insert("end", f"{message}\n")
        self.progress_display.see("end")
        self.progress_display.configure(state="disabled")

    # Schedule update on main thread
    self.after(0, update)
```

### 3. Clean Output
**Problem:** ANSI color codes and console title updates cluttered the display.

**Fix:** Added yt-dlp flags to disable colors and console title

```python
cmd = [
    "yt-dlp",
    "--progress",
    "--newline",
    "--no-colors",          # Remove ANSI codes
    "--console-title", "",  # No title updates
    url
]
```

### 4. Better Message Filtering
**Problem:** Too many redundant messages, unclear what's happening.

**Fix:** Smarter filtering of yt-dlp output

```python
if "100%" in line and "[download]" in line:
    self.log_message(f"[SUCCESS] Download complete!")
elif "%" in line and "[download]" in line:
    self.log_message(line)  # Show progress
elif "[download]" in line:
    self.log_message(line)  # Show download info
elif line.startswith("["):
    self.log_message(line)  # Show other yt-dlp messages
```

## What You Should See Now

### Single Video Download:
```
[START] Downloading video...
[URL] https://youtube.com/watch?v=...
[FOLDER] D:\stacher_downloads

[VIDEO] Video Title Here
[download] Downloading video...
[download]  15.2%  5.2MiB   at 1.5MiB/s
[download]  28.4%  9.8MiB   at 1.8MiB/s
[download]  45.1% 15.4MiB   at 2.1MiB/s
[download]  67.8% 23.2MiB   at 2.3MiB/s
[download]  89.3% 30.5MiB   at 2.4MiB/s
[SUCCESS] Download complete!

[DONE] Successfully downloaded: Video Title Here
```

### Channel Download:
```
[START] Downloading channel...
[URL] https://youtube.com/@channel
[FOLDER] D:\stacher_downloads
[INFO] This may take a while...

[download] Downloading video 1 of 25
[download]  25.0%  10.2MiB  at 2.1MiB/s
[download]  50.0%  20.4MiB  at 2.3MiB/s
[download]  75.0%  30.6MiB  at 2.4MiB/s
[SUCCESS] Video #1 complete!

[download] Downloading video 2 of 25
...

[DONE] Successfully downloaded 25 videos from channel!
```

## Testing
Close and relaunch QuickTube to see the fixes:

```bash
cd D:\QuickTube
python quicktube.py
```

Try downloading a video and watch the clean, real-time progress display!
