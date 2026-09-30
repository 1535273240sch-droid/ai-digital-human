"""从素材视频里自动挑出「闭嘴 + 头部稳定」的连续片段，用于重建数字人形象。

判据（dlib 68 点，缩放后跑以提速）：
  - mouth_open : 内唇上下距离 / 眼距（越小越闭嘴）
  - head_move  : 鼻尖+双眼中心的相邻帧位移 / 眼距（越小越稳）
输出：把最佳窗口的帧拷到 out_dir（默认 50 帧 ≈ 2 秒循环）
"""
import glob
import os
import shutil
import sys

import cv2
import dlib
import numpy as np

SRC_DIR = sys.argv[1] if len(sys.argv) > 1 else r"D:\AI\LiveTalking\data\avatars\musetalk_xiaoya\full_imgs"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\Administrator\Desktop\_pick_tmp"
WIN = int(sys.argv[3]) if len(sys.argv) > 3 else 50

os.makedirs(OUT_DIR, exist_ok=True)
for f in glob.glob(os.path.join(OUT_DIR, "*.png")):
    os.remove(f)

files = sorted(glob.glob(os.path.join(SRC_DIR, "*.png")), key=lambda p: int(os.path.splitext(os.path.basename(p))[0]))
print(f"frames: {len(files)}")

detector = dlib.get_frontal_face_detector()
import face_recognition_models  # noqa: E402

pred = dlib.shape_predictor(face_recognition_models.pose_predictor_model_location())
print("predictor: ok")

mouth, head, ok = [], [], []
for i, p in enumerate(files):
    img = cv2.imread(p)
    small = cv2.resize(img, (640, 360))
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    dets = detector(rgb, 0)
    if not dets:
        ok.append(False); mouth.append(1.0); head.append([0.0, 0.0])
        continue
    d = max(dets, key=lambda r: r.width() * r.height())
    lm = pred(rgb, d)
    pts = np.array([[lm.part(k).x, lm.part(k).y] for k in range(68)], dtype=np.float32)
    eye = np.linalg.norm(pts[36] - pts[45]) + 1e-6
    up = pts[62:65].mean(axis=0)
    lo = pts[66:69].mean(axis=0)
    m = float(np.linalg.norm(up - lo) / eye)
    nose = pts[30] / eye  # 用眼距归一化，尺度无关
    mouth.append(m); head.append([float(nose[0]), float(nose[1])]); ok.append(True)
    if i % 25 == 0:
        print(f"  {i}/{len(files)} mouth={m:.3f}")

head = np.array(head, dtype=np.float32)
valid = np.array(ok)
mv = np.linalg.norm(np.diff(head, axis=0), axis=1)
mv = np.concatenate([[mv[0]], mv])

mouth = np.array(mouth, dtype=np.float32)
n = len(files)
best, best_score = 0, 1e9
for s in range(0, n - WIN + 1):
    w_m = mouth[s:s + WIN].mean()
    w_v = mv[s:s + WIN].mean() * 20.0
    if not valid[s:s + WIN].all():
        w_m += 1.0
    score = w_m + w_v
    if score < best_score:
        best_score, best = score, s
print(f"best window: start={best} len={WIN} score={best_score:.3f} "
      f"mouth_avg={mouth[best:best+WIN].mean():.3f} move_avg={mv[best:best+WIN].mean():.4f}")

for k in range(best, best + WIN):
    src = files[k]
    dst = os.path.join(OUT_DIR, os.path.basename(src))
    shutil.copyfile(src, dst)
print("PICK_DONE", OUT_DIR, WIN)
