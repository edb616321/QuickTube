"""
Visual Analysis Module for QuickTube
Detects physical comedy actions (falls, faceplants, slaps, etc.) in videos
using PyTorchVideo's SlowFast model pre-trained on Kinetics-400/700.

Requires: conda activate video_analysis
"""

import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import hashlib

# Paths
QUICKTUBE_DIR = Path(r"D:\QuickTube")
PROCESSED_DB_PATH = QUICKTUBE_DIR / "processed_videos.json"
TEMP_FOLDER = QUICKTUBE_DIR / "temp"
FRAMES_FOLDER = TEMP_FOLDER / "frames"
CONDA_ENV = "video_analysis"

# Kinetics-400 action classes relevant to physical comedy
# COMPREHENSIVE LIST - 85 classes covering falls, slides, trips, impacts, stunts
# Full list: https://gist.github.com/willprice/f19da185c9c5f32847134b87c1960769
PHYSICAL_COMEDY_CLASSES = {
    # === COMBAT/FIGHTING (High priority for slapstick) ===
    6: "arm wrestling",
    150: "headbutting",
    152: "high kick",
    258: "punching bag",
    259: "punching person (boxing)",
    302: "side kick",
    314: "slapping",
    345: "sword fighting",
    396: "wrestling",
    # === FALLS AND STUNTS ===
    122: "faceplanting",
    147: "gymnastics tumbling",
    207: "parkour",
    325: "somersaulting",
    365: "trapezing",
    45: "cartwheeling",
    43: "capoeira",
    34: "breakdancing",
    179: "krumping",
    277: "robot dancing",
    # === SLIDING/SKATING (trips and falls) ===
    28: "bobsledding",
    164: "ice skating",
    280: "roller skating",
    306: "skateboarding",
    308: "skiing (not slalom or crosscountry)",
    309: "skiing crosscountry",
    310: "skiing slalom",
    313: "slacklining",
    322: "snowboarding",
    323: "snowkiting",
    337: "surfing water",
    361: "tobogganing",
    384: "water skiing",
    385: "water sliding",
    # === KICKS (sports) ===
    105: "drop kicking",
    174: "kicking field goal",
    175: "kicking soccer ball",
    237: "playing kickball",
    # === SPORTS WITH IMPACTS ===
    94: "dodgeball",
    153: "hitting baseball",
    48: "catching or throwing baseball",
    235: "playing ice hockey",
    154: "hockey stop",
    240: "playing paintball",
    251: "playing volleyball",
    297: "shooting goal (soccer)",
    # === JUMPING ===
    40: "bungee jumping",
    151: "high jump",
    172: "jumping into pool",
    173: "jumpstyle dancing",
    182: "long jump",
    307: "ski jumping",
    368: "triple jump",
    30: "bouncing on trampoline",
    160: "hurdling",
    253: "pole vault",
    377: "vault",
    # === DIVING ===
    93: "diving cliff",
    312: "skydiving",
    329: "springboard diving",
    286: "scuba diving",
    205: "paragliding",
    206: "parasailing",
    # === RISKY VEHICLES/RIDING ===
    157: "hoverboarding",
    167: "jetskiing",
    177: "kitesurfing",
    199: "motorcycling",
    267: "riding a bike",
    270: "riding mechanical bull",
    271: "riding mountain bike",
    274: "riding scooter",
    275: "riding unicycle",
    315: "sled dog racing",
    324: "snowmobiling",
    376: "using segway",
    394: "windsurfing",
    # === CLIMBING (potential falls) ===
    66: "climbing a rope",
    67: "climbing ladder",
    68: "climbing tree",
    162: "ice climbing",
    278: "rock climbing",
    # === THROWING ===
    148: "hammer throw",
    166: "javelin throw",
    298: "shot put",
    357: "throwing axe",
    358: "throwing ball",
    359: "throwing discus",
    49: "catching or throwing frisbee",
    # === BOUNCING/SWINGING ===
    344: "swinging on something",
    311: "skipping rope",
    55: "cheerleading",
    # === REACTIONS (secondary) ===
    149: "headbanging",
    180: "laughing",
    79: "crying",
    360: "tickling",
}


