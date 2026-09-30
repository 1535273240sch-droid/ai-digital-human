"""精确测量形象帧的唇缝宽度，挑出"最闭嘴"的一帧（用于做静态底图）。

dlib 68 点：
  内唇上缘 62,63,64 / 内唇下缘 66,67,68 → 唇缝高度（按眼距归一化）
  同时输出头部偏移（鼻尖相对首帧位移，按眼距归一化）
"""
import glob
import json
import os
import shutil

import cv2
import dlib
import face_recognition_models
import numpy as np

SRC = r"D:\AI\avatars_src\xiaoya_closed_mouth"
OUT = r"D:\AI\avatars_src\xiaoya_static"

detector = dlib.get_frontal_face_detector()
pred = dlib.shape_predictor(face_recognition_models.pose_predictor_model_location())

files = sorted(glob.glob(os.path.join(SRC, "*.png")))
rows = []
base_nose = None
for f in files:
    img = cv2.imread(f)
    small = cv2.resize(img, (640, 360))
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    dets = detector(rgb, 0)
    if not dets:
        rows.append((os.path.basename(f), None, None))
        continue
    d = max(dets, key=lambda r: r.width() * r.height())
    lm = pred(rgb, d)
    pts = np.array([[lm.part(k).x, lm.part(k).y] for k in range(68)], dtype=np.float32)
    eye = float(np.linalg.norm(pts[36] - pts[45])) + 1e-6
    up = pts[62:65].mean(axis=0)
    lo = pts[66:69].mean(axis=0)
    gap = float(np.linalg.norm(up - lo) / eye)
    nose = pts[30] / eye
    if base_nose is None:
        base_nose = nose
    off = float(np.linalg.norm(nose - base_nose))
    rows.append((os.path.basename(f), gap, off))

valid = [(n, g, o) for n, g, o in rows if g is not None]
valid_sorted = sorted(valid, key=lambda r: r[1])
print(f"共 {len(files)} 帧，有效 {len(valid)} 帧")
print("唇缝最窄的前 8 帧（越窄越闭嘴）：")
for n, g, o in valid_sorted[:8]:
    print(f"  {n}  gap={g:.4f}  头部位移={o:.4f}")
print("唇缝最宽的前 3 帧：")
for n, g, o in valid_sorted[-3:]:
    print(f"  {n}  gap={g:.4f}  头部位移={o:.4f}")

# 选择：唇缝尽量小 + 头部居中（位移小），综合打分
best = min(valid, key=lambda r: r[1] + 2.0 * r[2])
print("综合最佳（可做静态底图）：", best[0], f"gap={best[1]:.4f} off={best[2]:.4f}")

os.makedirs(OUT, exist_ok=True)
for f in glob.glob(os.path.join(OUT, "*.png")):
    os.remove(f)
shutil.copyfile(os.path.join(SRC, best[0]), os.path.join(OUT, "00000000.png"))

# 附带一份"前三窄"的备选，方便对比
for i, (n, g, o) in enumerate(valid_sorted[:3]):
    shutil.copyfile(os.path.join(SRC, n), os.path.join(OUT, f"alt{i}_{n}"))

with open(os.path.join(OUT, "measure.json"), "w", encoding="utf-8") as fh:
    json.dump([{"file": n, "gap": g, "offset": o} for n, g, o in valid], fh, ensure_ascii=False, indent=1)
print("STATIC_SRC_READY", OUT)
