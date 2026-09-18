import pygetwindow as gw
import mss
import numpy as np
import cv2
import ctypes
from ctypes import wintypes
import random
import time
import os
import json
import sys
from pathlib import Path
import ddddocr

from recognizer import CardRecognizer
from poker_core import calculate_best, JOKER_ID
from strategy_runtime import (
    ALL_IN_MODE,
    LEGACY_MODE,
    TIME_TARGET_MODE,
    StrategySession,
    StableNumber,
)
from high_low_strategy import TARGET, DAILY_CAP

try:
    # Windows source-mode runs otherwise inherit a legacy console encoding and
    # crash on the existing multilingual/emoji status messages.
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 直接全局初始化 OCR 引擎
ocr = ddddocr.DdddOcr(show_ad=False)

bot_running = False
# ================= 全局配置与常量 =================
GAME_TITLE = "hololive-Dreams"
TARGET_LIMIT = 19800

# All bundled assets are resolved relative to the executable/source directory.
# The old code depended on the process working directory, so launching from a
# shortcut or another folder made every template silently disappear.
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()
TEMPLATE_DIR = RESOURCE_DIR / "templates"
DEBUG_DIR = APP_DIR / "debug"
DATA_FILE = APP_DIR / "daily_coins.json"

# Icon templates and hard-coded recognition zones were captured at 1920x1080.
# Every game frame is normalized to this size before matching/recognition, and
# clicks are transformed back to the actual client size.
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080


def resource_path(*parts):
    return str(RESOURCE_DIR.joinpath(*parts))


try:
    # Must happen before Tk creates a window. It keeps Win32 coordinates,
    # PrintWindow output and background-click coordinates in the same DPI space.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_capture_context = None

_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.restype = wintypes.BOOL
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
_user32.PrintWindow.restype = wintypes.BOOL
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsWindow.restype = wintypes.BOOL
_user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ScreenToClient.restype = wintypes.BOOL
_user32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
_user32.ChildWindowFromPointEx.restype = wintypes.HWND
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.BringWindowToTop.argtypes = [wintypes.HWND]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]

_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.GetBitmapBits.argtypes = [wintypes.HBITMAP, wintypes.LONG, wintypes.LPVOID]
_gdi32.GetBitmapBits.restype = wintypes.LONG
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]

# Win32 mouse messages are delivered to the game window without moving or
# pressing the user's physical mouse cursor.
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004

# === 动态寻框参数 ===
CARD_WIDTH = 260
# 超大搜索区，覆盖整个屏幕中段，彻底杜绝漏抓
HIGH_LOW_SEARCH_ZONE = (42, 358, 1256, 451)

# 💰 奖金黄字 OCR 识别区 (!!! 必须用 get_coords.py 重新量取你的黄色数字坐标 !!!)
REWARD_ZONE = (606, 389, 870, 253)

# 💰 结算蓝字 OCR 识别区 (已保留你量好的数据)
RESULT_REWARD_ZONE = (1044, 337, 450, 97)

upcoming_card_val = None


# === 真实点数映射表 ===
def get_real_card_value(card):
    if card.card_id == JOKER_ID:
        return 0

    raw = str(card.rank).upper().strip()
    if "." in raw:
        raw = raw.split(".")[-1]

    robust_map = {
        "2": 2, "TWO": 2,
        "3": 3, "THREE": 3,
        "4": 4, "FOUR": 4,
        "5": 5, "FIVE": 5,
        "6": 6, "SIX": 6,
        "7": 7, "SEVEN": 7,
        "8": 8, "EIGHT": 8,
        "9": 9, "NINE": 9,
        "10": 10, "TEN": 10,
        "11": 11, "J": 11, "JACK": 11,
        "12": 12, "Q": 12, "QUEEN": 12,
        "13": 13, "K": 13, "KING": 13,
        "14": 14, "A": 14, "ACE": 14, "1": 14
    }

    if raw in robust_map:
        return robust_map[raw]

    print(f"[警告] 识别器输出了无法解析的 Rank: '{raw}', ID: {card.card_id}")
    return 8


