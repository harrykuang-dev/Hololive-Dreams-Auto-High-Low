"""Always double to a reachable target; advance only on confirmed settlement."""

TARGETS = (12800, 6400, 12800)


class PhasedStrategy:
    def __init__(self, stage=0):
        if type(stage) is not int or not 0 <= stage <= len(TARGETS):
            raise ValueError('Invalid saved strategy stage')
        self.stage = stage
        self.round_target = None

    @property
    def complete(self):
        return self.stage == len(TARGETS)

    def reset_round(self):
        self.round_target = None

    def decide(self, coins, cash):
        if self.complete:
            return 'stop'
        if cash <= 0:
            raise ValueError('Reward must be confirmed before deciding')
        if self.round_target is None:
            candidates = [cash * 2**n for n in range(32)]
            # Keep a following round available for the first two settlements.
            if self.stage < 2:
                candidates = [amount for amount in candidates if coins + amount < 20000]
            if not candidates:
                raise RuntimeError('当前奖金额已无法在每日上限内保留下一阶段，请手动处理本局。')
            self.round_target = min(candidates, key=lambda amount: (abs(amount - TARGETS[self.stage]), amount))
        return 'cashout' if cash >= self.round_target else 'challenge'

    def stage_after_credit(self, earned):
        if self.round_target is not None and earned >= self.round_target and not self.complete:
            return self.stage + 1
        return self.stage
