"""从项目 .env 读取 StepFun 密钥（避免把密钥写进代码后提交到仓库）。

默认路径：<仓库根>/LiveTalking/.env，可用环境变量 STEPFUN_API_KEY 覆盖。
"""
import io
import os
import re

ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LiveTalking", ".env"
)


def read_key(env_path: str = "") -> str:
    path = env_path or ENV_PATH
    try:
        s = io.open(path, encoding="utf-8", errors="ignore").read()
        m = re.search(r"^\s*STEPFUN_API_KEY\s*=\s*(\S+)", s, re.M)
        if m and m.group(1):
            return m.group(1)
    except Exception:
        pass
    return os.getenv("STEPFUN_API_KEY", "")