ICON_TEMPLATES = {
    "START_BET": [
        resource_path("templates", "icons", "en", "start_en.png"),
        resource_path("templates", "icons", "ja", "start_ja.png"),
        resource_path("templates", "icons", "zh", "start_zh.png"),
        resource_path("templates", "icons", "tw", "start_tw.png"),
    ],
    "HOLD_CARDS": [resource_path("templates", "icons", "tpl_replace.png")],
    "TAP_TO_PROCEED": [
        resource_path("templates", "icons", "en", "proceed_en.png"),
        resource_path("templates", "icons", "ja", "proceed_ja.png"),
        resource_path("templates", "icons", "zh", "proceed_zh.png"),
        resource_path("templates", "icons", "tw", "proceed_tw.png"),
    ],
    "HIGH_LOW": [resource_path("templates", "icons", "tpl_high.png")],
    "RESULT": [
        resource_path("templates", "icons", "en", "result_en.png"),
        resource_path("templates", "icons", "ja", "result_ja.png"),
        resource_path("templates", "icons", "zh", "result_zh.png"),
        resource_path("templates", "icons", "tw", "result_tw.png"),
    ],
    "FAIL": [
        resource_path("templates", "icons", "en", "fail_en.png"),
        resource_path("templates", "icons", "en", "toobad_en.png"),
        resource_path("templates", "icons", "ja", "fail_ja.png"),
        resource_path("templates", "icons", "ja", "toobad_ja.png"),
        resource_path("templates", "icons", "zh", "fail_zh.png"),
        resource_path("templates", "icons", "zh", "toobad_zh.png"),
        resource_path("templates", "icons", "tw", "fail_tw.png"),
        resource_path("templates", "icons", "tw", "toobad_tw.png"),
    ],
    "ASK_CHALLENGE": [
        resource_path("templates", "icons", "en", "chance_en.png"),
        resource_path("templates", "icons", "en", "success_en.png"),
        resource_path("templates", "icons", "ja", "chance_ja.png"),
        resource_path("templates", "icons", "ja", "success_ja.png"),
        resource_path("templates", "icons", "zh", "chance_zh.png"),
        resource_path("templates", "icons", "zh", "success_zh.png"),
        resource_path("templates", "icons", "tw", "chance_tw.png"),
        resource_path("templates", "icons", "tw", "success_tw.png"),
    ],
    "FULL": [
        resource_path("templates", "icons", "en", "full_en.png"),
        resource_path("templates", "icons", "ja", "full_ja.png"),
        resource_path("templates", "icons", "zh", "full_zh.png"),
        resource_path("templates", "icons", "tw", "full_tw.png"),
    ],
}

TPL_REPLACE = resource_path("templates", "icons", "tpl_replace.png")
TPL_HIGH = resource_path("templates", "icons", "tpl_high.png")
TPL_LOW = resource_path("templates", "icons", "tpl_low.png")
TPL_CHECK = resource_path("templates", "icons", "tpl_check.png")
TPL_CROSS = resource_path("templates", "icons", "tpl_cross.png")


# ================= 1. 核心算法：高低记牌器 =================
class HighLowCounter:
    def __init__(self):
        self.deck = {i: 4 for i in range(2, 15)}

    def reset(self):
        self.deck = {i: 4 for i in range(2, 15)}

    def remove_cards(self, cards_list):
        for card_val in cards_list:
            if self.deck.get(card_val, 0) > 0:
                self.deck[card_val] -= 1

    def get_best_choice_and_rate(self, current_card):
        high_count = sum(count for val, count in self.deck.items() if val > current_card)
        low_count = sum(count for val, count in self.deck.items() if val < current_card)

        total_valid_cards = high_count + low_count
        if total_valid_cards == 0:
            return "high", 0.5

        high_rate = high_count / total_valid_cards
        low_rate = low_count / total_valid_cards

        if high_rate >= low_rate:
            return "high", high_rate
        else:
            return "low", low_rate


