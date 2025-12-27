# QuickTube - Simple YouTube Downloader

## Overview

QuickTube is a simple, clean YouTube downloader with a GUI interface. Just paste a URL and click download - that's it!

## Features

✅ **Simple Interface** - Paste URL, click download, done
✅ **Single Video or Channel** - Download one video or entire channels
✅ **Real-time Progress** - Watch downloads happen live
✅ **Download History** - Track what you've downloaded
✅ **Quality Settings** - Choose video quality (best, 1080p, 720p, 480p)
✅ **Audio Only Option** - Download as MP3
✅ **Clean UI** - Matches CCL launcher theme

## Installation

### Required

```bash
pip install yt-dlp customtkinter pyperclip
```

### Download Folder

All videos save to: `D:\stacher_downloads`

## Usage

### Launch QuickTube

```bash
cd D:\QuickTube
python quicktube.py
```

### Download Single Video

1. Copy YouTube video URL
2. Click **📋 Paste URL** (or Ctrl+V)
3. Click **🎬 Download Video**
4. Watch progress in real-time
5. Done! File is in `D:\stacher_downloads`

### Download Entire Channel

1. Copy YouTube channel URL
2. Click **📋 Paste URL**
3. Click **📺 Download Channel**
4. Confirm you want to download all videos
5. Videos download one by one
6. All videos save to `D:\stacher_downloads\[Channel Name]\`

## Supported URLs

- Single videos: `https://youtube.com/watch?v=...`
- Short links: `https://youtu.be/...`
- Channels: `https://youtube.com/@channelname`
- Playlists: `https://youtube.com/playlist?list=...`

## Settings

Click **⚙️ Settings** to configure:

### Video Quality
- **Best** (default) - Highest quality available
- **1080p** - Full HD
- **720p** - HD
- **480p** - SD

### Audio Only
- Check this to download MP3 audio only (no video)

## Codec Detection & Compatibility

QuickTube automatically checks downloaded videos for compatibility issues with mobile devices and media servers like PLEX.

### The Problem

YouTube sometimes encodes videos with codecs that don't work well on all devices:
- **Opus audio in MP4** - Won't play on many mobile devices or PLEX mobile apps
- **VP9 video** - Limited support on older devices
- **AV1 video** - Cutting-edge codec with limited device support

Videos may play fine on your computer but fail on phones, tablets, or streaming servers.

### Automatic Detection

After each download, QuickTube checks the video codec:
```
[CODEC] Checking: Video Title.mp4
[CODEC] Video: h264, Audio: opus
[CODEC] Compatibility: poor - Opus audio not supported on mobile
```

### Compatibility Levels

| Level | Video | Audio | Works On |
|-------|-------|-------|----------|
| Excellent | H.264 | AAC | Everything - mobile, PLEX, TV, web |
| Good | H.264 | MP3 | Most devices |
| Moderate | H.265 | AAC | Newer devices, some issues |
| Poor | Any | Opus | Computer only, fails on mobile |
| Very Poor | VP9/AV1 | Opus | Limited device support |

### Conversion Options

When a compatibility issue is detected, QuickTube offers:

1. **Convert Now** - Convert audio to AAC for mobile compatibility
2. **Skip** - Keep the file as-is (works on computer)
3. **Auto-Convert** - Enable in settings to always convert problematic files

### Settings

Click **⚙️ Settings** to configure:

- **Check Compatibility** - Scan downloads for codec issues (default: on)
- **Auto Convert** - Automatically convert incompatible files (default: off)
- **Prefer H.264** - Request H.264 codec from YouTube when available

### Batch Conversion

To convert existing files with compatibility issues:

```python
from codec_utils import batch_analyze, convert_for_compatibility
import os

# Analyze a folder
folder = "D:/stacher_downloads/Channel Name"
for file in os.listdir(folder):
    if file.endswith('.mp4'):
        path = os.path.join(folder, file)
        info = detect_codecs(path)
        if not info.is_mobile_compatible:
            output = path.replace('.mp4', '_converted.mp4')
            convert_for_compatibility(path, output)
```

### What Gets Converted

- **Audio only** (default): Opus → AAC (fast, preserves video quality)
- **Full conversion**: Also converts VP9/AV1 → H.264 (slower, for maximum compatibility)

