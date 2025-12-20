"""
Codec Detection and Conversion Utilities

Provides video/audio codec detection using FFprobe and conversion using FFmpeg.
Identifies problematic codecs for mobile/PLEX compatibility and offers conversion options.

Compatible codecs (play everywhere):
- Video: H.264 (AVC)
- Audio: AAC, MP3

Problematic codecs (may not play on mobile/PLEX):
- Video: VP9, AV1, HEVC (H.265)
- Audio: Opus (especially in MP4 container)
"""

import subprocess
import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable, List
from enum import Enum


class VideoCodec(Enum):
    H264 = "h264"
    H265 = "hevc"
    VP9 = "vp9"
    AV1 = "av1"
    UNKNOWN = "unknown"


class AudioCodec(Enum):
    AAC = "aac"
    MP3 = "mp3"
    OPUS = "opus"
    FLAC = "flac"
    AC3 = "ac3"
    VORBIS = "vorbis"
    UNKNOWN = "unknown"


class CompatibilityLevel(Enum):
    EXCELLENT = "excellent"  # H.264 + AAC - plays everywhere
    GOOD = "good"            # H.264 + MP3 or similar
    MODERATE = "moderate"    # H.265/HEVC - some devices support
    POOR = "poor"            # VP9, Opus in MP4 - limited support
    VERY_POOR = "very_poor"  # AV1 - very limited support


@dataclass
class MediaInfo:
    """Complete media file information"""
    file_path: str
    file_size: int = 0
    duration: float = 0.0

    # Video info
    video_codec: VideoCodec = VideoCodec.UNKNOWN
    video_codec_raw: str = ""
    video_profile: str = ""
    width: int = 0
    height: int = 0
    frame_rate: float = 0.0
    video_bitrate: int = 0

    # Audio info
    audio_codec: AudioCodec = AudioCodec.UNKNOWN
    audio_codec_raw: str = ""
    sample_rate: int = 0
    channels: int = 0
    audio_bitrate: int = 0

    # Container info
    container_format: str = ""

    # Compatibility
    compatibility: CompatibilityLevel = CompatibilityLevel.EXCELLENT
    compatibility_issues: List[str] = field(default_factory=list)

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "Unknown"

    @property
    def fps_display(self) -> str:
        if self.frame_rate:
            return f"{self.frame_rate:.2f} fps"
        return "Unknown"

    @property
    def needs_conversion(self) -> bool:
        """Returns True if file has problematic codecs"""
        return self.compatibility in [CompatibilityLevel.POOR, CompatibilityLevel.VERY_POOR]

    @property
    def video_needs_conversion(self) -> bool:
        """Returns True if video codec is problematic"""
        return self.video_codec in [VideoCodec.VP9, VideoCodec.AV1]

    @property
    def audio_needs_conversion(self) -> bool:
        """Returns True if audio codec is problematic (Opus in MP4)"""
        return self.audio_codec == AudioCodec.OPUS