# ================= 2. 视觉识别与控制 =================
def find_game_window():
    """Return the real game window using an exact title match.

    ``getWindowsWithTitle`` performs a substring search.  A browser tab or
    Explorer window containing the repository name therefore used to win the
    race and get captured instead of the game.  Compare every returned window
    title exactly and prefer the largest exact match.
    """
    expected = GAME_TITLE.casefold().strip()
    matches = [
        win for win in gw.getAllWindows()
        if win.title.casefold().strip() == expected and getattr(win, "_hWnd", None)
    ]
    if not matches:
        return None
    return max(matches, key=lambda win: max(0, win.width) * max(0, win.height))


def _get_client_geometry(hwnd):
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    if not _user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError()
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def _capture_client_with_printwindow(hwnd, width, height):
    """Capture a client area even when another window covers the game."""
    window_dc = _user32.GetDC(hwnd)
    memory_dc = bitmap = old_bitmap = None
    try:
        if not window_dc:
            raise ctypes.WinError()
        memory_dc = _gdi32.CreateCompatibleDC(window_dc)
        bitmap = _gdi32.CreateCompatibleBitmap(window_dc, width, height)
        if not memory_dc or not bitmap:
            raise ctypes.WinError()
        old_bitmap = _gdi32.SelectObject(memory_dc, bitmap)

        # PW_CLIENTONLY | PW_RENDERFULLCONTENT. This works for the game's
        # Chromium/DirectX-backed window and avoids desktop occlusion.
        if not _user32.PrintWindow(hwnd, memory_dc, 0x00000001 | 0x00000002):
            raise RuntimeError("PrintWindow failed")

        byte_count = width * height * 4
        buffer = ctypes.create_string_buffer(byte_count)
        if _gdi32.GetBitmapBits(bitmap, byte_count, buffer) != byte_count:
            raise RuntimeError("GetBitmapBits returned an incomplete frame")
        frame = np.frombuffer(buffer, dtype=np.uint8).reshape(height, width, 4)
        frame = frame[:, :, :3].copy()  # BGRA -> BGR by dropping alpha.
        if frame.size == 0 or float(frame.mean()) < 1.0:
            raise RuntimeError("PrintWindow returned a blank frame")
        return frame
    finally:
        if old_bitmap and memory_dc:
            _gdi32.SelectObject(memory_dc, old_bitmap)
        if bitmap:
            _gdi32.DeleteObject(bitmap)
        if memory_dc:
            _gdi32.DeleteDC(memory_dc)
        if window_dc:
            _user32.ReleaseDC(hwnd, window_dc)


def capture_game_window():
    global _capture_context
    win = find_game_window()
    if win is None:
        _capture_context = None
        return None, 0, 0

    if win.isMinimized:
        win.restore()
        time.sleep(0.5)

    hwnd = win._hWnd
    try:
        left, top, width, height = _get_client_geometry(hwnd)
        if width < 640 or height < 360:
            raise RuntimeError(f"游戏客户区尺寸异常: {width}x{height}")
        img = _capture_client_with_printwindow(hwnd, width, height)
    except Exception as exc:
        # Fallback for Windows versions/drivers where PrintWindow is disabled.
        # Bring the exact game window forward before using a desktop capture.
        print(f"[警告] 后台窗口截图失败，切换到前台截图: {exc}")
        _bring_game_to_front(hwnd)
        time.sleep(0.2)
        left, top, width, height = _get_client_geometry(hwnd)
        monitor = {"top": top, "left": left, "width": width, "height": height}
        with mss.MSS() as sct:
            img = cv2.cvtColor(np.array(sct.grab(monitor)), cv2.COLOR_BGRA2BGR)

    _capture_context = {
        "hwnd": hwnd,
        "width": width,
        "height": height,
    }
    normalized = cv2.resize(img, (REFERENCE_WIDTH, REFERENCE_HEIGHT), interpolation=cv2.INTER_CUBIC)
    return normalized, left, top


def _bring_game_to_front(hwnd):
    if not hwnd or not _user32.IsWindow(hwnd):
        return False
    _user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
    _user32.BringWindowToTop(hwnd)
    _user32.SetForegroundWindow(hwnd)
    # A short topmost -> non-topmost transition also handles windows that were
    # visually above the foreground window on multi-monitor setups.
    flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW
    _user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, flags)
    _user32.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, flags)
    return True


