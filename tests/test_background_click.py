import ctypes
import unittest
from ctypes import wintypes
from unittest.mock import patch

import auto_bot


_user32 = ctypes.windll.user32
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.PeekMessageW.restype = wintypes.BOOL


class BackgroundClickTests(unittest.TestCase):
    def test_mouse_lparam_packs_client_coordinates(self):
        self.assertEqual(auto_bot._mouse_lparam(0x1234, 0x5678), 0x56781234)

    def test_click_posts_to_window_without_moving_cursor(self):
        hwnd = _user32.CreateWindowExW(
            0, "STATIC", "background-click-test", 0, 50, 50, 320, 180,
            None, None, None, None,
        )
        self.assertTrue(hwnd)
        self.addCleanup(_user32.DestroyWindow, hwnd)

        before = wintypes.POINT()
        after = wintypes.POINT()
        cursor_available = bool(_user32.GetCursorPos(ctypes.byref(before)))

        auto_bot._capture_context = {
            "hwnd": hwnd,
            "width": 320,
            "height": 180,
        }
        with (
            patch.object(auto_bot, "bot_running", True),
            patch.object(auto_bot.random, "randint", return_value=0),
            patch.object(auto_bot.time, "sleep", return_value=None),
        ):
            self.assertTrue(auto_bot.safe_click(960, 540))

        received = []
        message = wintypes.MSG()
        while _user32.PeekMessageW(
            ctypes.byref(message), hwnd,
            auto_bot.WM_MOUSEMOVE, auto_bot.WM_LBUTTONUP, 0x0001,
        ):
            received.append(message.message)

        self.assertEqual(
            received,
            [auto_bot.WM_MOUSEMOVE, auto_bot.WM_LBUTTONDOWN, auto_bot.WM_LBUTTONUP],
        )
        if cursor_available:
            self.assertTrue(_user32.GetCursorPos(ctypes.byref(after)))
            self.assertEqual((before.x, before.y), (after.x, after.y))


if __name__ == "__main__":
    unittest.main()