@dataclass
class DetectedAction:
    """Represents a detected action in a video"""
    timestamp: float           # Seconds into video
    timestamp_str: str         # "00:01:23" format
    action_class: str          # "faceplanting", "slapping", etc.
    confidence: float          # 0-1 confidence score
    class_id: int              # Kinetics class ID


@dataclass
class DetectedClip:
    """Represents a merged clip with start/end times"""
    start_time: float          # Clip start (seconds)
    end_time: float            # Clip end (seconds)
    start_str: str             # "00:01:23" format
    end_str: str               # "00:01:33" format
    duration: float            # Clip duration in seconds
    action_classes: List[str]  # Actions detected in this clip
    primary_action: str        # Most common/confident action
    confidence: float          # Max confidence in clip
    detection_count: int       # Number of raw detections merged


@dataclass
class VideoAnalysisResult:
    """Results from analyzing a video"""
    video_id: str
    video_url: str
    video_title: str
    duration_seconds: float
    analyzed_date: str
    total_detections: int
    detections: List[Dict]     # List of DetectedAction as dicts
    analysis_params: Dict


def merge_detections_into_clips(
    detections: List[DetectedAction],
    min_duration: float = 5.0,
    merge_gap: float = 3.0,
    padding: float = 2.0
) -> List[DetectedClip]:
    """
    Merge nearby detections into clips with minimum duration.

    Args:
        detections: List of raw detections
        min_duration: Minimum clip duration in seconds (default 5)
        merge_gap: Max gap between detections to merge (seconds)
        padding: Extra time to add before/after clip (seconds)

    Returns:
        List of merged clips meeting minimum duration
    """
    if not detections:
        return []

    # Sort by timestamp
    sorted_dets = sorted(detections, key=lambda x: x.timestamp)

    # Group nearby detections
    groups = []
    current_group = [sorted_dets[0]]

    for det in sorted_dets[1:]:
        # If this detection is within merge_gap of the last one, add to group
        if det.timestamp - current_group[-1].timestamp <= merge_gap:
            current_group.append(det)
        else:
            groups.append(current_group)
            current_group = [det]
    groups.append(current_group)

    # Convert groups to clips
    clips = []
    for group in groups:
        # Calculate clip boundaries with padding
        start_time = max(0, group[0].timestamp - padding)
        end_time = group[-1].timestamp + padding

        # Ensure minimum duration
        duration = end_time - start_time
        if duration < min_duration:
            # Extend equally on both sides
            extra = (min_duration - duration) / 2
            start_time = max(0, start_time - extra)
            end_time = end_time + extra
            duration = end_time - start_time

        # Get all action classes in this clip
        action_classes = [d.action_class for d in group]

        # Find primary action (most common or highest confidence)
        action_counts = {}
        action_confidence = {}
        for d in group:
            action_counts[d.action_class] = action_counts.get(d.action_class, 0) + 1
            if d.action_class not in action_confidence or d.confidence > action_confidence[d.action_class]:
                action_confidence[d.action_class] = d.confidence

        # Primary = highest count, tiebreak by confidence
        primary_action = max(action_counts.keys(),
                           key=lambda a: (action_counts[a], action_confidence[a]))

        # Max confidence in clip
        max_confidence = max(d.confidence for d in group)

        clip = DetectedClip(
            start_time=round(start_time, 1),
            end_time=round(end_time, 1),
            start_str=seconds_to_timestamp(start_time),
            end_str=seconds_to_timestamp(end_time),
            duration=round(duration, 1),
            action_classes=list(set(action_classes)),
            primary_action=primary_action,
            confidence=max_confidence,
            detection_count=len(group)
        )
        clips.append(clip)

    return clips


def filter_detections_by_keywords(
    detections: List[DetectedAction],
    keywords: List[str]
) -> List[DetectedAction]:
    """Filter detections to only include those matching keywords."""
    if not keywords:
        return detections

    # Normalize keywords to lowercase
    keywords = [k.lower().strip() for k in keywords if k.strip()]
    if not keywords:
        return detections

    filtered = []
    for det in detections:
        action_lower = det.action_class.lower()
        # Check if any keyword is contained in the action class
        for kw in keywords:
            if kw in action_lower or action_lower in kw:
                filtered.append(det)
                break

    return filtered


