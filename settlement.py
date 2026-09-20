"""Confirm a finished result before crediting it, never a count-up frame."""
from high_low_strategy import PRIZES


def valid_payout(amount):
    return any(amount == prize * 2**n for prize in PRIZES[1:] for n in range(33))


class SettlementReader:
    def __init__(self, minimum_wait=1.5, stable_seconds=.6, timeout=8.0):
        self.minimum_wait = minimum_wait
        self.stable_seconds = stable_seconds
        self.timeout = timeout
        self.reset()

    def reset(self):
        self.started = None
        self.candidate = None
        self.since = None
        self.samples = 0

    def observe(self, amount, now, expected=None):
        if self.started is None:
            self.started = now
        if not valid_payout(amount) or (expected is not None and amount != expected):
            self.candidate = self.since = None
            self.samples = 0
        elif amount == self.candidate:
            self.samples += 1
        else:
            self.candidate = amount
            self.since = now
            self.samples = 1
        if (self.samples >= 3 and now-self.started >= self.minimum_wait
                and now-self.since >= self.stable_seconds):
            return self.candidate
        if now-self.started >= self.timeout:
            raise RuntimeError('结算金额未能确认，已停止且没有将此笔入账。'
                               '请核对结算画面与今日累计后再继续。')
        return None
