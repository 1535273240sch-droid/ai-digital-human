"""从视频生成 MuseTalk 形象（等价于项目里 /avatar.html 的 CLI 版本）。"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LiveTalking")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "avatars", "musetalk", "utils"))
os.chdir(ROOT)

from avatars.musetalk.genavatar import generate_avatar  # noqa: E402

video = sys.argv[1]
avatar_id = sys.argv[2] if len(sys.argv) > 2 else "musetalk_xiaoya"

generate_avatar(
    video_path=video,
    avatar_id=avatar_id,
    save_path=os.path.join(ROOT, "data", "avatars"),
    bbox_shift=0,
    extra_margin=10,
    parsing_mode="jaw",
    version="v15",
    progress_callback=lambda p: print(f"progress: {p}%", flush=True),
)
print("AVATAR_GEN_DONE")
