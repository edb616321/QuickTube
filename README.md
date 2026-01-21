# QuickTube - Simple YouTube Downloader

## Overview

QuickTube is a simple, clean YouTube downloader with a GUI interface. Just paste a URL and click download - that's it!

## Features

### Core Features
- **Simple Interface** - Paste URL, click download, done
- **Single Video or Channel** - Download one video or entire channels
- **Real-time Progress** - Watch downloads happen live
- **Download History** - Track what you've downloaded
- **Quality Settings** - Choose video quality (best, 1080p, 720p, 480p)
- **Audio Only Option** - Download as MP3
- **Clean UI** - Matches CCL launcher theme

### Search Tab (New in 2026-01)
- **YouTube Search** - Search videos without leaving the app
- **Video Preview Panel** - See thumbnail, title, duration before downloading
- **30-Second Preview Clips** - Preview videos with embedded VLC player
- **Quick Links** - Open video/channel in browser directly
- **Batch Selection** - Select multiple videos to download at once
- **Open Folder Button** - Quick access to downloads folder in tab bar

### Visual Analysis Tab (New in 2026-01-21)
- **AI-Powered Physical Comedy Detection** - Detect falls, slaps, chases, slapstick
- **Scene-Based Analysis** - PySceneDetect + perceptual hash deduplication
- **CLIP Model (Current)** - Semantic matching (limited accuracy for specific actions)
- **Future: Qwen2.5-VL-7B** - Recommended upgrade for true action understanding
- **Multi-Select Action Filters** - Choose categories: Slapstick, Falls, Fighting, Chases, etc.
- **Configurable Thresholds** - Min clip length, min confidence, max duration
- **Download Detected Clips** - Save clips directly to `visual_clips` folder
- **Re-Analyze Support** - Previously analyzed videos can be re-processed with new filters

### Codec Compatibility (Added 2025-12)
- **Automatic Codec Detection** - Scans downloads using FFprobe
- **Compatibility Warnings** - Alerts for problematic files (Opus audio, VP9/AV1 video)
- **One-Click Conversion** - Convert incompatible files to H.264 + AAC
- **Mobile/PLEX Friendly** - Ensures videos work on all devices

## Installation

### Required

```bash
pip install yt-dlp customtkinter pyperclip pillow requests python-vlc
```

### External Requirements
- **FFmpeg** - For codec detection and conversion
- **VLC Media Player** - For embedded video preview playback

### Download Folder

All videos save to: `D:\stacher_downloads`

## Usage

### Launch QuickTube

```bash
cd D:\QuickTube
python quicktube.py
```

### Download Tab - Single Video

1. Copy YouTube video URL
2. Click **Paste URL** (or Ctrl+V)
3. Click **Download Video**
4. Watch progress in real-time
5. Done! File is in `D:\stacher_downloads`

### Download Tab - Entire Channel

1. Copy YouTube channel URL
2. Click **Paste URL**
3. Click **Download Channel**
4. Confirm you want to download all videos
5. Videos download one by one
6. All videos save to `D:\stacher_downloads\[Channel Name]\`

### Search Tab

1. Enter search terms in the search box
2. Click **Search** or press Enter
3. Browse results with thumbnails on the left
4. Click **Preview** on any result to see details in the preview panel
5. Click **Play 30s Preview** to watch a clip embedded in the app
6. Check boxes to select videos for download
7. Click **Download Selected** to download all checked videos

## Supported URLs

- Single videos: `https://youtube.com/watch?v=...`
- Short links: `https://youtu.be/...`
- Channels: `https://youtube.com/@channelname`
- Playlists: `https://youtube.com/playlist?list=...`

## Settings

Click **Settings** to configure:

### Video Quality
- **Best** (default) - Highest quality available
- **1080p** - Full HD
- **720p** - HD
- **480p** - SD

### Audio Only
- Check this to download MP3 audio only (no video)

### Codec Options
- **Check Compatibility** - Scan downloads for codec issues (default: on)
- **Auto Convert** - Automatically convert incompatible files (default: off)
- **Prefer H.264** - Request H.264 codec from YouTube when available

## Codec Detection & Compatibility