def _deepest_window_at_client_point(hwnd, client_x, client_y):
    """Return the deepest visible child and coordinates local to that child."""
    screen_point = wintypes.POINT(client_x, client_y)
    if not _user32.ClientToScreen(hwnd, ctypes.byref(screen_point)):
        raise ctypes.WinError()

    target = hwnd
    skip_flags = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT
    while True:
        local_point = wintypes.POINT(screen_point.x, screen_point.y)
        if not _user32.ScreenToClient(target, ctypes.byref(local_point)):
            raise ctypes.WinError()
        child = _user32.ChildWindowFromPointEx(target, local_point, skip_flags)
        if not child or child == target:
            return target, local_point.x, local_point.y
        target = child


def _mouse_lparam(x, y):
    """Pack signed client coordinates into a Win32 mouse-message LPARAM."""
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


def safe_click(rel_x, rel_y, win_left=None, win_top=None):
    """Click the game in the background without touching the real cursor.

    Coordinates use the normalized 1920x1080 recognition space.  The legacy
    window-origin arguments remain accepted for existing call sites.
    """
    if not bot_running:
        return False
    if not _capture_context:
        print("[警告] 尚未取得有效游戏窗口，取消点击。")
        return False

    hwnd = _capture_context["hwnd"]
    if not hwnd or not _user32.IsWindow(hwnd):
        print("[警告] 游戏窗口已失效，取消点击。")
        return False

    # PostMessage uses client coordinates, so the game can stay covered and the
    # cursor position and physical button state remain unchanged.
    try:
        _, _, client_width, client_height = _get_client_geometry(hwnd)
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError(f"游戏客户区尺寸异常: {client_width}x{client_height}")
    except Exception as exc:
        print(f"[警告] 无法读取游戏窗口客户区，取消点击: {exc}")
        return False

    offset_x = random.randint(-4, 4)
    offset_y = random.randint(-4, 4)

    client_x = round(rel_x * client_width / REFERENCE_WIDTH) + offset_x
    client_y = round(rel_y * client_height / REFERENCE_HEIGHT) + offset_y
    client_x = max(0, min(client_width - 1, client_x))
    client_y = max(0, min(client_height - 1, client_y))

    try:
        target_hwnd, target_x, target_y = _deepest_window_at_client_point(hwnd, client_x, client_y)
        lparam = _mouse_lparam(target_x, target_y)
        if not _user32.PostMessageW(target_hwnd, WM_MOUSEMOVE, 0, lparam):
            raise ctypes.WinError()
        time.sleep(random.uniform(0.02, 0.05))
        if not _user32.PostMessageW(target_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam):
            raise ctypes.WinError()
        time.sleep(random.uniform(0.05, 0.08))
        if not _user32.PostMessageW(target_hwnd, WM_LBUTTONUP, 0, lparam):
            raise ctypes.WinError()
    except Exception as exc:
        print(f"[警告] 后台点击消息发送失败，未使用真实鼠标回退: {exc}")
        return False

    time.sleep(random.uniform(0.05, 0.1))
    return True


