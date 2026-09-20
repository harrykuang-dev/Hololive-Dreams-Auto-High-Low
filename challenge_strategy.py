"""Small strategy adapter; deliberately leaves the 1.0.1 game loop intact."""
from high_low_strategy import Decision, PRIZES, TimePolicy

# Prior from 128 optimal-hand calculations; not live win-rate measurements.
PAYOUT_PRIOR = (0.684262297319869, 0.2399609395075291,
                0.022216631253854452, 0.023858288123779426,
                0.01454000081907186, 0.014584196570819188,
                0.0002749712521841916, 0.0002250841556172272,
                0.0000775909972761846)


def valid_reward(value):
    return any(value == prize * 2**n for prize in PRIZES[1:] for n in range(1, 33))


class ChallengeStrategy:
    def __init__(self, **timings):
        self.policy = TimePolicy(PAYOUT_PRIOR, **timings)
        self.misses = 0

    def reset_reading(self):
        self.misses = 0

    def decide(self, coins, next_reward, deck, rank):
        if not valid_reward(next_reward):
            self.misses += 1
            if self.misses < 3:
                return Decision('wait', 'retry_reward_ocr')
            # Never block both policies indefinitely or invent a 100 payout.
            # Once already in sprint, the amount is irrelevant to the action.
            return Decision('challenge' if coins >= 19800 else 'cashout',
                            'unreadable_reward_fallback')
        self.misses = 0
        remaining = dict(deck)
        # In the 1.0.1 loop the predicted card is not removed until HIGH_LOW.
        # The policy expects its current rank already excluded; do not mutate
        # the legacy counter and accidentally remove it twice.
        if rank in remaining and remaining[rank] > 0:
            remaining[rank] -= 1
        return self.policy.decide(coins, next_reward//2, remaining, rank)