QuickTube automatically checks downloaded videos for compatibility issues with mobile devices and media servers like PLEX.

### The Problem

YouTube sometimes encodes videos with codecs that don't work well on all devices:
- **Opus audio in MP4** - Won't play on many mobile devices or PLEX mobile apps
- **VP9 video** - Limited support on older devices
- **AV1 video** - Cutting-edge codec with limited device support

Videos may play fine on your computer but fail on phones, tablets, or streaming servers.

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

## Visual Analysis - How It Works

The Visual Analysis tab uses AI to detect physical comedy moments in videos with automatic scene detection and duplicate removal.

### Workflow (Single Video - Scene-Based Analysis)
1. **Search** - Enter a search query (e.g., "benny hill slapstick") or browse local files
2. **Select ONE Video** - Check a single video to analyze with full progress tracking
3. **Set Confidence** - Set minimum confidence threshold (default 15%)
4. **Analyze** - Click "Analyze Selected Videos" to start 6-step process:
   - Step 1: Download video
   - Step 2: Detect scene boundaries (PySceneDetect)
   - Step 3: Extract thumbnails from each scene
   - Step 4: Remove duplicate scenes (perceptual hash deduplication)
   - Step 5: Classify scenes with CLIP AI
   - Step 6: Build clip candidates
5. **Preview** - View thumbnail grid with scene info, click "Preview" to watch clips
6. **Select & Download** - Check clips to keep, click "Download Selected Clips"

### Progress Indicators
- Visual step indicators (1-6) showing completed/current/pending steps
- Progress bar showing overall completion
- Spinner animation during processing
- Real-time status messages

### Multi-Video Batch Analysis
When multiple videos are selected, uses the original batch processing mode without scene-based deduplication.

### Detection Models

| Model | Best For | How It Works | Accuracy |
|-------|----------|--------------|----------|
| **CLIP** (Current) | Visual similarity filtering | Matches frames to text descriptions | ~29% on slapstick |
| SlowFast | Sports, defined movements | Kinetics-400 action classes | 0.27% on slapstick |
| **Qwen2.5-VL-7B** (Planned) | True action understanding | Temporal video reasoning | High (recommended) |

**Note:** CLIP cannot reliably detect specific actions like "slaps" - see limitations section below.

### CLIP Detection Categories (17 prompts)
- **Slapstick**: "slapstick comedy scene", "person slapping another person", "comedic fighting"
- **Falls**: "person falling down", "someone tripping", "pratfall"
- **Chases**: "people running and chasing", "comedy chase scene", "fast motion"
- **Physical Humor**: "pie in face", "being pushed", "knocked over", "silly movements"
- **Excluded**: "dialogue", "scenery", "credits" (auto-filtered)

### Requirements for Visual Analysis
```bash
# Separate conda environment required
conda create -n video_analysis python=3.10
conda activate video_analysis
pip install torch torchvision pytorchvideo pillow numpy imagehash
pip install git+https://github.com/openai/CLIP.git
pip install scenedetect[opencv]
```

## Visual Analysis - Limitations & Future Improvements

### Current CLIP Model Limitations

After extensive testing with Benny Hill slapstick videos, we discovered fundamental limitations with the CLIP-based approach:

**The Problem:**
- CLIP matches **visual aesthetics**, not **temporal actions**
- A single frame of a "slap" doesn't look distinctly like a slap
- CLIP sees "two people close together" rather than "someone slapping someone"
- 29% accuracy is insufficient for reliable action detection
- Many false positives from visually similar but non-action scenes

**Why CLIP Fails for Action Detection:**
- CLIP was trained on image-caption pairs, not video action sequences
- Physical actions like slaps, falls, and chases require **temporal context** (before/during/after)
- A mid-slap frame looks similar to someone waving or gesturing

### Research: Alternative Approaches (2026-01-21)

We researched several alternatives for improved action detection. Hardware available: **Dual RTX 4090 server** with vLLM/Ollama, plus API accounts (Anthropic, Google, OpenAI).

#### Option 1: Qwen2.5-VL-7B (STRONGLY RECOMMENDED)

