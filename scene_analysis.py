"""
Scene-Based Visual Analysis Module for QuickTube v2
Improved approach: Download -> Scene Detection -> Dedupe -> Classify -> Preview -> Save

Key improvements over v1:
- Scene-based detection (not frame-by-frame)
- Perceptual hash deduplication (removes similar scenes)
- User preview before saving
- Progress callbacks for UI updates
"""

import os
import json
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple
import shutil

# Paths
QUICKTUBE_DIR = Path(r"D:\QuickTube")
TEMP_FOLDER = QUICKTUBE_DIR / "temp"
SCENE_CACHE_DIR = TEMP_FOLDER / "scene_cache"
THUMBNAILS_DIR = TEMP_FOLDER / "thumbnails"
CONDA_ENV = "video_analysis"


@dataclass
class SceneCandidate:
    """A detected scene that may contain physical comedy"""
    scene_id: int
    start_time: float
    end_time: float
    duration: float
    start_str: str  # "00:01:23"
    end_str: str
    thumbnail_path: str  # Path to thumbnail image
    action_label: str  # "slapstick comedy", "chase scene", etc.
    confidence: float  # 0-1
    hash_value: str  # Perceptual hash for deduplication
    is_duplicate: bool = False
    duplicate_of: int = -1  # Scene ID this is duplicate of
    user_selected: bool = True  # User selection for saving


@dataclass
class AnalysisProgress:
    """Progress update for UI callbacks"""
    step: str  # "downloading", "detecting_scenes", "deduplicating", etc.
    step_number: int  # 1-6
    total_steps: int  # 6
    progress: float  # 0-100 for current step
    message: str  # Human readable status
    detail: str = ""  # Optional detail (e.g., "Scene 5/23")


@dataclass
class VideoAnalysisResult:
    """Complete analysis result for a video"""
    video_id: str
    video_url: str
    video_title: str
    video_path: str  # Local path to downloaded video
    duration_seconds: float
    total_scenes: int
    unique_scenes: int
    candidates: List[SceneCandidate]
    analysis_time: float  # Seconds taken
    analyzed_date: str


def seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def get_video_hash(video_url: str) -> str:
    """Generate unique hash for a video URL"""
    return hashlib.md5(video_url.encode()).hexdigest()[:12]


def extract_video_id(video_url: str) -> str:
    """Extract YouTube video ID from URL"""
    if "v=" in video_url:
        return video_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        return video_url.split("youtu.be/")[1].split("?")[0]
    elif "shorts/" in video_url:
        return video_url.split("shorts/")[1].split("?")[0]
    return get_video_hash(video_url)