def get_video_hash(video_url: str) -> str:
    """Generate unique hash for a video URL"""
    return hashlib.md5(video_url.encode()).hexdigest()[:12]


def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def load_processed_database() -> Dict:
    """Load the processed videos database"""
    if PROCESSED_DB_PATH.exists():
        try:
            with open(PROCESSED_DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"videos": {}, "last_updated": None}


def save_processed_database(db: Dict):
    """Save the processed videos database"""
    db["last_updated"] = datetime.now().isoformat()
    with open(PROCESSED_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def is_video_processed(video_url: str) -> Tuple[bool, Optional[Dict]]:
    """Check if a video has already been processed"""
    db = load_processed_database()
    video_hash = get_video_hash(video_url)

    if video_hash in db["videos"]:
        return True, db["videos"][video_hash]
    return False, None


def save_video_result(result: VideoAnalysisResult):
    """Save analysis result to database"""
    db = load_processed_database()
    video_hash = get_video_hash(result.video_url)

    db["videos"][video_hash] = {
        "video_id": result.video_id,
        "video_url": result.video_url,
        "video_title": result.video_title,
        "duration_seconds": result.duration_seconds,
        "analyzed_date": result.analyzed_date,
        "total_detections": result.total_detections,
        "detections": result.detections,
        "analysis_params": result.analysis_params
    }

    save_processed_database(db)


def extract_video_id(video_url: str) -> str:
    """Extract YouTube video ID from URL"""
    if "v=" in video_url:
        return video_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        return video_url.split("youtu.be/")[1].split("?")[0]
    elif "shorts/" in video_url:
        return video_url.split("shorts/")[1].split("?")[0]
    return get_video_hash(video_url)


def download_video(video_url: str, output_path: str) -> bool:
    """Download video using yt-dlp with QuickTube's cookie authentication"""
    # Use QuickTube's cookie file for authentication
    cookies_file = QUICKTUBE_DIR / "temp" / "youtube_cookies.txt"

    # Format selection that avoids SABR streaming issues:
    # - Prefer mp4 with h264 video codec (most compatible, avoids HLS)
    # - Avoid premium/restricted formats
    # - Fall back to best available
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "-o", output_path,
        "--no-playlist",
        "--merge-output-format", "mp4",  # Ensure MP4 output
        "--no-warnings",
    ]

    # Add cookie authentication - prefer browser cookies for freshest session
    cmd.extend(["--cookies-from-browser", "firefox"])

    cmd.append(video_url)

    try:
        print(f"[VISUAL] Download command: {' '.join(cmd[:5])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"[VISUAL] yt-dlp failed with code {result.returncode}")
            if result.stderr:
                # Print first 500 chars of error
                print(f"[VISUAL] yt-dlp stderr: {result.stderr[:500]}")
            if result.stdout:
                print(f"[VISUAL] yt-dlp stdout: {result.stdout[:200]}")
        if os.path.exists(output_path):
            print(f"[VISUAL] Download success: {output_path}")
            return True
        else:
            print(f"[VISUAL] Output file not created: {output_path}")
            return False
    except Exception as e:
        print(f"[VISUAL] Download error: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_video_duration(video_path: str) -> float:
    """Get video duration using ffprobe"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except:
        return 0.0


def extract_frames(video_path: str, output_dir: str, fps: float = 2.0) -> List[str]:
    """Extract frames from video at specified FPS"""
    os.makedirs(output_dir, exist_ok=True)

    # Clear old frames
    for f in Path(output_dir).glob("*.jpg"):
        f.unlink()

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        os.path.join(output_dir, "frame_%06d.jpg")
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=300)
        frames = sorted(Path(output_dir).glob("*.jpg"))
        return [str(f) for f in frames]
    except:
        return []


# CLIP text prompts for physical comedy detection
# Maps descriptive prompts to action category names
CLIP_TEXT_PROMPTS_DICT = {
    # Slapstick comedy
    "a person slapping another person on the head": "head slapping",
    "someone hitting another person": "hitting",
    "a man slapping someone": "slapping",
    "people fighting in a comedic way": "comedic fighting",
    "slapstick comedy scene": "slapstick comedy",
    "funny physical comedy": "physical comedy",

    # Falls and trips
    "a person falling down": "falling",
    "someone tripping and falling": "tripping",
    "a person stumbling": "stumbling",
    "someone doing a pratfall": "pratfall",
    "a person faceplanting": "faceplant",

    # Chases
    "people running and chasing": "chase scene",
    "a comedy chase scene": "comedy chase",
    "people running in fast motion": "fast motion chase",

    # Physical humor
    "someone getting hit with a pie": "pie in face",
    "a person being pushed": "being pushed",
    "someone being knocked over": "knocked over",
    "a person doing silly movements": "silly movements",
    "exaggerated physical movements": "exaggerated movements",

    # Benny Hill specific
    "women in bikinis running": "bikini chase",
    "old man chasing women": "chase scene",
    "people in costumes running": "costume chase",
    "speeded up comedy footage": "fast motion",
}

# The actual inference code that runs in the conda environment (SlowFast)
INFERENCE_SCRIPT = '''
import sys
import json
import torch
import numpy as np
from PIL import Image
from torchvision import transforms
from pytorchvideo.models.hub import slowfast_r50

# Load model
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = slowfast_r50(pretrained=True)
model = model.to(device)
model.eval()

# Kinetics-400 class names (subset for physical comedy)
PHYSICAL_COMEDY_IDS = {json_classes}

# Load Kinetics-400 labels
KINETICS_LABELS = {kinetics_labels}

# Transform for frames
transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.45, 0.45, 0.45], std=[0.225, 0.225, 0.225]),
])

def load_frames(frame_paths, num_frames=32):
    """Load and preprocess frames for SlowFast"""
    frames = []
    indices = np.linspace(0, len(frame_paths) - 1, num_frames, dtype=int)

    for idx in indices:
        img = Image.open(frame_paths[idx]).convert("RGB")
        frames.append(transform(img))

    video = torch.stack(frames)  # T, C, H, W
    video = video.permute(1, 0, 2, 3)  # C, T, H, W

    # SlowFast needs [slow_pathway, fast_pathway]
    # Slow: 8 frames, Fast: 32 frames
    slow_idx = np.linspace(0, num_frames - 1, 8, dtype=int)
    fast_idx = np.arange(num_frames)

    slow = video[:, slow_idx, :, :]
    fast = video[:, fast_idx, :, :]

    return [slow.unsqueeze(0).to(device), fast.unsqueeze(0).to(device)]

# Read frame paths from file (stdin doesn't work well with conda run)
import sys
frame_paths_file = sys.argv[1] if len(sys.argv) > 1 else None
if frame_paths_file:
    with open(frame_paths_file, 'r') as f:
        frame_paths = json.load(f)
else:
    frame_paths = []

detections = []

# Process in sliding windows
window_size = 32
stride = 16
fps = {fps}

for i in range(0, max(1, len(frame_paths) - window_size + 1), stride):
    window_frames = frame_paths[i:i + window_size]
    if len(window_frames) < window_size:
        window_frames = frame_paths[-window_size:] if len(frame_paths) >= window_size else frame_paths

    if len(window_frames) < 8:
        continue

    try:
        inputs = load_frames(window_frames)

        with torch.no_grad():
            outputs = model(inputs)
            probs = torch.nn.functional.softmax(outputs, dim=1)

        # Check for physical comedy classes
        for class_id in PHYSICAL_COMEDY_IDS:
            if class_id < probs.shape[1]:
                conf = probs[0, class_id].item()
                if conf > {threshold}:
                    timestamp = (i + window_size // 2) / fps
                    detections.append({{
                        "timestamp": timestamp,
                        "class_id": class_id,
                        "class_name": KINETICS_LABELS.get(str(class_id), f"class_{{class_id}}"),
                        "confidence": conf
                    }})
    except Exception as e:
        pass

# Output results
print(json.dumps(detections))
'''


def run_inference(frame_paths: List[str], fps: float = 2.0, threshold: float = 0.1) -> List[DetectedAction]:
    """Run SlowFast inference on frames using conda environment"""

    # Build the inference script with parameters
    # Use the same class labels as PHYSICAL_COMEDY_CLASSES
    kinetics_labels = PHYSICAL_COMEDY_CLASSES.copy()

    script = INFERENCE_SCRIPT.format(
        json_classes=json.dumps(list(PHYSICAL_COMEDY_CLASSES.keys())),
        kinetics_labels=json.dumps(kinetics_labels),
        fps=fps,
        threshold=threshold
    )

    # Write script to temp file
    script_path = TEMP_FOLDER / "inference_script.py"
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    with open(script_path, 'w') as f:
        f.write(script)

    # Write frame paths to temp file (stdin doesn't work with conda run)
    frames_file = TEMP_FOLDER / "frame_paths.json"
    with open(frames_file, 'w') as f:
        json.dump(frame_paths, f)

    # Run in conda environment with frame paths file as argument
    cmd = f'conda run -n {CONDA_ENV} python "{script_path}" "{frames_file}"'

    try:
        print(f"[VISUAL] Running inference command: {cmd[:100]}...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            shell=True
        )

        print(f"[VISUAL] Inference return code: {result.returncode}")
        if result.stderr:
            print(f"[VISUAL] Inference stderr: {result.stderr[:500]}")
        if result.stdout:
            print(f"[VISUAL] Inference stdout length: {len(result.stdout)}")

        if result.returncode == 0 and result.stdout.strip():
            raw_detections = json.loads(result.stdout.strip())
            print(f"[VISUAL] Parsed {len(raw_detections)} raw detections")

            detections = []
            for d in raw_detections:
                detections.append(DetectedAction(
                    timestamp=d["timestamp"],
                    timestamp_str=seconds_to_timestamp(d["timestamp"]),
                    action_class=d["class_name"],
                    confidence=d["confidence"],
                    class_id=d["class_id"]
                ))

            return detections
    except Exception as e:
        print(f"[VISUAL] Inference error: {e}")

    return []


def run_clip_inference(frame_paths: List[str], fps: float = 2.0, threshold: float = 0.25) -> List[DetectedAction]:
    """Run CLIP inference on frames for semantic matching"""

    # Write the CLIP inference script directly (avoid string formatting issues)
    script_content = f'''import sys
import json
import torch
from PIL import Image

import clip

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

# Text prompts for physical comedy detection
TEXT_PROMPTS = {json.dumps(CLIP_TEXT_PROMPTS_DICT)}

# Encode text prompts once
text_tokens = clip.tokenize(list(TEXT_PROMPTS.keys())).to(device)
with torch.no_grad():
    text_features = model.encode_text(text_tokens)
    text_features = text_features / text_features.norm(dim=-1, keepdim=True)

# Read frame paths
with open(sys.argv[1], 'r') as f:
    frame_paths = json.load(f)

detections = []
fps = {fps}
threshold = {threshold}
prompt_names = list(TEXT_PROMPTS.keys())
prompt_categories = list(TEXT_PROMPTS.values())

# Process frames in batches
batch_size = 16
for i in range(0, len(frame_paths), batch_size):
    batch_paths = frame_paths[i:i+batch_size]
    images = []
    valid_paths = []

    for path in batch_paths:
        try:
            img = Image.open(path).convert("RGB")
            images.append(preprocess(img))
            valid_paths.append(path)
        except:
            continue

    if not images:
        continue

    # Encode images
    image_tensors = torch.stack(images).to(device)
    with torch.no_grad():
        image_features = model.encode_image(image_tensors)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

    # Compute similarity scores
    similarities = (image_features @ text_features.T).cpu().numpy()

    for j, (path, sims) in enumerate(zip(valid_paths, similarities)):
        # Calculate frame index from path (frame_000001.jpg -> 0)
        frame_idx = i + j
        timestamp = frame_idx / fps

        # Check each prompt - find the best matching one above threshold
        best_score = 0
        best_category = None
        best_prompt = None
        best_idx = -1

        for k, (prompt, category) in enumerate(zip(prompt_names, prompt_categories)):
            score = float(sims[k])
            if score > threshold and score > best_score:
                best_score = score
                best_category = category
                best_prompt = prompt
                best_idx = k

        if best_category:
            detections.append({{
                "timestamp": timestamp,
                "class_id": best_idx,
                "class_name": best_category,
                "confidence": best_score,
                "prompt": best_prompt
            }})

print(json.dumps(detections))
'''

    # Write script to temp file
    script_path = TEMP_FOLDER / "clip_inference_script.py"
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    with open(script_path, 'w') as f:
        f.write(script_content)

    # Write frame paths to temp file
    frames_file = TEMP_FOLDER / "frame_paths.json"
    with open(frames_file, 'w') as f:
        json.dump(frame_paths, f)

    # Run in conda environment
    cmd = f'conda run -n {CONDA_ENV} python "{script_path}" "{frames_file}"'

    try:
        print(f"[VISUAL] Running CLIP inference...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            shell=True
        )

        print(f"[VISUAL] CLIP return code: {result.returncode}")
        if result.stderr:
            print(f"[VISUAL] CLIP stderr: {result.stderr[:500]}")

        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            # Find the JSON output (last line)
            for line in reversed(output.split('\n')):
                if line.strip().startswith('['):
                    raw_detections = json.loads(line.strip())
                    break
            else:
                raw_detections = json.loads(output)

            print(f"[VISUAL] CLIP found {len(raw_detections)} detections")

            detections = []
            for d in raw_detections:
                detections.append(DetectedAction(
                    timestamp=d["timestamp"],
                    timestamp_str=seconds_to_timestamp(d["timestamp"]),
                    action_class=d["class_name"],
                    confidence=d["confidence"],
                    class_id=d["class_id"]
                ))

            return detections
    except Exception as e:
        print(f"[VISUAL] CLIP inference error: {e}")
        import traceback
        traceback.print_exc()

    return []


def analyze_video(
    video_url: str,
    video_title: str = "Unknown",
    fps: float = 2.0,
    threshold: float = 0.02,  # 2% threshold - lower to catch more actions
    force_reprocess: bool = False,
    action_keywords: List[str] = None,  # Filter by action type keywords
    min_clip_duration: float = 5.0,  # Minimum clip duration in seconds
    model: str = "clip"  # "clip" or "slowfast" - CLIP is default (better for slapstick)
) -> Optional[VideoAnalysisResult]:
    """
    Analyze a video for physical comedy actions.

    Args:
        video_url: YouTube URL or local video path
        video_title: Title of the video
        fps: Frames per second to extract (higher = more accurate, slower)
        threshold: Confidence threshold for detections (0-1)
        force_reprocess: Re-analyze even if already processed
        action_keywords: List of keywords to filter actions (e.g., ["fall", "trip", "slap"])
        min_clip_duration: Minimum clip duration in seconds (clips shorter than this are discarded)
        model: Detection model - "clip" (recommended) or "slowfast"
            - CLIP: Better at semantic matching (slapstick, hitting, chasing)
            - SlowFast: Better at specific Kinetics-400 actions (may miss comedy)

    Returns:
        VideoAnalysisResult or None if failed
    """
    action_keywords = action_keywords or []

    # Check if already processed (but still apply filters to cached data)
    if not force_reprocess:
        is_processed, cached_result = is_video_processed(video_url)
        if is_processed:
            print(f"[VISUAL] Video already processed: {video_title}")
            # Convert cached result back to VideoAnalysisResult
            result = VideoAnalysisResult(
                video_id=cached_result["video_id"],
                video_url=cached_result["video_url"],
                video_title=cached_result["video_title"],
                duration_seconds=cached_result["duration_seconds"],
                analyzed_date=cached_result["analyzed_date"],
                total_detections=cached_result["total_detections"],
                detections=cached_result["detections"],
                analysis_params=cached_result["analysis_params"]
            )
            # Apply filters to cached detections
            filtered_dets = result.detections

            # Filter by confidence threshold
            if threshold > 0:
                filtered_dets = [d for d in filtered_dets
                               if d.get("confidence", 0) >= threshold]

            # Filter by action keywords if provided
            if action_keywords:
                filtered_dets = [d for d in filtered_dets
                               if any(kw.lower() in d.get("action_class", "").lower() or
                                     d.get("action_class", "").lower() in kw.lower()
                                     for kw in action_keywords)]

            # Filter by minimum clip duration
            if min_clip_duration > 0:
                filtered_dets = [d for d in filtered_dets
                               if d.get("duration", 0) >= min_clip_duration]

            result.detections = filtered_dets
            result.total_detections = len(filtered_dets)
            print(f"[VISUAL] Cached result filtered: {len(result.detections)} detections (threshold={threshold:.0%})")
            return result

    video_id = extract_video_id(video_url)
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    os.makedirs(FRAMES_FOLDER, exist_ok=True)

    # Determine if URL or local file
    is_local = os.path.exists(video_url)

    if is_local:
        video_path = video_url
        print(f"[VISUAL] Using local file: {video_path}")
    else:
        # Download video
        video_path = str(TEMP_FOLDER / f"{video_id}_temp.mp4")
        print(f"[VISUAL] Downloading: {video_url}")

        if not download_video(video_url, video_path):
            print(f"[VISUAL] Failed to download video")
            return None

    # Get duration
    duration = get_video_duration(video_path)
    print(f"[VISUAL] Duration: {duration:.1f}s")

    # Extract frames
    frames_dir = str(FRAMES_FOLDER / video_id)
    print(f"[VISUAL] Extracting frames at {fps} FPS...")
    frame_paths = extract_frames(video_path, frames_dir, fps)

    if not frame_paths:
        print(f"[VISUAL] Failed to extract frames")
        return None

    print(f"[VISUAL] Extracted {len(frame_paths)} frames")

    # Run inference based on selected model
    if model.lower() == "clip":
        print(f"[VISUAL] Running CLIP inference (better for slapstick)...")
        # CLIP needs higher threshold (0.20-0.30) since it uses cosine similarity
        clip_threshold = max(threshold, 0.20) if threshold < 0.10 else threshold
        detections = run_clip_inference(frame_paths, fps, clip_threshold)
    else:
        print(f"[VISUAL] Running SlowFast inference...")
        detections = run_inference(frame_paths, fps, threshold)
    print(f"[VISUAL] Raw detections: {len(detections)}")

    # Apply action keyword filter if provided
    if action_keywords:
        print(f"[VISUAL] Filtering by keywords: {action_keywords}")
        detections = filter_detections_by_keywords(detections, action_keywords)
        print(f"[VISUAL] After filtering: {len(detections)} detections")

    # NO MERGING - each detection is its own clip
    # Add padding around each detection to create clip boundaries
    padding = min_clip_duration / 2  # Half of min duration on each side

    clips_data = []
    skipped_count = 0
    for det in detections:
        start_time = max(0, det.timestamp - padding)
        end_time = min(duration, det.timestamp + padding)
        clip_duration = end_time - start_time

        # SKIP clips shorter than minimum duration (don't extend them)
        if clip_duration < min_clip_duration:
            skipped_count += 1
            continue

        clips_data.append({
            "timestamp": round(start_time, 1),
            "timestamp_str": seconds_to_timestamp(start_time),
            "end_time": round(end_time, 1),
            "end_str": seconds_to_timestamp(end_time),
            "duration": round(clip_duration, 1),
            "action_class": det.action_class,
            "action_classes": [det.action_class],
            "confidence": det.confidence,
            "detection_count": 1,
            "class_id": det.class_id
        })

    if skipped_count > 0:
        print(f"[VISUAL] Skipped {skipped_count} clips shorter than {min_clip_duration}s")

    print(f"[VISUAL] Found {len(clips_data)} individual detections (no merging)")

    # Create result
    result = VideoAnalysisResult(
        video_id=video_id,
        video_url=video_url,
        video_title=video_title,
        duration_seconds=duration,
        analyzed_date=datetime.now().isoformat(),
        total_detections=len(clips_data),
        detections=clips_data,  # Individual clips (no merging)
        analysis_params={
            "fps": fps,
            "threshold": threshold,
            "model": model.lower()
        }
    )

    # Save to database
    save_video_result(result)

    # Cleanup
    if not is_local and os.path.exists(video_path):
        try:
            os.remove(video_path)
        except:
            pass

    # Clean up frames
    try:
        import shutil
        shutil.rmtree(frames_dir, ignore_errors=True)
    except:
        pass

    return result


def format_results(result: VideoAnalysisResult) -> str:
    """Format analysis results for display"""
    lines = [
        f"Video: {result.video_title}",
        f"Duration: {seconds_to_timestamp(result.duration_seconds)}",
        f"Analyzed: {result.analyzed_date[:10]}",
        f"Detections: {result.total_detections}",
        "-" * 50
    ]

    if not result.detections:
        lines.append("No physical comedy actions detected.")
    else:
        for det in result.detections:
            conf_bar = "#" * int(det["confidence"] * 10)
            lines.append(
                f"[{det['timestamp_str']}] {det['action_class'].upper():20} "
                f"{conf_bar:10} ({det['confidence']:.2f})"
            )

    return "\n".join(lines)


def search_youtube(query: str, max_results: int = 10, max_duration_minutes: int = 0) -> List[Dict]:
    """Search YouTube for videos matching query

    Args:
        query: Search query
        max_results: Maximum number of results to return
        max_duration_minutes: Maximum video duration in minutes (0 = no limit)
    """
    # Search for more results than needed to account for duration filtering
    search_count = max_results * 3 if max_duration_minutes > 0 else max_results

    cmd = [
        "yt-dlp",
        "--dump-json",
        "--flat-playlist",
        f"ytsearch{search_count}:{query}"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        max_duration_sec = max_duration_minutes * 60 if max_duration_minutes > 0 else 0

        for line in result.stdout.strip().split("\n"):
            if line:
                data = json.loads(line)
                duration = data.get("duration", 0) or 0

                # Filter by duration if specified
                if max_duration_sec > 0 and duration > max_duration_sec:
                    continue

                videos.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", "Unknown"),
                    "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                    "duration": duration
                })

                # Stop if we have enough results
                if len(videos) >= max_results:
                    break

        return videos
    except:
        return []


def get_benny_hill_videos(max_results: int = 20, max_duration_minutes: int = 0) -> List[Dict]:
    """Get initial set of Benny Hill videos to process

    Args:
        max_results: Maximum number of results to return
        max_duration_minutes: Maximum video duration in minutes (0 = no limit)
    """
    queries = [
        "Benny Hill chase scene",
        "Benny Hill compilation falls",
        "Benny Hill slapstick funny",
        "Benny Hill best moments"
    ]

    all_videos = []
    seen_ids = set()

    for query in queries:
        videos = search_youtube(query, max_results // len(queries), max_duration_minutes)
        for v in videos:
            if v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                all_videos.append(v)

    return all_videos[:max_results]


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python visual_analysis.py <video_url_or_path>")
        print("  python visual_analysis.py --search <query>")
        print("  python visual_analysis.py --benny-hill")
        print("")
        print("Examples:")
        print("  python visual_analysis.py 'https://youtube.com/watch?v=xxx'")
        print("  python visual_analysis.py video.mp4")
        print("  python visual_analysis.py --search 'Benny Hill falls'")
        print("  python visual_analysis.py --benny-hill")
        sys.exit(1)

    if sys.argv[1] == "--search":
        query = " ".join(sys.argv[2:])
        print(f"[VISUAL] Searching: {query}")
        videos = search_youtube(query)
        for i, v in enumerate(videos, 1):
            print(f"{i}. {v['title'][:50]} ({v['duration']}s)")
            print(f"   {v['url']}")

    elif sys.argv[1] == "--benny-hill":
        print("[VISUAL] Getting Benny Hill videos...")
        videos = get_benny_hill_videos()

        db = load_processed_database()
        unprocessed = []

        for v in videos:
            video_hash = get_video_hash(v["url"])
            if video_hash not in db["videos"]:
                unprocessed.append(v)

        print(f"[VISUAL] Found {len(videos)} videos, {len(unprocessed)} unprocessed")

        for v in unprocessed[:5]:  # Process first 5
            print(f"\n[VISUAL] Analyzing: {v['title']}")
            result = analyze_video(v["url"], v["title"])
            if result:
                print(format_results(result))

    else:
        video_input = sys.argv[1]
        print(f"[VISUAL] Analyzing: {video_input}")
        result = analyze_video(video_input)
        if result:
            print("\n" + "=" * 60)
            print(format_results(result))
        else:
            print("[VISUAL] Analysis failed")
