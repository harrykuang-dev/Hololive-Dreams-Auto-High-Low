"""Validated icon loading, including non-ASCII Windows installation paths."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=128)
def load_icon(path):
    path = Path(path)
    try:
        encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        if encoded.size == 0:
            raise ValueError('empty file')
        image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        if image is None or image.size == 0:
            raise ValueError('invalid image')
    except (OSError, ValueError, cv2.error) as exc:
        raise RuntimeError(f'无法读取图标模板：{path}。请完整解压程序并保留 _internal 文件夹。') from exc
    return image


def frame_gray(frame):
    if not isinstance(frame, np.ndarray) or frame.size == 0:
        return None
    if frame.dtype != np.uint8:
        return None
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return None


def match_icon(gray, path):
    """Return (score, top-left, template size), or None for an unusable frame."""
    if gray is None:
        return None
    template = load_icon(str(path))
    h, w = template.shape
    if gray.shape[0] < h or gray.shape[1] < w:
        return None
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    return score, location, (h, w)