def find_and_click_icon(screen_bgr, tpl_path, win_left, win_top, threshold=0.80):
    tpl_path = os.fspath(tpl_path)
    if not os.path.exists(tpl_path):
        print(f"❌ 找不到图标文件: {tpl_path}")
        return False

    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tpl_img = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
    res = cv2.matchTemplate(screen_gray, tpl_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        h, w = tpl_img.shape
        if safe_click(max_loc[0] + w // 2, max_loc[1] + h // 2, win_left, win_top):
            print(f"👉 已发送后台点击: {os.path.basename(tpl_path)} (匹配度: {max_val:.2f} >= {threshold})")
            return True
        print(f"❌ 已匹配图标，但后台点击消息发送失败: {os.path.basename(tpl_path)}")
        return False
    else:
        print(f"⚠️ 放弃点击: {os.path.basename(tpl_path)} (当前匹配度仅 {max_val:.2f}，达不到 {threshold})")
        return False


def detect_game_state(screen_bgr):
    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    THRESHOLD = 0.85

    for state, tpl_paths in ICON_TEMPLATES.items():
        for tpl_path in tpl_paths:
            if not os.path.exists(tpl_path):
                continue
            tpl_img = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
            res = cv2.matchTemplate(screen_gray, tpl_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val >= THRESHOLD:
                return state
    return "UNKNOWN"


def find_all_card_rects(img, search_zone):
    sx, sy, sw, sh = search_zone
    roi = img[sy:sy + sh, sx:sx + sw]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # 提取所有纯白色区域（利用暗牌是紫黑色的特点主动忽略暗牌）
    white_mask = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))

    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # 尺寸过滤：只保留像卡牌那么大的白块
        if w > 100 and h > 150:
            rects.append((sx + x, sy + y, w, h))
    return rects


# ---------------------------------------------------------
# OCR 引擎 1：用于提取浅紫底色上的黄色数字 (加入强制纠偏机制)
# ---------------------------------------------------------
def read_screen_number(img, search_zone):
    sx, sy, sw, sh = search_zone
    if sw == 0 or sh == 0:
        return 0

    roi = img[sy:sy + sh, sx:sx + sw]

    # 1. 提取黄色区域
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_yellow = np.array([15, 50, 50])
    upper_yellow = np.array([45, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # 🚀 核心修复：在超大搜索框中自动捕捉黄色像素的真实边界（紧致裁切）
    points = cv2.findNonZero(yellow_mask)
    if points is None:
        return 0  # 画面中完全没有黄色元素

    x, y, w, h = cv2.boundingRect(points)

    # 过滤微小的噪点颗粒（至少要像个数字的宽高）
    if w < 10 or h < 10:
        return 0

    # 留 8 像素的外边距，避免贴边裁剪损伤字形
    pad = 8
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(yellow_mask.shape[1], x + w + pad)
    y2 = min(yellow_mask.shape[0], y + h + pad)

    cropped_mask = yellow_mask[y1:y2, x1:x2]

    # 2. 颜色反转（变为白底黑字）并放大到 OCR 最适宜的尺寸
    perfect_img = cv2.bitwise_not(cropped_mask)
    perfect_img = cv2.resize(perfect_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    _, img_bytes = cv2.imencode('.png', perfect_img)
    text = ocr.classification(img_bytes.tobytes())

    # 3. 强制字符纠偏
    text = text.upper()
    text = text.replace('O', '0').replace('Q', '0').replace('D', '0').replace('U', '0')
    text = text.replace('I', '1').replace('L', '1')
    text = text.replace('S', '5')
    text = text.replace('Z', '2')
    text = text.replace('B', '8')

    try:
        return int(''.join(filter(str.isdigit, text)))
    except ValueError:
        return 0

# ---------------------------------------------------------
# OCR 引擎 2：用于纯白底浅蓝字 (最终 RESULT 结算界面的 Coins)
# ---------------------------------------------------------
def read_result_number(img, search_zone):
    sx, sy, sw, sh = search_zone
    if sw == 0 or sh == 0:
        return 0

    roi = img[sy:sy + sh, sx:sx + sw]
    roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    _, img_bytes = cv2.imencode('.png', gray)
    text = ocr.classification(img_bytes.tobytes())

    try:
        return int(''.join(filter(str.isdigit, text)))
    except ValueError:
        return 0


# ================= 3. 数据与主循环 =================
def load_daily_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("date") == time.strftime("%Y-%m-%d"):
                    return data.get("coins", 0), data.get("fails", 0)
        except Exception:
            pass
    return 0, 0


def save_daily_data(coins, fails):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({"coins": coins, "fails": fails, "date": time.strftime("%Y-%m-%d")}, f)


def auto_play_loop(mode=None):
    """Shared recognition/execution loop; policy choice is the only A/B change."""
    global upcoming_card_val, bot_running
    session = StrategySession(APP_DIR, RESOURCE_DIR, mode)
    ledger = session.ledger
    counter = HighLowCounter()
    card_rec = CardRecognizer(TEMPLATE_DIR)
    reward_reader, result_reader = StableNumber(), StableNumber()
    seen_ids = set()
    round_active = False
    hold_done = False
    result_done = fail_done = False
    last_guess = None
    ask_clicked = None
    first_cash = last_cash = 0
    best_doubles = 0
    last_state = None
    state_since = time.monotonic()
    last_action = 0.0
    unknown_since = None
    last_decision_key = None
    decision = None

    def stats():
        d = ledger.data
        print(f"当日累计代币: {d['coins']} | 累计失败: {d['fails']} 次 | 今日净利润: {d['coins'] - d['fails'] * 50}")

    def observe(card):
        if card.card_id != JOKER_ID and card.card_id not in seen_ids:
            counter.remove_cards([get_real_card_value(card)])
            seen_ids.add(card.card_id)

    def trusted(card):
        return card.rank_score >= .55 and card.suit_score >= .62 and card.rank_margin >= .055

    def check_button(img, left, top):
        return find_and_click_icon(img, TPL_CHECK, left, top, threshold=.80)

    mode_descriptions = {
        TIME_TARGET_MODE: "时间优先动态决策；达标后持续翻倍至游戏上限",
        LEGACY_MODE: "旧版 60% 风控；达标后以在手 10,000 为止盈目标",
        ALL_IN_MODE: "极速梭哈；从第一轮起始终继续至本轮自然结束",
    }
    print(f"[策略] {session.mode} | {mode_descriptions[session.mode]}")
    print("[账目] 净利润栏沿用旧版失败门票估算；目标按已结算奖励计算。")
    stats()
    while bot_running and ledger.data['coins'] < DAILY_CAP:
        # Use the day of actual settlement. Reset at a configured LOCAL hour.
        if ledger.rollover():
            session.event('daily_reset', date=ledger.data['date'])
            stats()
        img, win_left, win_top = capture_game_window()
        if img is None:
            time.sleep(.5)
            continue
        state = detect_game_state(img)
        if state != last_state:
            state_since = time.monotonic()
            session.event('state', previous=last_state, state=state)
            if state != 'ASK_CHALLENGE':
                reward_reader.reset()
            if state != 'RESULT':
                result_reader.reset()
            last_state = state
        elif time.monotonic() - state_since > 45:
            print(f'[暂停] {state} 画面 45 秒未推进，请核对识别结果。')
            session.event('recognition_pause', reason='state_timeout', state=state)
            break
        if state == 'UNKNOWN':
            unknown_since = unknown_since or time.monotonic()
            if time.monotonic() - unknown_since > 30:
                print('[暂停] 画面连续 30 秒无法识别，请核对游戏状态。')
                session.event('recognition_pause', reason='unknown_state')
                break
            time.sleep(.2)
            continue
        unknown_since = None

        if state == 'FULL':
            print('[完成] 游戏显示每日上限/结束状态，停止挂机。')
            session.event('game_limit', coins=ledger.data['coins'])
            break

        if state == 'START_BET':
            if time.monotonic() - last_action < 2:
                time.sleep(.1)
                continue
            for tpl in ICON_TEMPLATES['START_BET']:
                if find_and_click_icon(img, tpl, win_left, win_top):
                    last_action = time.monotonic()
                    round_active = False
                    break
            time.sleep(.4)

        elif state == 'HOLD_CARDS':
            cards, rects = card_rec.recognize(img)
            if len(cards) != 5 or any(c.card_id != JOKER_ID and not trusted(c) for c in cards):
                time.sleep(.2)
                continue
            if not round_active:
                counter.reset()
                seen_ids.clear()
                upcoming_card_val = None
                result_done = fail_done = hold_done = False
                last_guess = ask_clicked = last_decision_key = None
                first_cash = last_cash = best_doubles = 0
                decision = None
                round_active = True
                ledger.data['rounds'] += 1
                ledger.save()
                session.event('round_start', round=ledger.data['rounds'])
            if not hold_done:
                for c in cards:
                    observe(c)
                best, _ = calculate_best([c.card_id for c in cards], 'standard')
                for idx in best.held_indices:
                    if not bot_running:
                        break
                    x, y, w, h = rects[idx]
                    if not safe_click(x+w//2, y+h//2, win_left, win_top):
                        raise RuntimeError('Hold click failed; pause to avoid toggling cards twice')
                    time.sleep(.10)
                hold_done = True
                session.event('hold', cards=[c.card_id for c in cards], held=list(best.held_indices))
            if time.monotonic() - last_action >= 1:
                if find_and_click_icon(img, TPL_REPLACE, win_left, win_top):
                    last_action = time.monotonic()
            time.sleep(.4)

        elif state == 'TAP_TO_PROCEED':
            # Account for replacement cards too, once per physical card ID.
            cards, _ = card_rec.recognize(img)
            for card in cards:
                if trusted(card):
                    observe(card)
            if time.monotonic() - last_action >= .7:
                h, w = img.shape[:2]
                safe_click(w//2, h//2, win_left, win_top)
                last_action = time.monotonic()
            time.sleep(.2)

        elif state == 'ASK_CHALLENGE':
            round_active = True
            next_reward = read_screen_number(img, REWARD_ZONE)
            if not reward_reader.accept(next_reward):
                time.sleep(.15)
                continue
            if next_reward % 2 or next_reward > 2**40:
                raise RuntimeError('Invalid reward OCR; please inspect the game')
            cash = next_reward // 2
            if first_cash == 0:
                first_cash = cash
            # Count only completed reward doublings, never attempted guesses.
            ratio = cash // first_cash if first_cash else 0
            if cash >= first_cash and cash % first_cash == 0 and ratio and ratio & (ratio-1) == 0:
                best_doubles = max(best_doubles, ratio.bit_length()-1)
            ledger.data['best_doubles'] = max(ledger.data['best_doubles'], best_doubles)
            last_cash = cash
            key = (ledger.data['coins'], cash, upcoming_card_val, tuple(counter.deck.values()))
            if key != last_decision_key:
                decision = session.decide(ledger.data['coins'], cash, counter.deck, upcoming_card_val)
                last_decision_key = key
                print(f"[决策 {session.mode}] 已入账 {ledger.data['coins']} | 在手 {cash} | 成功翻倍 {best_doubles} 次 | {decision.action}: {decision.reason}")
                if decision.cashout_seconds is not None and decision.challenge_seconds is not None:
                    print(f"[模型] 收手剩余约 {decision.cashout_seconds:.1f}s；挑战剩余约 {decision.challenge_seconds:.1f}s")
            if ask_clicked == key and time.monotonic() - last_action < 3:
                time.sleep(.15)
                continue
            if decision.action == 'cashout':
                clicked = find_and_click_icon(img, TPL_CROSS, win_left, win_top)
            elif decision.action == 'challenge':
                clicked = check_button(img, win_left, win_top)
            else:
                clicked = False
            if clicked:
                ask_clicked = key
                last_action = time.monotonic()
            time.sleep(.35)

        elif state == 'HIGH_LOW':
            round_active = True
            ask_clicked = None
            rects = find_all_card_rects(img, HIGH_LOW_SEARCH_ZONE)
            if not rects:
                time.sleep(.15)
                continue
            rects.sort(key=lambda r: r[0])
            rect = rects[-1]
            card = card_rec.recognize_card(img, rect)
            if card.card_id == JOKER_ID:
                print('[暂停] 翻倍阶段出现百搭王，其处理规则尚未确认。')
                session.event('recognition_pause', reason='high_low_joker')
                break
            if not trusted(card):
                time.sleep(.15)
                continue
            # Read every exposed card, including ties skipped by flip capture.
            for visible_rect in rects:
                visible = card_rec.recognize_card(img, visible_rect)
                if trusted(visible):
                    observe(visible)
            signature = (card.card_id, round(rect[0]/20), last_cash)
            if signature == last_guess:
                if time.monotonic() - last_action > 15:
                    print('[暂停] 同一猜牌画面未推进，避免重复点击/重复记牌。')
                    break
                time.sleep(.15)
                continue
            current = get_real_card_value(card)
            observe(card)
            choice, rate = counter.get_best_choice_and_rate(current)
            print(f"[猜牌] {card.rank}: {choice.upper()} | 排除同点后的胜率 {rate:.2%}")
            if not find_and_click_icon(img, TPL_HIGH if choice == 'high' else TPL_LOW, win_left, win_top):
                time.sleep(.2)
                continue
            last_guess = signature
            last_action = time.monotonic()
            session.event('guess', rank=current, choice=choice, conditional_win_rate=rate, cash=last_cash)
            upcoming_card_val = None
            previous_candidate = None
            # Require two agreeing frames; animation fragments are not cards.
            for _ in range(25):
                if not bot_running:
                    break
                time.sleep(.04)
                flip_img, _, _ = capture_game_window()
                if flip_img is None:
                    continue
                new_rects = find_all_card_rects(flip_img, HIGH_LOW_SEARCH_ZONE)
                if not new_rects:
                    continue
                newest = max(new_rects, key=lambda r: r[0])
                if newest[0] <= rect[0] + 50:
                    continue
                try:
                    revealed = card_rec.recognize_card(flip_img, newest)
                    if revealed.card_id == JOKER_ID or not trusted(revealed):
                        continue
                    if previous_candidate == revealed.card_id:
                        observe(revealed)
                        upcoming_card_val = get_real_card_value(revealed)
                        break
                    previous_candidate = revealed.card_id
                except (ValueError, RuntimeError):
                    continue
            if upcoming_card_val is None:
                print('[预判] 未确认下一张牌；新策略按未知牌分布估计。')
            time.sleep(.2)

        elif state == 'FAIL':
            if not fail_done:
                if round_active:
                    ledger.data['fails'] += 1
                    ledger.save()
                    session.event('round_fail', best_doubles=best_doubles)
                fail_done = True
                round_active = False
                stats()
            if time.monotonic() - last_action >= 1.5:
                if check_button(img, win_left, win_top):
                    last_action = time.monotonic()
            time.sleep(.3)

        elif state == 'RESULT':
            if not round_active and not result_done:
                # Starting on a settlement screen must not credit the old
                # executable's already-booked award a second time.
                print('[账目] 接管已有结算画面，跳过旧结算；可在停止后校正今日累计。')
                session.event('existing_settlement_skipped')
                result_done = True
            if not result_done:
                earned = read_result_number(img, RESULT_REWARD_ZONE)
                if not result_reader.accept(earned):
                    time.sleep(.2)
                    continue
                if earned > 2**40:
                    raise RuntimeError('Implausible settlement OCR')
                # A requested cashout must settle the amount used to decide.
                if decision is not None and decision.action == 'cashout' and last_cash and earned != last_cash:
                    raise RuntimeError(f'Settlement mismatch: expected {last_cash}, OCR {earned}; daily ledger unchanged')
                before = ledger.data['coins']
                ledger.data['coins'] += earned
                ledger.data['target_reached'] = ledger.data['coins'] >= TARGET
                ledger.save()
                session.event('settlement', earned=earned, coins=ledger.data['coins'], best_doubles=best_doubles)
                if before < TARGET <= ledger.data['coins']:
                    session.event('target_reached', coins=ledger.data['coins'], final_round_available=ledger.data['coins'] < DAILY_CAP)
                    print('[达标] 已结算奖励达到 19,800；后续解除止盈，挑战游戏最大翻倍次数。')
                result_done = True
                round_active = False
                stats()
            if time.monotonic() - last_action >= 1.5:
                if check_button(img, win_left, win_top):
                    last_action = time.monotonic()
            time.sleep(.3)
    ledger.save()
    session.event('session_end', coins=ledger.data['coins'], best_doubles=ledger.data['best_doubles'])
    bot_running = False


if __name__ == '__main__':
    bot_running = True
    auto_play_loop()
