import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import auto_bot as bot
from challenge_reward import ChallengeRewardReader, valid_next_reward
from phased_strategy import PhasedStrategy
from settlement import SettlementReader


class StrategyTests(unittest.TestCase):
    def test_reachable_targets(self):
        for cash, first, second in [(200, 12800, 6400), (400, 12800, 6400),
                                    (1500, 12000, 6000), (3000, 12000, 6000),
                                    (700, 11200, 5600), (7000, 14000, 7000),
                                    (10000, 10000, 10000)]:
            for stage, expected in [(0, first), (1, second), (2, first)]:
                policy = PhasedStrategy(stage)
                policy.decide(0, cash)
                self.assertEqual(policy.round_target, expected)

    def test_failure_does_not_advance_and_credit_does(self):
        policy = PhasedStrategy()
        self.assertEqual(policy.decide(0, 200), 'challenge')
        self.assertEqual(policy.stage_after_credit(200), 0)
        policy.reset_round()  # A failed round starts over in the same stage.
        self.assertEqual(policy.stage, 0)
        self.assertEqual(policy.decide(0, 1500), 'challenge')
        self.assertEqual(policy.decide(0, 12000), 'cashout')
        self.assertEqual(policy.stage, 0)
        self.assertEqual(policy.stage_after_credit(12000), 1)

    def test_first_two_stages_preserve_next_round(self):
        policy = PhasedStrategy(1)
        policy.decide(14000, 700)
        self.assertEqual(policy.round_target, 5600)
        with self.assertRaises(RuntimeError):
            PhasedStrategy(1).decide(14000, 7000)
        final = PhasedStrategy(2)
        final.decide(19200, 200)
        self.assertEqual(final.round_target, 12800)

    def test_only_valid_stable_amounts_reach_strategy(self):
        for value in (0, 20, 80, 200, 8000, -400):
            self.assertFalse(valid_next_reward(value))
        reader = ChallengeRewardReader()
        self.assertIsNone(reader.observe(80, 0))
        self.assertIsNone(reader.observe(800, .3))
        self.assertEqual(reader.observe(800, .6), 800)
        reader.reset_prompt()
        self.assertIsNone(reader.observe(6400, 1))  # Impossible jump.
        self.assertIsNone(reader.observe(1600, 1.3))
        self.assertEqual(reader.observe(1600, 1.6), 1600)
        reader.reset_round()
        self.assertIsNone(reader.observe(400, 2))
        self.assertEqual(reader.observe(400, 2.3), 400)

    def test_invalid_ocr_times_out_without_inventing_reward(self):
        reader = ChallengeRewardReader()
        for i in range(8):
            self.assertIsNone(reader.observe(80, i))
        with self.assertRaises(RuntimeError):
            reader.observe(80, 8)

    def test_settlement_must_match_confirmed_cashout(self):
        reader = SettlementReader()
        for i in range(8):
            self.assertIsNone(reader.observe(400, i, expected=12800))
        with self.assertRaises(RuntimeError):
            reader.observe(400, 8, expected=12800)

    def test_ledger_stage_is_atomic_persistent_and_date_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'daily_coins.json'
            with patch.object(bot, 'DATA_FILE', path):
                bot.save_daily_data(12800, 3, 1)
                self.assertEqual(bot.load_daily_data(), (12800, 3))
                self.assertEqual(bot.load_daily_stage(), 1)
                bot.save_daily_data(12800, 4)  # Failure or legacy write.
                self.assertEqual(bot.load_daily_stage(), 1)
                self.assertFalse(path.with_suffix('.tmp').exists())
                data = json.loads(path.read_text())
                data['date'] = '2000-01-01'
                path.write_text(json.dumps(data))
                self.assertEqual(bot.load_daily_stage(), 0)

    def run_frames(self, frames, mode='phased', stage=0):
        frames = iter(frames)
        current = ['UNKNOWN', 0]
        clock = [0.0]
        writes, clicks = [], []
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)

        def capture():
            clock[0] += .3
            try:
                current[:] = next(frames)
                return image, 0, 0
            except StopIteration:
                bot.bot_running = False
                return None, 0, 0

        def click(img, tpl, *args, **kwargs):
            clicks.append((current[0], current[1], Path(tpl).name))
            return True

        with patch.object(bot, 'capture_game_window', side_effect=capture), \
             patch.object(bot, 'detect_game_state', side_effect=lambda _: current[0]), \
             patch.object(bot, 'CardRecognizer'), \
             patch.object(bot, 'read_screen_number', side_effect=lambda *a: current[1]), \
             patch.object(bot, 'read_result_number', side_effect=lambda *a: current[1]), \
             patch.object(bot, 'find_and_click_icon', side_effect=click), \
             patch.object(bot, 'load_daily_data', return_value=(0, 0)), \
             patch.object(bot, 'load_daily_stage', return_value=stage), \
             patch.object(bot, 'save_daily_data', side_effect=lambda *a: writes.append(a)), \
             patch.object(bot.time, 'sleep'), \
             patch.object(bot.time, 'monotonic', side_effect=lambda: clock[0]), \
             contextlib.redirect_stdout(io.StringIO()):
            bot.bot_running = True
            bot.upcoming_card_val = None
            try:
                bot.auto_play_loop(mode)
            finally:
                bot.bot_running = False
        return writes, clicks

    def test_full_three_stage_loop_and_failure_retry(self):
        frames = [('FAIL', 0), ('START_BET', 0)]
        for cashout in (12800, 6400, 12800):
            reward = 400
            while reward <= cashout * 2:
                frames.extend([('ASK_CHALLENGE', reward)] * 2)
                reward *= 2
            frames.extend([('RESULT', cashout)] * 12)
            frames.append(('UNKNOWN', 0))
            frames.append(('RESULT', cashout))  # Must not credit twice.
            frames.append(('START_BET', 0))
        writes, clicks = self.run_frames(frames)
        self.assertEqual(writes, [(0, 1), (12800, 1, 1), (19200, 1, 2), (32000, 1, 3)])
        self.assertEqual([reward for state, reward, tpl in clicks if tpl == 'tpl_cross.png'],
                         [25600, 12800, 25600])

    def test_invalid_reward_cannot_trigger_click_in_either_mode(self):
        for mode in ('legacy', 'phased'):
            writes, clicks = self.run_frames([('ASK_CHALLENGE', 80)] * 3, mode)
            self.assertEqual((writes, clicks), ([], []))

    def test_completed_stage_does_not_start_a_fourth_round(self):
        self.assertEqual(self.run_frames([('START_BET', 0)], stage=3), ([], []))


if __name__ == '__main__':
    unittest.main()