**Why This Is The Preferred Option:**
- True video understanding with temporal reasoning
- Can process multiple frames and understand actions
- Natural language queries: "Find all scenes where someone gets slapped"
- Returns timestamps and descriptions
- Runs locally on 4090 (14-18GB VRAM)

**Specifications:**
| Property | Value |
|----------|-------|
| Model Size | 7B parameters |
| VRAM Required | 14-18GB (fits single 4090) |
| Framework | vLLM, Ollama, or transformers |
| Input | Video frames + text prompt |
| Output | Descriptions with timestamps |

**Implementation Approach:**
```python
# Example workflow
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

model = Qwen2VLForConditionalGeneration.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct")

# Process video in chunks
prompt = "Identify all scenes containing: slaps, falls, chases, physical comedy. Return timestamps."
result = model.generate(video_frames, prompt)
# Returns: "0:42-0:45: Man slaps another man on the back of the head"
```

**Advantages:**
- Runs entirely locally (no API costs)
- True temporal understanding
- Can be fine-tuned on slapstick examples
- Supports natural language queries
- High accuracy on action recognition benchmarks

#### Option 2: Gemini 2.5 Pro API

**Best for highest accuracy without local GPU:**
- Native video+audio processing
- Can hear slap sounds AND see actions
- Returns timestamps
- User already has Gemini account

| Property | Value |
|----------|-------|
| Input | Full video file (up to 2 hours) |
| Audio Analysis | Yes - detects slap sounds, screams |
| Timestamps | Yes - precise to seconds |
| Cost | ~$0.001/second of video |

**Advantages:**
- Highest accuracy (video + audio combined)
- No local GPU requirements
- Simple API integration

**Disadvantages:**
- Ongoing API costs
- Requires internet connection
- Data sent to Google servers

#### Option 3: Audio Detection (PANNs / Whisper-AT)

**For detecting actions by sound:**
- Slaps have distinct audio signatures
- Screams, crashes, running footsteps
- Can complement visual analysis

| Model | Purpose | Size |
|-------|---------|------|
| PANNs | Audio event detection | 80MB |
| Whisper-AT | Audio tagging + transcription | 1.5GB |

**Best Used:** As a secondary signal combined with visual analysis

#### Option 4: MMAction2 (Specialized Action Detection)

**For fine-grained temporal action localization:**
- SlowFast, TimeSformer, VideoMAE models
- Requires training on slapstick dataset
- More complex setup

**Best Used:** If building a specialized slapstick detector with labeled training data

### Recommended Upgrade Path

1. **Phase 1 (Immediate):** Keep current CLIP system for basic filtering
2. **Phase 2 (Next):** Implement Qwen2.5-VL-7B for accurate action detection
3. **Phase 3 (Optional):** Add audio detection for slap sounds as secondary signal
4. **Phase 4 (Optional):** Fine-tune on labeled slapstick clips for highest accuracy

### Hardware Requirements for Qwen2.5-VL-7B

```
Minimum:
- RTX 4090 (24GB) or RTX 3090 (24GB)
- 32GB system RAM
- 50GB disk space for model

Recommended (Current Server):
- Dual RTX 4090 (48GB total)
- vLLM for optimized inference
- Can process multiple videos in parallel
```

## Recent Updates

### 2026-01-21 - Research: Action Detection Alternatives
- **CLIP Limitations Documented** - CLIP cannot reliably detect temporal actions (slaps, falls)
- **Research Completed** - Evaluated Qwen2.5-VL-7B, Gemini API, MMAction2, audio detection
- **Qwen2.5-VL-7B Recommended** - True video understanding with temporal reasoning
- **Hardware Ready** - Dual RTX 4090 server available for local inference
- **Upgrade Path Defined** - Phased approach from CLIP to Qwen2.5-VL-7B

### 2026-01-21 - Scene-Based Analysis with Deduplication
- **Scene Detection** - Uses PySceneDetect to find natural scene boundaries (not frame-by-frame)
- **Perceptual Hash Deduplication** - Removes duplicate/similar scenes automatically using imagehash
- **6-Step Progress UI** - Visual step indicators, progress bar, and spinner animations
- **Thumbnail Preview Grid** - See scene thumbnails before downloading
- **Preview Clips** - Click to preview any scene with ffplay before saving
- **User Selection** - Check/uncheck scenes to include in download
- **CLIP Model** - Basic slapstick filtering (29% accuracy - limited for specific actions)
- **Download Selected** - Save only the scenes you want to `visual_clips` folder

