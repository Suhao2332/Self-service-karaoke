"""Test pipeline with user's video"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from core.lyrics_fetcher import LyricsFetcher
from core.karaoke_renderer import KaraokeRenderer, KaraokeStyleConfig

# Step 1: Search lyrics
print("=" * 60)
print("Step 1: Searching lyrics for Scream...")
f = LyricsFetcher()
results = f.search_all_sources('Scream 万魔殿パンデモニウム 煉獄編', '祖堅正慶')
total = sum(len(v) for v in results.values())
print(f"Found {total} songs")

# Find best source
for src, songs in results.items():
    if songs:
        print(f"  Using [{src}]: {songs[0]['title']} / {songs[0]['artist']}")
        best_src = src
        best_song = songs[0]
        break

if total == 0:
    print("No songs found - trying alternative keywords")
    results = f.search_all_sources('Scream', '祖堅正慶')
    for src, songs in results.items():
        if songs:
            print(f"  [{src}]: {songs[0]['title']}")
            best_src = src
            best_song = songs[0]
            break

# Step 2: Fetch lyrics
print("\nStep 2: Fetching lyrics...")
source_key = "netease"
if "酷狗" in best_src:
    source_key = "kugou"
elif "QQ" in best_src:
    source_key = "qqmusic"

extra = {}
if source_key == "kugou":
    extra = {"hash": best_song.get("hash", ""), "title": best_song["title"], "artist": best_song["artist"]}

lyrics = f.fetch_lyrics(best_song["id"], source_key, extra)
if lyrics:
    print(f"  LRC lines: {len(lyrics.get('lrc', []))}")
    print(f"  Word lyrics: {len(lyrics.get('word_lyrics', []))}")
    if lyrics.get('lrc'):
        for l in lyrics['lrc'][:3]:
            print(f"    [{l['time']:.1f}s] {l['text']}")

# Step 3: Render with DEFAULT style
print("\nStep 3: Rendering with DEFAULT style...")
video_path = os.path.join(os.path.dirname(__file__), 'test', '859039485-1-208.mp4')
output_path = os.path.join(os.path.dirname(__file__), 'output', 'test_scream_default.mp4')
os.makedirs(os.path.dirname(output_path), exist_ok=True)

renderer = KaraokeRenderer()
cfg = KaraokeStyleConfig()
try:
    result = renderer.render_karaoke(video_path, lyrics['lrc'], output_path, cfg)
    print(f"  Rendered: {result} ({os.path.getsize(result)} bytes)")
except Exception as e:
    print(f"  Render failed: {e}")

# Step 4: Render with MODIFIED style (large font, different colors)
print("\nStep 4: Rendering with MODIFIED style...")
cfg2 = KaraokeStyleConfig()
cfg2.font_size = 80
cfg2.font_name = "SimHei"
cfg2.primary_color = "&H000000FF"  # Red
cfg2.next_primary_color = "&H8C0000FF"  # Dimmed red
output_path2 = os.path.join(os.path.dirname(__file__), 'output', 'test_scream_modified.mp4')

renderer2 = KaraokeRenderer()
try:
    result2 = renderer2.render_karaoke(video_path, lyrics['lrc'], output_path2, cfg2)
    print(f"  Rendered: {result2} ({os.path.getsize(result2)} bytes)")
except Exception as e:
    print(f"  Render failed: {e}")

# Step 5: Inspect ASS files
print("\nStep 5: ASS file inspection")
for label, renderer_obj in [("DEFAULT", renderer), ("MODIFIED", renderer2)]:
    ass_path = renderer_obj.last_ass_path
    if ass_path and os.path.exists(ass_path):
        with open(ass_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"\n--- {label} ASS ({ass_path}) ---")
        for line in content.split('\n'):
            if line.startswith('Style:') or line.startswith('Dialogue:'):
                print(f"  {line[:120]}")
        
        # Check for issues
        lines = content.split('\n')
        dialogue_styles = set()
        for line in lines:
            if line.startswith('Dialogue:'):
                parts = line.split(',')
                dialogue_styles.add(parts[3])
        print(f"  Dialogue styles used: {dialogue_styles}")
        
        # Check if any dialogue uses wrong style
        singing_count = sum(1 for l in lines if 'Dialogue:' in l and '\\kf' in l)
        preview_count = sum(1 for l in lines if 'Dialogue:' in l and '\\kf' not in l and l.startswith('Dialogue:'))
        print(f"  Singing dialogues: {singing_count}, Preview dialogues: {preview_count}")

print("\nDone!")
