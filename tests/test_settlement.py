import contextlib
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import cv2
import numpy as np
import auto_bot as bot
from high_low_strategy import Decision
from settlement import SettlementReader


class SettlementTests(unittest.TestCase):
    def test_animation_is_not_credited(self):
        reader=SettlementReader()
        for now, value in [(0,20),(.2,60),(.4,280),(.6,40),(.8,400),(1.,400),(1.2,400),(1.4,400)]:
            self.assertIsNone(reader.observe(value,now))
        self.assertEqual(reader.observe(400,1.6),400)

    def test_legal_intermediate_value_cannot_override_cashout(self):
        reader=SettlementReader()
        for i in range(12):
            self.assertIsNone(reader.observe(200,i*.2,expected=400))
        for i in range(4):
            result=reader.observe(400,3+i*.25,expected=400)
        self.assertEqual(result,400)

    def test_unreadable_or_conflicting_result_stops_without_assuming_income(self):
        for amount in (0,20,800):
            reader=SettlementReader()
            reader.observe(amount,0,expected=400)
            with self.assertRaisesRegex(RuntimeError,'没有将此笔入账'):
                reader.observe(amount,8.1,expected=400)

    def run_loop(self, rows, mode='legacy', real_frames=False):
        iterator=iter(rows)
        current=[0,None,None,None]
        def capture():
            try:
                current[:]=next(iterator)
                return current[1],0,0
            except StopIteration:
                bot.bot_running=False
                return None,0,0
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(bot,'capture_game_window',side_effect=capture))
            stack.enter_context(patch.object(bot.time,'monotonic',side_effect=lambda:current[0]))
            stack.enter_context(patch.object(bot.time,'sleep'))
            stack.enter_context(patch.object(bot,'load_daily_data',return_value=(360,0)))
            save=stack.enter_context(patch.object(bot,'save_daily_data'))
            stack.enter_context(patch.object(bot,'safe_click',return_value=True))
            stack.enter_context(patch.object(bot,'CardRecognizer'))
            stack.enter_context(patch.object(bot,'ChallengeStrategy',return_value=SimpleNamespace(
                reset_reading=lambda:None,decide=lambda *args:Decision('cashout','test'))))
            if not real_frames:
                stack.enter_context(patch.object(bot,'detect_game_state',side_effect=lambda img:current[2]))
                stack.enter_context(patch.object(bot,'read_result_number',side_effect=lambda *a:current[3]))
                stack.enter_context(patch.object(bot,'read_challenge_number',return_value=800))
                stack.enter_context(patch.object(bot,'find_and_click_icon',return_value=True))
            bot.bot_running=True
            bot.auto_play_loop(mode)
            return [call.args for call in save.call_args_list]

    def test_both_modes_credit_once_through_unknown_flicker_then_next_round(self):
        frame=np.zeros((100,100,3),np.uint8)
        rows=[(i*.2,frame,'RESULT',n) for i,n in enumerate([20,60,280,40,400,400,400,400,400])]
        rows += [(2.,frame,'UNKNOWN',0),(2.2,frame,'RESULT',400),(2.5,frame,'START_BET',0)]
        rows += [(3+i*.2,frame,'RESULT',200) for i in range(10)]
        for mode in ('legacy','time_target'):
            self.assertEqual(self.run_loop(rows,mode),[(760,0),(960,0)])

    def test_cashout_amount_is_checked_before_credit(self):
        frame=np.zeros((100,100,3),np.uint8)
        rows=[(0.,frame,'ASK_CHALLENGE',0)]
        rows += [(1+i*.2,frame,'RESULT',200) for i in range(10)]
        rows += [(4+i*.2,frame,'RESULT',400) for i in range(5)]
        self.assertEqual(self.run_loop(rows,'time_target'),[(760,0)])

    @unittest.skipUnless(os.environ.get('HOLOLIVE_TEST_VIDEO'), 'Set HOLOLIVE_TEST_VIDEO for private-video replay')
    def test_recorded_400_payout_credits_400_not_animation_frame(self):
        path=os.environ['HOLOLIVE_TEST_VIDEO']
        self.assertTrue(Path(path).is_file())
        cap=cv2.VideoCapture(path)
        rows=[]
        try:
            for i in range(14):
                t=337.8+i*.2
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000)
                ok,frame=cap.read()
                self.assertTrue(ok)
                frame=cv2.resize(frame[163:862,517:1759],(1920,1080),interpolation=cv2.INTER_CUBIC)
                rows.append((t,frame,None,None))
        finally:
            cap.release()
        self.assertNotEqual(bot.read_result_number(rows[0][1],bot.RESULT_REWARD_ZONE),400)
        for mode in ('legacy','time_target'):
            self.assertEqual(self.run_loop(rows,mode,real_frames=True),[(760,0)])


if __name__=='__main__':
    unittest.main()