def get_ffprobe_path() -> str:
    """Find ffprobe executable"""
    # Check if in PATH
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe

    # Common locations on Windows
    common_paths = [
        r"C:\ProgramData\chocolatey\bin\ffprobe.exe",
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path

    raise FileNotFoundError("ffprobe not found. Please install FFmpeg.")


def get_ffmpeg_path() -> str:
    """Find ffmpeg executable"""
    # Check if in PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    # Common locations on Windows
    common_paths = [
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path

    raise FileNotFoundError("ffmpeg not found. Please install FFmpeg.")


def detect_codecs(file_path: str) -> MediaInfo:
    """
    Detect video and audio codecs using FFprobe.
    Returns MediaInfo with codec details and compatibility assessment.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ffprobe = get_ffprobe_path()

    # Run ffprobe to get stream info in JSON format
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFprobe timed out analyzing: {file_path}")
    except json.JSONDecodeError:
        raise RuntimeError(f"Failed to parse FFprobe output for: {file_path}")

    info = MediaInfo(file_path=file_path)

    # File size
    info.file_size = os.path.getsize(file_path)

    # Parse format info
    if "format" in data:
        fmt = data["format"]
        info.duration = float(fmt.get("duration", 0))
        info.container_format = fmt.get("format_name", "")

    # Parse streams
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type", "")
        codec_name = stream.get("codec_name", "").lower()

        if codec_type == "video":
            info.video_codec_raw = codec_name
            info.video_profile = stream.get("profile", "")
            info.width = int(stream.get("width", 0))
            info.height = int(stream.get("height", 0))
            info.video_bitrate = int(stream.get("bit_rate", 0))

            # Parse frame rate
            fps_str = stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                if int(den) > 0:
                    info.frame_rate = int(num) / int(den)

            # Map codec name to enum
            if codec_name in ["h264", "avc", "avc1"]:
                info.video_codec = VideoCodec.H264
            elif codec_name in ["hevc", "h265", "hev1"]:
                info.video_codec = VideoCodec.H265
            elif codec_name == "vp9":
                info.video_codec = VideoCodec.VP9
            elif codec_name == "av1":
                info.video_codec = VideoCodec.AV1
            else:
                info.video_codec = VideoCodec.UNKNOWN

        elif codec_type == "audio":
            info.audio_codec_raw = codec_name
            info.sample_rate = int(stream.get("sample_rate", 0))
            info.channels = int(stream.get("channels", 0))
            info.audio_bitrate = int(stream.get("bit_rate", 0))

            # Map codec name to enum
            if codec_name == "aac":
                info.audio_codec = AudioCodec.AAC
            elif codec_name == "mp3":
                info.audio_codec = AudioCodec.MP3
            elif codec_name == "opus":
                info.audio_codec = AudioCodec.OPUS
            elif codec_name == "flac":
                info.audio_codec = AudioCodec.FLAC
            elif codec_name in ["ac3", "eac3"]:
                info.audio_codec = AudioCodec.AC3
            elif codec_name == "vorbis":
                info.audio_codec = AudioCodec.VORBIS
            else:
                info.audio_codec = AudioCodec.UNKNOWN

    # Assess compatibility
    _assess_compatibility(info)

    return info


def _assess_compatibility(info: MediaInfo) -> None:
    """Assess codec compatibility for mobile/PLEX playback"""
    issues = []
    worst_level = CompatibilityLevel.EXCELLENT

    # Check video codec
    if info.video_codec == VideoCodec.AV1:
        issues.append("AV1 video: Very limited device support, will not play on most mobiles/TVs")
        worst_level = CompatibilityLevel.VERY_POOR
    elif info.video_codec == VideoCodec.VP9:
        issues.append("VP9 video: Limited hardware decoding on mobile devices")
        if worst_level.value not in ["very_poor"]:
            worst_level = CompatibilityLevel.POOR
    elif info.video_codec == VideoCodec.H265:
        issues.append("HEVC/H.265 video: Some older devices may not support")
        if worst_level.value in ["excellent", "good"]:
            worst_level = CompatibilityLevel.MODERATE

    # Check audio codec
    if info.audio_codec == AudioCodec.OPUS:
        # Opus in MP4 is particularly problematic
        if "mp4" in info.container_format.lower() or "mov" in info.container_format.lower():
            issues.append("Opus audio in MP4: Not supported on most mobile devices")
            if worst_level.value in ["excellent", "good", "moderate"]:
                worst_level = CompatibilityLevel.POOR
        else:
            issues.append("Opus audio: May have compatibility issues")
            if worst_level.value in ["excellent", "good"]:
                worst_level = CompatibilityLevel.MODERATE
    elif info.audio_codec == AudioCodec.VORBIS:
        issues.append("Vorbis audio: Limited support outside WebM")
        if worst_level.value in ["excellent", "good"]:
            worst_level = CompatibilityLevel.MODERATE
    elif info.audio_codec == AudioCodec.FLAC:
        issues.append("FLAC audio: Not all devices support in video containers")
        if worst_level.value == "excellent":
            worst_level = CompatibilityLevel.GOOD

    # Set results
    info.compatibility = worst_level
    info.compatibility_issues = issues


@dataclass
class ConversionProgress:
    """Track conversion progress"""
    percent: float = 0.0
    current_time: float = 0.0
    total_duration: float = 0.0
    speed: str = ""
    status: str = "pending"  # pending, running, completed, failed
    error_message: str = ""


def convert_for_compatibility(
    input_path: str,
    output_path: str,
    convert_video: bool = False,
    convert_audio: bool = True,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    video_crf: int = 23,
    progress_callback: Optional[Callable[[ConversionProgress], None]] = None
) -> bool:
    """
    Convert video file for maximum compatibility.

    Args:
        input_path: Source video file
        output_path: Destination file path
        convert_video: If True, re-encode video (slower but fixes VP9/AV1)
        convert_audio: If True, convert audio to AAC
        video_codec: Video codec to use (libx264 recommended)
        audio_codec: Audio codec to use (aac recommended)
        audio_bitrate: Audio bitrate (192k default)
        video_crf: Video quality (18-28, lower = better, 23 = default)
        progress_callback: Optional callback for progress updates

    Returns:
        True if successful, False otherwise
    """
    ffmpeg = get_ffmpeg_path()

    # Get duration for progress tracking
    try:
        info = detect_codecs(input_path)
        duration = info.duration
    except:
        duration = 0

    # Build FFmpeg command
    cmd = [ffmpeg, "-y", "-i", input_path]

    # Video settings
    if convert_video:
        cmd.extend(["-c:v", video_codec, "-crf", str(video_crf), "-preset", "medium"])
    else:
        cmd.extend(["-c:v", "copy"])  # Copy video stream (fast, no quality loss)

    # Audio settings
    if convert_audio:
        cmd.extend(["-c:a", audio_codec, "-b:a", audio_bitrate])
    else:
        cmd.extend(["-c:a", "copy"])

    # Output settings
    cmd.extend(["-movflags", "+faststart", output_path])

    progress = ConversionProgress(total_duration=duration, status="running")

    try:
        # Run FFmpeg with progress output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace'
        )

        # Parse output for progress
        for line in process.stdout:
            if "time=" in line:
                # Parse time=HH:MM:SS.ms
                try:
                    time_part = line.split("time=")[1].split()[0]
                    parts = time_part.split(":")
                    current_time = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    progress.current_time = current_time
                    if duration > 0:
                        progress.percent = min(100, (current_time / duration) * 100)

                    # Parse speed
                    if "speed=" in line:
                        progress.speed = line.split("speed=")[1].split()[0]

                    if progress_callback:
                        progress_callback(progress)
                except:
                    pass

        process.wait()

        if process.returncode == 0:
            progress.status = "completed"
            progress.percent = 100
            if progress_callback:
                progress_callback(progress)
            return True
        else:
            progress.status = "failed"
            progress.error_message = f"FFmpeg exited with code {process.returncode}"
            if progress_callback:
                progress_callback(progress)
            return False

    except Exception as e:
        progress.status = "failed"
        progress.error_message = str(e)
        if progress_callback:
            progress_callback(progress)
        return False


def convert_for_compatibility_async(
    input_path: str,
    output_path: str,
    convert_video: bool = False,
    convert_audio: bool = True,
    progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    completion_callback: Optional[Callable[[bool], None]] = None
) -> threading.Thread:
    """
    Async version of convert_for_compatibility.
    Returns the thread handle for monitoring.
    """
    def run():
        success = convert_for_compatibility(
            input_path=input_path,
            output_path=output_path,
            convert_video=convert_video,
            convert_audio=convert_audio,
            progress_callback=progress_callback
        )
        if completion_callback:
            completion_callback(success)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def batch_analyze(folder_path: str, extensions: List[str] = None) -> List[MediaInfo]:
    """
    Analyze all video files in a folder.

    Args:
        folder_path: Directory to scan
        extensions: File extensions to include (default: common video formats)

    Returns:
        List of MediaInfo objects for each file
    """
    if extensions is None:
        extensions = [".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"]

    results = []

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in extensions:
                file_path = os.path.join(root, file)
                try:
                    info = detect_codecs(file_path)
                    results.append(info)
                except Exception as e:
                    print(f"Error analyzing {file}: {e}")

    return results


def get_compatibility_summary(media_list: List[MediaInfo]) -> dict:
    """
    Generate a summary of codec compatibility for a list of files.

    Returns:
        Dict with counts by compatibility level and codec type
    """
    summary = {
        "total": len(media_list),
        "by_compatibility": {level.value: 0 for level in CompatibilityLevel},
        "by_video_codec": {},
        "by_audio_codec": {},
        "needs_conversion": 0,
        "files_needing_conversion": []
    }

    for info in media_list:
        summary["by_compatibility"][info.compatibility.value] += 1

        vc = info.video_codec.value
        ac = info.audio_codec.value
        summary["by_video_codec"][vc] = summary["by_video_codec"].get(vc, 0) + 1
        summary["by_audio_codec"][ac] = summary["by_audio_codec"].get(ac, 0) + 1

        if info.needs_conversion:
            summary["needs_conversion"] += 1
            summary["files_needing_conversion"].append(info.file_path)

    return summary


# Convenience function for quick compatibility check
def is_mobile_compatible(file_path: str) -> tuple[bool, List[str]]:
    """
    Quick check if a file will play on mobile devices.

    Returns:
        (is_compatible: bool, issues: List[str])
    """
    try:
        info = detect_codecs(file_path)
        return (not info.needs_conversion, info.compatibility_issues)
    except Exception as e:
        return (False, [f"Error analyzing file: {e}"])