Converted files are saved alongside originals with `_converted` suffix.

## Download History

Recent downloads appear at the bottom with:
- ✓ checkmark for completed downloads
- **📂 Open** button to view the file

## Buttons

- **🎬 Download Video** - Download single video
- **📺 Download Channel** - Download all videos from channel
- **📋 Paste URL** - Paste URL from clipboard
- **📁 Open Downloads Folder** - Open D:\stacher_downloads in Explorer
- **⚙️ Settings** - Configure quality and audio settings
- **❌ Close** - Close the application

## Progress Display

The progress display shows:
- `[START]` - Download beginning
- `[PROGRESS]` - Download percentage and speed
- `[SUCCESS]` - Download complete
- `[DONE]` - All downloads finished
- `[ERROR]` - If something went wrong

## File Organization

### Single Video
```
D:\stacher_downloads\
└── Video Title.mp4
```

### Channel Downloads
```
D:\stacher_downloads\
└── Channel Name\
    ├── Video 1.mp4
    ├── Video 2.mp4
    └── Video 3.mp4
```

## Integration with CCL

Add QuickTube to your Command Center LaunchPad:

```json
{
  "name": "QuickTube",
  "path": "D:\\QuickTube\\quicktube.py",
  "category": "Media",
  "monitor": 0
}
```

## Keyboard Shortcuts

- **Ctrl+V** - Paste URL from clipboard

## YouTube Authentication

YouTube requires authentication to bypass bot detection. QuickTube handles this automatically.

### How It Works

1. Stay logged into YouTube in **Firefox** (your normal browser)
2. QuickTube automatically reads Firefox cookies on startup
3. Downloads work without any manual steps

### Requirements

- Firefox browser installed
- Logged into YouTube in Firefox

### That's It

No Playwright. No manual cookie export. No complex setup. Just stay logged into YouTube in Firefox and QuickTube handles the rest.

### Manual Cookie Refresh (if needed)

If cookies expire, just run:
```powershell
cd D:\QuickTube
python export_firefox_cookies.py
```

## Troubleshooting

### "Sign in to confirm you're not a bot" Error
1. Open Firefox
2. Go to youtube.com
3. Make sure you're logged in (you should see your profile icon)
4. Restart QuickTube

### "Invalid URL" Error
- Make sure you copied the full YouTube URL
- URL must contain `youtube.com` or `youtu.be`

### Download Fails
- Check your internet connection
- Video might be private or age-restricted
- Try updating yt-dlp: `pip install --upgrade yt-dlp`

### Slow Downloads
- This is normal for large files
- Check the progress display for speed
- Quality setting affects file size (lower quality = faster)

### Channel Download Takes Forever
- Channels with many videos take time
- Each video downloads sequentially
- You can close QuickTube and downloads will stop (don't close mid-download)

## Advanced: Command Line

QuickTube uses `yt-dlp` behind the scenes. You can also use it directly:

```bash
# Download single video
yt-dlp -o "D:\stacher_downloads\%(title)s.%(ext)s" [URL]

# Download channel
yt-dlp -o "D:\stacher_downloads\%(uploader)s\%(title)s.%(ext)s" --yes-playlist [CHANNEL_URL]

# Audio only
yt-dlp -f bestaudio -x -o "D:\stacher_downloads\%(title)s.%(ext)s" [URL]
```

## Files

- `quicktube.py` - Main application
- `codec_utils.py` - Codec detection and conversion utilities
- `settings.json` - User settings
- `download_history.json` - Download history
- `README.md` - This file

## Requirements

### Core Dependencies
```powershell
pip install yt-dlp customtkinter pyperclip
```

### For Codec Detection & Conversion
- **FFmpeg** - Required for codec detection and conversion
  - Download: https://ffmpeg.org/download.html
  - Add `ffmpeg.exe` and `ffprobe.exe` to system PATH

## Support

For issues with:
- **QuickTube UI**: Check this README
- **yt-dlp downloads**: Visit https://github.com/yt-dlp/yt-dlp

---

**Built with CustomTkinter and yt-dlp** | **Theme matches CCL Launcher**