### 2026-01-20 - Visual Analysis Tab Added
- New tab for AI-powered physical comedy detection
- Multi-select action category filters
- Max results and max duration search filters
- Min confidence threshold filtering
- Download detected clips feature

### 2026-01-09 - Embedded Video Preview
- Added embedded VLC player for preview clips
- Preview plays inside the app instead of launching external player
- 30-second clips download via yt-dlp `--download-sections`

### 2026-01-09 - Search Tab UI Enhancements
- Added **Open Folder** button to tab bar (always visible)
- Added **Video/Channel/Preview** link buttons under each search result
- Added preview panel on right side with thumbnail, title, and action buttons
- Two-column layout: search results (left) + preview panel (right)

### 2026-01-09 - Wrong Video Bug Fix
- Fixed issue where cached videos caused wrong file to be downloaded
- Added parsing for "has already been downloaded" yt-dlp messages
- Improved fallback logic to sort temp files by modification time
- Added auto-cleanup of temp files older than 24 hours

### 2025-12-20 - Codec Compatibility
- Added FFprobe-based codec detection
- Compatibility warnings for Opus audio in MP4
- Batch conversion tool for problematic files

### 2025-11-05 - Progress Display Fixes
- Fixed progress tracking with temp folder architecture
- Thread-safe UI updates
- Clean output without ANSI codes
- Duplicate file handling dialog

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

## Files

```
D:\QuickTube\
├── quicktube.py           # Main application
├── scene_analysis.py      # Scene-based analysis (PySceneDetect + deduplication)
├── visual_analysis.py     # Visual analysis module (CLIP + SlowFast)
├── audio_detection.py     # Audio detection module
├── codec_utils.py         # Codec detection utilities
├── settings.json          # User preferences
├── download_history.json  # Download history
├── processed_videos.json  # Visual analysis cache
├── temp/                  # Temporary download/frame folder
│   └── scene_cache/       # Downloaded videos and thumbnails for analysis
├── logs/                  # Application logs
├── README.md              # This file
└── FIXES.md               # Bug fix documentation
```

## Troubleshooting

### Preview Not Playing in App
- Ensure VLC Media Player is installed
- Check that python-vlc package is installed: `pip install python-vlc`
- Check logs in `D:\QuickTube\logs\` for errors
- Falls back to external player if embedded fails

### Wrong Video Downloaded
- This was fixed in 2026-01-09 update
- Temp folder is now auto-cleaned every 24 hours
- If issue persists, manually clear `D:\QuickTube\temp\`

### "Sign in to confirm you're not a bot" Error
1. Open Firefox
2. Go to youtube.com
3. Make sure you're logged in (you should see your profile icon)
4. Restart QuickTube

### Open Folder Not Working
- Ensure download folder exists
- App will create folder if missing
- Falls back to subprocess if os.startfile fails

### Download Fails
- Check your internet connection
- Video might be private or age-restricted
- Try updating yt-dlp: `pip install --upgrade yt-dlp`

### Codec Compatibility Issues
- Files with Opus audio may not play on mobile/PLEX
- Use the conversion feature to convert to AAC audio
- Check `D:\stacher_downloads\*_Converted\` for converted files

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
- **Enter** - Submit search (in search tab)

## YouTube Authentication

YouTube requires authentication to bypass bot detection. QuickTube handles this automatically.

### How It Works

1. Stay logged into YouTube in **Firefox** (your normal browser)
2. QuickTube automatically reads Firefox cookies on startup
3. Downloads work without any manual steps

### Requirements

- Firefox browser installed
- Logged into YouTube in Firefox

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

## Support

For issues with:
- **QuickTube UI**: Check this README and FIXES.md
- **yt-dlp downloads**: Visit https://github.com/yt-dlp/yt-dlp

---

**Built with CustomTkinter and yt-dlp** | **Theme matches CCL Launcher**