def download_video(
    video_url: str,
    output_path: str,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> bool:
    """Download video using yt-dlp with progress updates"""

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[height<=720][ext=mp4]/best[ext=mp4]/best",
        "-o", output_path,
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--newline",  # Progress on new lines
        "--cookies-from-browser", "firefox",
        video_url
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            if "[download]" in line and "%" in line:
                # Parse progress like "[download]  45.2% of 50.00MiB"
                try:
                    pct = float(line.split("%")[0].split()[-1])
                    if progress_callback:
                        progress_callback(AnalysisProgress(
                            step="downloading",
                            step_number=1,
                            total_steps=6,
                            progress=pct,
                            message="Downloading video...",
                            detail=f"{pct:.0f}% complete"
                        ))
                except:
                    pass

        process.wait()
        return os.path.exists(output_path)

    except Exception as e:
        print(f"[SCENE] Download error: {e}")
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


def detect_scenes(
    video_path: str,
    threshold: float = 27.0,
    min_scene_len: float = 2.0,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> List[Tuple[float, float]]:
    """
    Detect scene boundaries using PySceneDetect.
    Returns list of (start_time, end_time) tuples.
    """
    # Create scene detection script
    script = f'''
import sys
from scenedetect import open_video, SceneManager, ContentDetector

video = open_video("{video_path.replace(chr(92), '/')}")
scene_manager = SceneManager()

# Calculate min_scene_len in frames (min_scene_len_sec * frame_rate)
min_scene_frames = int({min_scene_len} * video.frame_rate)
scene_manager.add_detector(ContentDetector(threshold={threshold}, min_scene_len=min_scene_frames))

# Detect scenes with progress
scene_manager.detect_scenes(video, show_progress=False)

# Get scene list
scene_list = scene_manager.get_scene_list()

# Output as JSON
import json
scenes = []
for i, (start, end) in enumerate(scene_list):
    scenes.append({{
        "start": start.get_seconds(),
        "end": end.get_seconds()
    }})
    # Progress output
    if len(scene_list) > 0:
        print(f"PROGRESS:{{int((i+1)/len(scene_list)*100)}}", flush=True)

print("SCENES:" + json.dumps(scenes))
'''

    script_path = TEMP_FOLDER / "scene_detect_script.py"
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    with open(script_path, 'w') as f:
        f.write(script)

    cmd = f'conda run -n {CONDA_ENV} python "{script_path}"'

    try:
        if progress_callback:
            progress_callback(AnalysisProgress(
                step="detecting_scenes",
                step_number=2,
                total_steps=6,
                progress=0,
                message="Detecting scene boundaries...",
                detail="Analyzing video for cuts"
            ))

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )

        scenes = []
        for line in process.stdout:
            line = line.strip()
            if line.startswith("PROGRESS:"):
                pct = int(line.split(":")[1])
                if progress_callback:
                    progress_callback(AnalysisProgress(
                        step="detecting_scenes",
                        step_number=2,
                        total_steps=6,
                        progress=pct,
                        message="Detecting scene boundaries...",
                        detail=f"{pct}% complete"
                    ))
            elif line.startswith("SCENES:"):
                scenes_json = line[7:]
                scenes_data = json.loads(scenes_json)
                scenes = [(s["start"], s["end"]) for s in scenes_data]

        process.wait()
        return scenes

    except Exception as e:
        print(f"[SCENE] Scene detection error: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_scene_thumbnails(
    video_path: str,
    scenes: List[Tuple[float, float]],
    output_dir: str,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> List[str]:
    """Extract a thumbnail from the middle of each scene"""
    os.makedirs(output_dir, exist_ok=True)

    thumbnail_paths = []
    total = len(scenes)

    for i, (start, end) in enumerate(scenes):
        # Get frame from middle of scene
        mid_time = (start + end) / 2
        thumb_path = os.path.join(output_dir, f"scene_{i:04d}.jpg")

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(mid_time),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            thumb_path
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
            if os.path.exists(thumb_path):
                thumbnail_paths.append(thumb_path)
            else:
                thumbnail_paths.append("")
        except:
            thumbnail_paths.append("")

        if progress_callback:
            progress_callback(AnalysisProgress(
                step="extracting_thumbnails",
                step_number=3,
                total_steps=6,
                progress=((i + 1) / total) * 100,
                message="Extracting scene thumbnails...",
                detail=f"Scene {i + 1}/{total}"
            ))

    return thumbnail_paths


def compute_image_hashes(
    thumbnail_paths: List[str],
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> List[str]:
    """Compute perceptual hashes for thumbnails using imagehash"""

    script = '''
import sys
import json
import imagehash
from PIL import Image

# Read paths from file
with open(sys.argv[1], 'r') as f:
    paths = json.load(f)
hashes = []

for i, path in enumerate(paths):
    try:
        if path and __import__('os').path.exists(path):
            img = Image.open(path)
            h = str(imagehash.dhash(img, hash_size=16))
            hashes.append(h)
        else:
            hashes.append("")
    except:
        hashes.append("")

    # Progress
    print(f"PROGRESS:{int((i+1)/len(paths)*100)}", flush=True)

print("HASHES:" + json.dumps(hashes))
'''

    script_path = TEMP_FOLDER / "hash_script.py"
    with open(script_path, 'w') as f:
        f.write(script)

    # Write paths to a temp file (Windows command line can't handle JSON args properly)
    paths_file = TEMP_FOLDER / "hash_paths.json"
    with open(paths_file, 'w') as f:
        json.dump(thumbnail_paths, f)

    cmd = f'conda run -n {CONDA_ENV} python "{script_path}" "{paths_file}"'

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )

        hashes = []
        for line in process.stdout:
            line = line.strip()
            if line.startswith("PROGRESS:"):
                pct = int(line.split(":")[1])
                if progress_callback:
                    progress_callback(AnalysisProgress(
                        step="computing_hashes",
                        step_number=3,
                        total_steps=6,
                        progress=pct,
                        message="Computing scene fingerprints...",
                        detail=f"{pct}% complete"
                    ))
            elif line.startswith("HASHES:"):
                hashes = json.loads(line[7:])

        process.wait()
        return hashes

    except Exception as e:
        print(f"[SCENE] Hash computation error: {e}")
        return [""] * len(thumbnail_paths)


def deduplicate_scenes(
    scenes: List[Tuple[float, float]],
    hashes: List[str],
    similarity_threshold: int = 10,  # Hamming distance threshold
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> List[Tuple[int, bool, int]]:
    """
    Find duplicate scenes based on perceptual hash similarity.
    Returns list of (scene_idx, is_duplicate, duplicate_of_idx)
    """
    results = []
    unique_hashes = {}  # hash -> scene_idx

    total = len(scenes)

    for i, h in enumerate(hashes):
        is_dup = False
        dup_of = -1

        if h:
            # Compare with existing hashes
            for existing_hash, existing_idx in unique_hashes.items():
                if existing_hash and h:
                    # Compute Hamming distance
                    try:
                        dist = sum(c1 != c2 for c1, c2 in zip(h, existing_hash))
                        if dist <= similarity_threshold:
                            is_dup = True
                            dup_of = existing_idx
                            break
                    except:
                        pass

            if not is_dup:
                unique_hashes[h] = i

        results.append((i, is_dup, dup_of))

        if progress_callback:
            progress_callback(AnalysisProgress(
                step="deduplicating",
                step_number=4,
                total_steps=6,
                progress=((i + 1) / total) * 100,
                message="Removing duplicate scenes...",
                detail=f"Checked {i + 1}/{total} scenes"
            ))

    return results


def classify_scenes_with_clip(
    thumbnail_paths: List[str],
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> List[Tuple[str, float]]:
    """
    Classify scenes using CLIP model.
    Returns list of (action_label, confidence)
    """

    # CLIP text prompts for physical comedy
    text_prompts = {
        "a person slapping another person": "slapping",
        "someone hitting another person on the head": "head slapping",
        "slapstick comedy scene with physical humor": "slapstick comedy",
        "people chasing each other running": "chase scene",
        "a person falling down or tripping": "falling/tripping",
        "someone doing a pratfall or stumbling": "pratfall",
        "people fighting in a funny comedic way": "comedic fighting",
        "exaggerated silly physical movements": "silly movements",
        "a pie being thrown at someone": "pie in face",
        "people running in fast motion sped up": "fast motion",
        "women in swimsuits or bikinis": "bikini scene",
        "man chasing women comedy": "chase comedy",
        "person being pushed or knocked over": "knocked over",
        "dancing or exaggerated movements": "dancing",
        "normal conversation or talking": "dialogue",
        "scenery or landscape shot": "scenery",
        "credits or title screen": "credits",
    }

    script = f'''
import sys
import json
import torch
import clip
from PIL import Image

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

TEXT_PROMPTS = {json.dumps(text_prompts)}
prompt_texts = list(TEXT_PROMPTS.keys())
prompt_labels = list(TEXT_PROMPTS.values())

# Encode text prompts once
text_tokens = clip.tokenize(prompt_texts).to(device)
with torch.no_grad():
    text_features = model.encode_text(text_tokens)
    text_features = text_features / text_features.norm(dim=-1, keepdim=True)

# Read paths from file
with open(sys.argv[1], 'r') as f:
    paths = json.load(f)
results = []

for i, path in enumerate(paths):
    try:
        if path and __import__('os').path.exists(path):
            img = Image.open(path).convert("RGB")
            img_tensor = preprocess(img).unsqueeze(0).to(device)

            with torch.no_grad():
                image_features = model.encode_image(img_tensor)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            similarities = (image_features @ text_features.T)[0].cpu().numpy()

            # Get best match
            best_idx = similarities.argmax()
            best_label = prompt_labels[best_idx]
            best_score = float(similarities[best_idx])

            results.append({{"label": best_label, "confidence": best_score}})
        else:
            results.append({{"label": "unknown", "confidence": 0.0}})
    except Exception as e:
        results.append({{"label": "error", "confidence": 0.0}})

    print(f"PROGRESS:{{int((i+1)/len(paths)*100)}}", flush=True)

print("RESULTS:" + json.dumps(results))
'''

    script_path = TEMP_FOLDER / "clip_classify_script.py"
    with open(script_path, 'w') as f:
        f.write(script)

    # Write paths to a temp file (Windows command line can't handle JSON args properly)
    paths_file = TEMP_FOLDER / "clip_paths.json"
    with open(paths_file, 'w') as f:
        json.dump(thumbnail_paths, f)

    cmd = f'conda run -n {CONDA_ENV} python "{script_path}" "{paths_file}"'

    try:
        if progress_callback:
            progress_callback(AnalysisProgress(
                step="classifying",
                step_number=5,
                total_steps=6,
                progress=0,
                message="Classifying scenes with AI...",
                detail="Loading CLIP model"
            ))

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )

        results = []
        for line in process.stdout:
            line = line.strip()
            if line.startswith("PROGRESS:"):
                pct = int(line.split(":")[1])
                if progress_callback:
                    progress_callback(AnalysisProgress(
                        step="classifying",
                        step_number=5,
                        total_steps=6,
                        progress=pct,
                        message="Classifying scenes with AI...",
                        detail=f"{pct}% complete"
                    ))
            elif line.startswith("RESULTS:"):
                data = json.loads(line[8:])
                results = [(r["label"], r["confidence"]) for r in data]

        process.wait()
        return results

    except Exception as e:
        print(f"[SCENE] CLIP classification error: {e}")
        import traceback
        traceback.print_exc()
        return [("unknown", 0.0)] * len(thumbnail_paths)


def analyze_video_scenes(
    video_url: str,
    video_title: str = "Unknown",
    min_confidence: float = 0.20,
    similarity_threshold: int = 10,
    scene_threshold: float = 27.0,
    min_scene_len: float = 2.0,
    exclude_labels: List[str] = None,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> Optional[VideoAnalysisResult]:
    """
    Full scene-based analysis pipeline:
    1. Download video
    2. Detect scenes
    3. Extract thumbnails
    4. Compute hashes & deduplicate
    5. Classify with CLIP
    6. Return candidates for user preview
    """
    import time
    start_time = time.time()

    exclude_labels = exclude_labels or ["dialogue", "scenery", "credits", "unknown", "error"]

    video_id = extract_video_id(video_url)
    os.makedirs(TEMP_FOLDER, exist_ok=True)
    os.makedirs(SCENE_CACHE_DIR, exist_ok=True)

    # Create video-specific directories
    video_cache_dir = SCENE_CACHE_DIR / video_id
    thumb_dir = video_cache_dir / "thumbnails"
    os.makedirs(thumb_dir, exist_ok=True)

    video_path = str(video_cache_dir / f"{video_id}.mp4")

    # === STEP 1: Download video ===
    if progress_callback:
        progress_callback(AnalysisProgress(
            step="downloading",
            step_number=1,
            total_steps=6,
            progress=0,
            message="Downloading video...",
            detail="Starting download"
        ))

    is_local = os.path.exists(video_url)
    if is_local:
        video_path = video_url
        print(f"[SCENE] Using local file: {video_path}")
    elif not os.path.exists(video_path):
        if not download_video(video_url, video_path, progress_callback):
            print(f"[SCENE] Failed to download video")
            return None
    else:
        print(f"[SCENE] Using cached video: {video_path}")

    duration = get_video_duration(video_path)
    print(f"[SCENE] Video duration: {duration:.1f}s")

    # === STEP 2: Detect scenes ===
    if progress_callback:
        progress_callback(AnalysisProgress(
            step="detecting_scenes",
            step_number=2,
            total_steps=6,
            progress=0,
            message="Detecting scene boundaries...",
            detail="Analyzing video structure"
        ))

    scenes = detect_scenes(video_path, scene_threshold, min_scene_len, progress_callback)
    print(f"[SCENE] Detected {len(scenes)} scenes")

    if not scenes:
        # Fallback: create scenes every 5 seconds
        scenes = [(i * 5, min((i + 1) * 5, duration)) for i in range(int(duration // 5) + 1)]
        print(f"[SCENE] Using fallback: {len(scenes)} segments")

    # === STEP 3: Extract thumbnails ===
    if progress_callback:
        progress_callback(AnalysisProgress(
            step="extracting_thumbnails",
            step_number=3,
            total_steps=6,
            progress=0,
            message="Extracting scene thumbnails...",
            detail=f"Processing {len(scenes)} scenes"
        ))

    thumbnail_paths = extract_scene_thumbnails(video_path, scenes, str(thumb_dir), progress_callback)
    print(f"[SCENE] Extracted {len([p for p in thumbnail_paths if p])} thumbnails")

    # === STEP 4: Compute hashes & deduplicate ===
    if progress_callback:
        progress_callback(AnalysisProgress(
            step="deduplicating",
            step_number=4,
            total_steps=6,
            progress=0,
            message="Finding duplicate scenes...",
            detail="Computing fingerprints"
        ))

    hashes = compute_image_hashes(thumbnail_paths, progress_callback)
    dup_results = deduplicate_scenes(scenes, hashes, similarity_threshold, progress_callback)

    unique_count = sum(1 for _, is_dup, _ in dup_results if not is_dup)
    print(f"[SCENE] Found {unique_count} unique scenes (removed {len(scenes) - unique_count} duplicates)")

    # === STEP 5: Classify scenes with CLIP ===
    # Only classify unique scenes
    unique_indices = [i for i, is_dup, _ in dup_results if not is_dup]
    unique_thumbs = [thumbnail_paths[i] if i < len(thumbnail_paths) else "" for i in unique_indices]

    if progress_callback:
        progress_callback(AnalysisProgress(
            step="classifying",
            step_number=5,
            total_steps=6,
            progress=0,
            message="Classifying scenes with AI...",
            detail=f"Analyzing {len(unique_thumbs)} unique scenes"
        ))

    classifications = classify_scenes_with_clip(unique_thumbs, progress_callback)

    # Map classifications back to all scenes
    class_map = {}
    for idx, (label, conf) in zip(unique_indices, classifications):
        class_map[idx] = (label, conf)

    # === STEP 6: Build candidates ===
    if progress_callback:
        progress_callback(AnalysisProgress(
            step="finalizing",
            step_number=6,
            total_steps=6,
            progress=50,
            message="Building clip candidates...",
            detail="Filtering results"
        ))

    candidates = []
    for i, (start, end) in enumerate(scenes):
        _, is_dup, dup_of = dup_results[i]

        # Get classification (from this scene or the one it duplicates)
        if i in class_map:
            label, conf = class_map[i]
        elif dup_of in class_map:
            label, conf = class_map[dup_of]
        else:
            label, conf = "unknown", 0.0

        # Skip excluded labels and low confidence
        if label in exclude_labels or conf < min_confidence:
            continue

        # Skip duplicates
        if is_dup:
            continue

        thumb_path = thumbnail_paths[i] if i < len(thumbnail_paths) else ""
        hash_val = hashes[i] if i < len(hashes) else ""

        candidate = SceneCandidate(
            scene_id=i,
            start_time=start,
            end_time=end,
            duration=end - start,
            start_str=seconds_to_timestamp(start),
            end_str=seconds_to_timestamp(end),
            thumbnail_path=thumb_path,
            action_label=label,
            confidence=conf,
            hash_value=hash_val,
            is_duplicate=is_dup,
            duplicate_of=dup_of,
            user_selected=True
        )
        candidates.append(candidate)

    # Sort by confidence (best first)
    candidates.sort(key=lambda c: -c.confidence)

    elapsed = time.time() - start_time

    if progress_callback:
        progress_callback(AnalysisProgress(
            step="complete",
            step_number=6,
            total_steps=6,
            progress=100,
            message="Analysis complete!",
            detail=f"Found {len(candidates)} clip candidates in {elapsed:.1f}s"
        ))

    print(f"[SCENE] Analysis complete: {len(candidates)} candidates in {elapsed:.1f}s")

    result = VideoAnalysisResult(
        video_id=video_id,
        video_url=video_url,
        video_title=video_title,
        video_path=video_path,
        duration_seconds=duration,
        total_scenes=len(scenes),
        unique_scenes=unique_count,
        candidates=candidates,
        analysis_time=elapsed,
        analyzed_date=datetime.now().isoformat()
    )

    return result


def extract_clip(
    video_path: str,
    start_time: float,
    end_time: float,
    output_path: str,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> bool:
    """Extract a clip from video using ffmpeg"""

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", video_path,
        "-t", str(end_time - start_time),
        "-c", "copy",  # Fast copy without re-encoding
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"[SCENE] Clip extraction error: {e}")
        return False


def save_selected_clips(
    result: VideoAnalysisResult,
    output_folder: str,
    progress_callback: Optional[Callable[[AnalysisProgress], None]] = None
) -> List[str]:
    """Save user-selected clips to output folder"""

    os.makedirs(output_folder, exist_ok=True)
    saved_paths = []

    selected = [c for c in result.candidates if c.user_selected]
    total = len(selected)

    for i, candidate in enumerate(selected):
        # Create filename
        safe_title = "".join(c for c in result.video_title[:30] if c.isalnum() or c in " -_").strip()
        filename = f"{safe_title}_{candidate.start_str.replace(':', '-')}_{candidate.action_label}.mp4"
        output_path = os.path.join(output_folder, filename)

        if progress_callback:
            progress_callback(AnalysisProgress(
                step="saving_clips",
                step_number=1,
                total_steps=1,
                progress=((i + 1) / total) * 100,
                message="Saving clips...",
                detail=f"Clip {i + 1}/{total}: {candidate.action_label}"
            ))

        if extract_clip(result.video_path, candidate.start_time, candidate.end_time, output_path):
            saved_paths.append(output_path)
            print(f"[SCENE] Saved: {filename}")
        else:
            print(f"[SCENE] Failed to save: {filename}")

    return saved_paths


# Test function
if __name__ == "__main__":
    import sys

    def print_progress(p: AnalysisProgress):
        bar_len = 30
        filled = int(p.progress / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[{p.step_number}/{p.total_steps}] {p.message} [{bar}] {p.progress:.0f}% - {p.detail}", end="", flush=True)
        if p.progress >= 100 or p.step == "complete":
            print()

    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(f"Analyzing: {url}")
        result = analyze_video_scenes(url, progress_callback=print_progress)

        if result:
            print(f"\n{'='*60}")
            print(f"Video: {result.video_title}")
            print(f"Duration: {result.duration_seconds:.1f}s")
            print(f"Total scenes: {result.total_scenes}")
            print(f"Unique scenes: {result.unique_scenes}")
            print(f"Candidates: {len(result.candidates)}")
            print(f"Analysis time: {result.analysis_time:.1f}s")
            print(f"{'='*60}")

            for c in result.candidates[:10]:
                print(f"  [{c.start_str}-{c.end_str}] {c.action_label:20} {c.confidence*100:.1f}%")
    else:
        print("Usage: python scene_analysis.py <video_url>")
