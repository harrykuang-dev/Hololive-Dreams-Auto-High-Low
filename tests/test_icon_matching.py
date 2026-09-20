import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import auto_bot as bot
from icon_matching import load_icon, frame_gray, match_icon


class IconMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(load_icon.cache_clear)
        self.folder = Path(self.temp.name)/'測試版_日本語_🎮'
        self.folder.mkdir()
        self.path = self.folder/'確認按鈕.png'
        self.template = np.random.default_rng(12).integers(0,256,(20,30),dtype=np.uint8)
        self.path.write_bytes(cv2.imencode('.png',self.template)[1].tobytes())
        self.frame = np.zeros((100,120),dtype=np.uint8)
        self.frame[40:60,50:80] = self.template

    def test_unicode_directory_loads_and_matches(self):
        np.testing.assert_array_equal(load_icon(str(self.path)), self.template)
        score, location, shape = match_icon(self.frame,self.path)
        self.assertGreater(score,.99)
        self.assertEqual(location,(50,40))
        self.assertEqual(shape,(20,30))

    def test_state_and_button_detection_use_unicode_loader(self):
        bgr=cv2.cvtColor(self.frame,cv2.COLOR_GRAY2BGR)
        with patch.object(bot,'ICON_TEMPLATES',{'ASK_CHALLENGE':[str(self.path)]}):
            self.assertEqual(bot.detect_game_state(bgr),'ASK_CHALLENGE')
        with patch.object(bot,'safe_click',return_value=True) as click:
            self.assertTrue(bot.find_and_click_icon(bgr,self.path,10,20))
            click.assert_called_once_with(65,50,10,20)

    def test_small_frame_never_calls_opencv_matching(self):
        with patch('icon_matching.cv2.matchTemplate',side_effect=AssertionError('must not match')):
            self.assertIsNone(match_icon(np.zeros((10,40),np.uint8),self.path))
            self.assertIsNone(match_icon(np.zeros((30,10),np.uint8),self.path))

    def test_empty_frame_is_unknown_and_does_not_click(self):
        for frame in (None,np.empty((0,0,3),np.uint8)):
            self.assertIsNone(frame_gray(frame))
            self.assertEqual(bot.detect_game_state(frame),'UNKNOWN')
            with patch.object(bot,'safe_click') as click:
                self.assertFalse(bot.find_and_click_icon(frame,self.path,0,0))
                click.assert_not_called()

    def test_bad_assets_report_path_instead_of_opencv_assertion(self):
        for name, data in [('empty.png',b''),('broken.png',b'not a png')]:
            path=self.folder/name
            path.write_bytes(data)
            with self.assertRaisesRegex(RuntimeError,name):
                load_icon(str(path))
        with self.assertRaisesRegex(RuntimeError,'missing.png'):
            load_icon(str(self.folder/'missing.png'))

    def test_all_shipped_icons_decode_and_fit_normalized_frame(self):
        root=Path(bot.TEMPLATE_DIR)/'icons'
        paths=list(root.rglob('*.png'))
        self.assertTrue(paths)
        for path in paths:
            image=load_icon(str(path))
            self.assertLessEqual(image.shape[0],bot.REFERENCE_HEIGHT,path)
            self.assertLessEqual(image.shape[1],bot.REFERENCE_WIDTH,path)


if __name__=='__main__':
    unittest.main()
