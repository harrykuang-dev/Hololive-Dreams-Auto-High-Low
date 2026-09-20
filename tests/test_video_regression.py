"""Offline real-video replay. All mouse input and accounting writes are mocked."""
import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import auto_bot as bot
from reward_vision import read_challenge_number
from challenge_strategy import ChallengeStrategy

FIXTURES = Path(__file__).parent/'fixtures'


class VideoRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (FIXTURES/'ask_800.png').exists():
            raise unittest.SkipTest('Private video fixtures are not distributed; see VIDEO_REWORK.md')
        cls.strategy = ChallengeStrategy()

    def test_blocked_video_rewards(self):
        for name, expected in [('ask_800.png',800),('ask_1600.png',1600),('ask_3200.png',3200)]:
            frame = cv2.imread(str(FIXTURES/name))
            self.assertEqual(bot.detect_game_state(frame), 'ASK_CHALLENGE')
            self.assertEqual(read_challenge_number(frame, bot.REWARD_ZONE, bot.ocr), expected)

    def test_old_crop_reproduces_the_reward_bug(self):
        frame=cv2.imread(str(FIXTURES/'ask_800.png'))
        self.assertNotEqual(bot.read_screen_number(frame,bot.REWARD_ZONE),800)

    def run_frames(self, frames, mode, coins=0):
        frames = iter(frames)
        clicks = []
        clock = [0.0]
        original_click = bot.find_and_click_icon
        def capture():
            clock[0] += .25
            try:
                return next(frames), 0, 0
            except StopIteration:
                bot.bot_running = False
                return None, 0, 0
        def click(img, path, left, top, threshold=.8):
            matched = original_click(img, path, left, top, threshold)
            if matched:
                clicks.append((Path(path).name, threshold))
            return matched
        self.strategy.reset_reading()
        with patch.object(bot,'capture_game_window',side_effect=capture), \
             patch.object(bot,'find_and_click_icon',side_effect=click), \
             patch.object(bot,'safe_click',return_value=True), \
             patch.object(bot,'load_daily_data',return_value=(coins,0)), \
             patch.object(bot,'save_daily_data'), \
             patch.object(bot,'ChallengeStrategy',return_value=self.strategy), \
             patch.object(bot.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(bot.time,'sleep'), contextlib.redirect_stdout(io.StringIO()):
            bot.bot_running = True
            bot.upcoming_card_val = None
            bot.auto_play_loop(mode)
        return clicks

    def test_both_modes_act_on_formerly_blocked_prompt(self):
        frame=cv2.imread(str(FIXTURES/'ask_800.png'))
        for mode in ('legacy','time_target'):
            actions=self.run_frames([frame],mode)
            self.assertEqual(len(actions),1)
            self.assertIn(actions[0][0],('tpl_check.png','tpl_cross.png'))
            if actions[0][0]=='tpl_check.png':
                self.assertEqual(actions[0][1],.55)

    def test_unreadable_prompt_does_not_stall(self):
        frame=cv2.imread(str(FIXTURES/'ask_800.png'))
        with patch.object(bot,'read_challenge_number',return_value=0):
            actions=self.run_frames([frame]*3,'time_target')
            self.assertEqual(actions,[('tpl_cross.png',.8)])
            actions=self.run_frames([frame]*3,'time_target',coins=19800)
            self.assertEqual(actions,[('tpl_check.png',.55)])

    def test_failure_and_settlement_still_continue(self):
        for name in ('fail.png','result.png'):
            for mode in ('legacy','time_target'):
                with patch.object(bot,'read_result_number',return_value=800):
                    frames=[cv2.imread(str(FIXTURES/name))]*(10 if name=='result.png' else 1)
                    actions=self.run_frames(frames,mode)
                self.assertIn(('tpl_check.png',.55),actions)

    def test_high_low_still_selects_a_direction(self):
        frame=cv2.imread(str(FIXTURES/'high_low.png'))
        self.assertEqual(bot.detect_game_state(frame),'HIGH_LOW')
        for mode in ('legacy','time_target'):
            actions=self.run_frames([frame],mode)
            self.assertTrue(any(name in ('tpl_high.png','tpl_low.png') for name,_ in actions))

    def test_bank_target_and_keep_sprinting(self):
        policy=self.strategy.policy
        deck={r:4 for r in range(2,15)}
        self.assertEqual(policy.decide(19600,200,deck).action,'cashout')
        self.assertEqual(policy.decide(19760,200,deck).action,'cashout')
        self.assertEqual(policy.decide(19000,700,deck).action,'cashout')
        self.assertEqual(policy.decide(19800,10000,deck).action,'challenge')
        self.assertEqual(policy.decide(19800,102400,deck).action,'challenge')

    def test_invalid_reward_retry_resets_on_readable_amount(self):
        self.strategy.reset_reading()
        deck={r:4 for r in range(2,15)}
        self.assertEqual(self.strategy.decide(0,9,deck,None).action,'wait')
        self.assertNotEqual(self.strategy.decide(0,800,deck,None).action,'wait')
        self.assertEqual(self.strategy.misses,0)

    def test_strategy_does_not_mutate_the_legacy_counter(self):
        deck={r:4 for r in range(2,15)}
        before=deck.copy()
        self.strategy.decide(0,800,deck,8)
        self.assertEqual(deck,before)


if __name__=='__main__':
    unittest.main()
