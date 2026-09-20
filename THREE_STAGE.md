# 三阶段翻倍策略 / 三階段翻倍策略 / Three-stage doubling strategy

[简体中文](#zh-cn) | [繁體中文](#zh-tw) | [English](#en)

<a id="zh-cn"></a>

## 简体中文

在界面策略选单选择「三阶段：12,800 → 6,400 → 12,800」。默认仍为 1.0.1 原版，可在停止挂机时切换。

### 收手规则

每局持续挑战，不因胜率低而提前收手；猜高／低方向仍沿用原版记牌判断。按三次成功入账依次追求 12,800、6,400、12,800，每次目标是本局奖金，不是每日累计。

目标取本局奖金倍数序列中最接近指定值的金额；差距相同时取较低金额。

| 本局起手奖金 | 第一次／第三次目标 | 第二次目标 |
|---|---:|---:|
| 200、400、800 | 12,800 | 6,400 |
| 1,500、3,000 | 12,000 | 6,000 |
| 700 | 11,200 | 5,600 |
| 7,000 | 14,000 | 7,000 |
| 10,000 | 10,000 | 10,000 |

前两阶段会排除本次入账后累计达到或超过 20,000 的候选，以保留后续游玩机会。例如先入账 14,000，第二阶段 700 起手选择 5,600；若 7,000 起手连立即收手都会跨过上限，程序停止，交由用户处理。已有当日收益时也应用此规则，实际目标可能低于表列值；日志会显示本局目标。

失败不推进阶段，下一局重新选择该阶段的可达目标。只有结算金额稳定确认、与收手金额相符并写入账目后才进入下一阶段。游戏强制提前结算且未达本局目标时，收益照常入账，但保持同一阶段。

第三阶段成功后停止挂机。进度与金币一起保存在程序旁的 `daily_coins.json`，当日重开仍保留，日期更换后重新开始。旧账目没有阶段字段时从第一阶段开始，不根据累计金币猜测已完成次数。切回原版不会删除三阶段进度。

<a id="zh-tw"></a>

## 繁體中文

在介面策略選單選擇「三階段：12,800 → 6,400 → 12,800」。預設仍為 1.0.1 原版，可在停止掛機時切換。

### 收手規則

每局持續挑戰，不因勝率低而提前收手；猜高／低方向仍沿用原版記牌判斷。按三次成功入帳依序追求 12,800、6,400、12,800，每次目標是本局獎金，不是每日累計。

目標取本局獎金倍數序列中最接近指定值的金額；差距相同時取較低金額。例如：

| 本局起手獎金 | 第一次／第三次目標 | 第二次目標 |
|---|---:|---:|
| 200、400、800 | 12,800 | 6,400 |
| 1,500、3,000 | 12,000 | 6,000 |
| 700 | 11,200 | 5,600 |
| 7,000 | 14,000 | 7,000 |
| 10,000 | 10,000 | 10,000 |

前兩階段還會排除「本次入帳後累計達到或超過 20,000」的候選，以保留後續遊玩機會。例如先入帳 14,000，第二階段 700 起手選 5,600；若 7,000 起手連立即收手都跨上限，程式停止讓使用者處理，不假裝還能完成三階段。已有當日收益時也套用此規則，實際目標可能低於表列值；日誌會顯示本局採用目標。

失敗不推進階段，下一局重新選取該階段可達目標。達到目標也不立即前進：只有結算金額穩定確認、與收手金額相符並寫入帳目後才進到下一階段。遊戲強制提早結算且不足本局目標時，收益照常入帳，但留在同一階段。

第三階段成功後停止掛機。三階段進度與金幣一起保存在程式旁的 `daily_coins.json`，當日重開程式仍保留；日期更換後重新開始。舊帳目沒有階段欄位時從第一階段開始，不根據累計金幣猜測已完成幾次。切回原版不會刪除三階段進度。

<a id="en"></a>

## English

Choose “3 stages: 12,800 → 6,400 → 12,800” in the strategy dropdown while the bot is stopped. Legacy 1.0.1 remains the default.

### Cashout rules

Keep doubling without an early cashout for unfavorable odds. High/Low direction selection still uses the original card-counting logic. The three successful cashouts target 12,800, 6,400, and 12,800 in order. Each target refers to the current round’s payout, not the daily total.

Choose the closest amount reachable by doubling the current payout. If two amounts are equally close, choose the lower one.

| Starting payout | First / third target | Second target |
|---|---:|---:|
| 200, 400, 800 | 12,800 | 6,400 |
| 1,500, 3,000 | 12,000 | 6,000 |
| 700 | 11,200 | 5,600 |
| 7,000 | 14,000 | 7,000 |
| 10,000 | 10,000 | 10,000 |

The first two stages exclude cashouts that would bring the daily total to 20,000 or more, preserving another round. For example, after banking 14,000, a second-stage hand starting at 700 targets 5,600. If a hand starts at 7,000 and even an immediate cashout would cross the cap, the bot stops for manual handling. Existing daily earnings count toward this check, so the actual target may be lower than the table shows. The log displays the selected target.

A loss does not advance the stage. The next round selects a reachable target for the same stage. Advance only after the settlement amount is confirmed, matches the requested cashout, and is saved. If the game forces an early settlement below the round’s target, record the earnings but remain in the same stage.

The bot stops after the third successful stage. Progress and coins are stored together in `daily_coins.json` next to the application. Restarting on the same day preserves progress; a new date resets it. An older ledger without a stage field starts at stage one: the bot does not infer past stages from total coins. Switching to Legacy does not erase three-stage progress.
