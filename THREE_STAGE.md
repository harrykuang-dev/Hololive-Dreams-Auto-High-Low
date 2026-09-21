# 三阶段翻倍策略 / 三階段翻倍策略 / Three-stage doubling strategy

[简体中文](#zh-cn) | [繁體中文](#zh-tw) | [English](#en)

<a id="zh-cn"></a>

## 简体中文

在策略选单选择「三阶段：最大 → 计次 → 最大」。原版仍为默认选项。

- 第一、第三阶段：持续挑战直到游戏自动结算，不设置 12,800 等软件止盈金额。
- 第二阶段：只在本局开始时确认一次起手奖励，确定目标成功次数，随后不再根据当前奖金判断翻倍。
- 只有点击猜高／低后出现成功询问，才增加一次成功；平手、重复画面、点击重试不增加次数。游戏达到上限直接结算时，最后一次成功也只计算一次。
- 失败后成功次数归零，重试同一阶段；确认结算入账后才推进阶段，不再比较结算金额是否达到旧目标。

| 起手奖励 | 第二阶段成功次数 | 对应奖金 |
|---|---:|---:|
| 200 | 5 | 6,400 |
| 400 | 4 | 6,400 |
| 700 | 3 | 5,600 |
| 800 | 3 | 6,400 |
| 1,500 | 2 | 6,000 |
| 3,000 | 1 | 6,000 |
| 7,000 / 10,000 | 0 | 7,000 / 10,000 |

第二阶段会在起手时排除入账后累计达到 20,000 的次数选项，以保留第三阶段；因此已有收益较高时，次数可能低于表中数值。若立即收手也会跨上限，则停止等待手动处理。第一阶段若被游戏提前结束当日游玩，程序无法绕过每日限制。

结算时以起手奖励及成功次数核对金额，不允许缺位数字造成错误入账。三阶段进度与金币保存在 `daily_coins.json`，当日重开保留，下一日期重置。中途重新启动而缺少本局计数时，停止提示从新一局开始，不猜测已成功次数。第三阶段成功后停止。此前已写入的错误账目需人工核对，更新不会自动推算历史收益。

<a id="zh-tw"></a>

## 繁體中文

在策略選單選擇「三階段：最大 → 計次 → 最大」。原版仍為預設選項。

- 第一、第三階段：持續挑戰直到遊戲自動結算，不設定 12,800 等軟體止盈金額。
- 第二階段：只在本局開始時確認一次起手獎勵，確定目標成功次數，之後不再根據當前獎金判斷翻倍。
- 只有點擊猜高／低後出現成功詢問，才增加一次成功；平手、重複畫面、點擊重試不增加次數。遊戲達到上限直接結算時，最後一次成功也只計算一次。
- 失敗後成功次數歸零，重試同一階段；確認結算入帳後才前進，不再比較結算金額是否達到舊目標。

| 起手獎勵 | 第二階段成功次數 | 對應獎金 |
|---|---:|---:|
| 200 | 5 | 6,400 |
| 400 | 4 | 6,400 |
| 700 | 3 | 5,600 |
| 800 | 3 | 6,400 |
| 1,500 | 2 | 6,000 |
| 3,000 | 1 | 6,000 |
| 7,000 / 10,000 | 0 | 7,000 / 10,000 |

第二階段會在起手時排除入帳後累計達到 20,000 的次數選項，以保留第三階段；因此已有收益較高時，次數可能低於表中數值。若立即收手也會跨上限，則停止等待手動處理。第一階段若被遊戲提前結束當日遊玩，程式無法繞過每日限制。

結算時以起手獎勵及成功次數核對金額，不允許缺位數字造成錯誤入帳。三階段進度與金幣保存在 `daily_coins.json`，當日重開保留，下一日期重置。中途重新啟動而缺少本局計數時，停止提示從新一局開始，不猜測已成功次數。第三階段成功後停止。此前已寫入的錯誤帳目需人工核對，更新不會自動推算歷史收益。

<a id="en"></a>

## English

Select “3 stages: Max → Win count → Max”. Legacy remains the default.

- Stages one and three keep challenging until the game settles automatically. There is no software cashout target such as 12,800.
- Stage two confirms the initial payout once and sets a win-count target. Ongoing reward readings do not decide whether to double.
- A successful High/Low click followed by a success prompt counts once. Ties, repeated frames, and click retries do not add wins. A final win leading directly to settlement also counts once.
- A loss resets the round’s count but keeps the stage. A confirmed successful settlement advances the stage without comparing the payout against the old target.

| Initial payout | Stage-two wins | Payout |
|---|---:|---:|
| 200 | 5 | 6,400 |
| 400 | 4 | 6,400 |
| 700 | 3 | 5,600 |
| 800 | 3 | 6,400 |
| 1,500 | 2 | 6,000 |
| 3,000 | 1 | 6,000 |
| 7,000 / 10,000 | 0 | 7,000 / 10,000 |

At the start of stage two, exclude win counts that would bring the daily total to 20,000 or more, preserving stage three. Existing earnings may therefore reduce the target count. If even an immediate cashout would cross the cap, stop for manual handling. The bot cannot override a daily limit imposed by the game during stage one.

Settlement amounts are checked against the initial payout and confirmed wins to prevent missing digits from corrupting the ledger. Stage progress and coins are saved in `daily_coins.json`, preserved on same-day restarts and reset on a new date. Restarting mid-round without its count stops the bot and asks for a fresh round rather than guessing progress. Stop after stage three. Previously incorrect ledger entries require manual review; updating does not reconstruct historical earnings.
