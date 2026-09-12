import pygetwindow as gw
import mss
import numpy as np
import cv2
import pydirectinput
import random
import time
import os
import json
import ddddocr

from recognizer import CardRecognizer
from poker_core import calculate_best, JOKER_ID

# 直接全局初始化 OCR 引擎
ocr = ddddocr.DdddOcr(show_ad=False)

bot_running = False
# ================= 全局配置与常量 =================
GAME_TITLE = "hololive"
TARGET_LIMIT = 19800
DATA_FILE = "daily_coins.json"

# === 动态寻框参数 ===
CARD_WIDTH = 260
# 超大搜索区，覆盖整个屏幕中段，彻底杜绝漏抓
HIGH_LOW_SEARCH_ZONE = (42, 358, 1256, 451)

# 💰 奖金黄字 OCR 识别区 (!!! 必须用 get_coords.py 重新量取你的黄色数字坐标 !!!)
REWARD_ZONE = (606, 389, 870, 253)

# 💰 结算蓝字 OCR 识别区 (已保留你量好的数据)
RESULT_REWARD_ZONE = (1044, 337, 450, 97)

upcoming_card_val = None


# === 真实点数映射表 ===
def get_real_card_value(card):
    if card.card_id == JOKER_ID:
        return 0

    raw = str(card.rank).upper().strip()
    if "." in raw:
        raw = raw.split(".")[-1]

    robust_map = {
        "2": 2, "TWO": 2,
        "3": 3, "THREE": 3,
        "4": 4, "FOUR": 4,
        "5": 5, "FIVE": 5,
        "6": 6, "SIX": 6,
        "7": 7, "SEVEN": 7,
        "8": 8, "EIGHT": 8,
        "9": 9, "NINE": 9,
        "10": 10, "TEN": 10,
        "11": 11, "J": 11, "JACK": 11,
        "12": 12, "Q": 12, "QUEEN": 12,
        "13": 13, "K": 13, "KING": 13,
        "14": 14, "A": 14, "ACE": 14, "1": 14
    }

    if raw in robust_map:
        return robust_map[raw]

    print(f"[警告] 识别器输出了无法解析的 Rank: '{raw}', ID: {card.card_id}")
    return 8


ICON_TEMPLATES = {
    "START_BET": [
        "templates/icons/en/start_en.png",
        "templates/icons/ja/start_ja.png",
        "templates/icons/zh/start_zh.png",
        "templates/icons/tw/start_tw.png",
        "templates/icons/tpl_start.png"
    ],
    "HOLD_CARDS": ["templates/icons/tpl_replace.png"],
    "TAP_TO_PROCEED": [
        "templates/icons/en/proceed_en.png",
        "templates/icons/ja/proceed_ja.png",
        "templates/icons/zh/proceed_zh.png",
        "templates/icons/tw/proceed_tw.png",
        "templates/icons/tpl_proceed.png"
    ],
    "HIGH_LOW": ["templates/icons/tpl_high.png"],
    "RESULT": [
        "templates/icons/en/result_en.png",
        "templates/icons/ja/result_ja.png",
        "templates/icons/zh/result_zh.png",
        "templates/icons/tw/result_tw.png",
        "templates/icons/tpl_result.png"
    ],
    "FAIL": [
        "templates/icons/en/fail_en.png",
        "templates/icons/en/toobad_en.png",
        "templates/icons/ja/fail_ja.png",
        "templates/icons/ja/toobad_ja.png",
        "templates/icons/zh/fail_zh.png",
        "templates/icons/zh/toobad_zh.png",
        "templates/icons/tw/fail_tw.png",
        "templates/icons/tw/toobad_tw.png"
    ],
    "ASK_CHALLENGE": [
        "templates/icons/en/chance_en.png",
        "templates/icons/en/success_en.png",
        "templates/icons/ja/chance_ja.png",
        "templates/icons/ja/success_ja.png",
        "templates/icons/zh/chance_zh.png",
        "templates/icons/zh/success_zh.png",
        "templates/icons/tw/chance_tw.png",
        "templates/icons/tw/success_tw.png"
    ],
    "FULL": [
        "templates/icons/en/full_en.png",
        "templates/icons/ja/full_ja.png",
        "templates/icons/zh/full_zh.png",
        "templates/icons/tw/full_tw.png",
        "templates/icons/tpl_full.png"
    ],
}


# ================= 1. 核心算法：高低记牌器 =================
class HighLowCounter:
    def __init__(self):
        self.deck = {i: 4 for i in range(2, 15)}

    def reset(self):
        self.deck = {i: 4 for i in range(2, 15)}

    def remove_cards(self, cards_list):
        for card_val in cards_list:
            if self.deck.get(card_val, 0) > 0:
                self.deck[card_val] -= 1

    def get_best_choice_and_rate(self, current_card):
        high_count = sum(count for val, count in self.deck.items() if val > current_card)
        low_count = sum(count for val, count in self.deck.items() if val < current_card)

        total_valid_cards = high_count + low_count
        if total_valid_cards == 0:
            return "high", 0.5

        high_rate = high_count / total_valid_cards
        low_rate = low_count / total_valid_cards

        if high_rate >= low_rate:
            return "high", high_rate
        else:
            return "low", low_rate


# ================= 2. 视觉识别与控制 =================
def capture_game_window():
    all_titles = gw.getAllTitles()
    target_title = None
    for title in all_titles:
        # 核心修改：将获取到的窗口名转为小写并去除首尾空格，进行严格全等判断
        if title.lower().strip() == "hololive-dreams":
            target_title = title
            break

    if not target_title:
        return None, 0, 0

    win = gw.getWindowsWithTitle(target_title)[0]
    if win.isMinimized:
        win.restore()
        time.sleep(0.5)

    monitor = {"top": win.top, "left": win.left, "width": win.width, "height": win.height}
    with mss.MSS() as sct:
        img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), win.left, win.top


def safe_click(rel_x, rel_y, win_left, win_top):
    offset_x = random.randint(-4, 4)
    offset_y = random.randint(-4, 4)

    target_x = win_left + rel_x + offset_x
    target_y = win_top + rel_y + offset_y

    pydirectinput.moveTo(target_x, target_y)
    time.sleep(random.uniform(0.02, 0.05))

    pydirectinput.mouseDown()
    time.sleep(random.uniform(0.05, 0.08))
    pydirectinput.mouseUp()

    time.sleep(random.uniform(0.05, 0.1))


def find_and_click_icon(screen_bgr, tpl_path, win_left, win_top, threshold=0.80):
    if not os.path.exists(tpl_path):
        print(f"❌ 找不到图标文件: {tpl_path}")
        return False

    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tpl_img = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
    res = cv2.matchTemplate(screen_gray, tpl_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        h, w = tpl_img.shape
        print(f"👉 成功触发点击: {os.path.basename(tpl_path)} (匹配度: {max_val:.2f} >= {threshold})")
        safe_click(max_loc[0] + w // 2, max_loc[1] + h // 2, win_left, win_top)
        return True
    else:
        print(f"⚠️ 放弃点击: {os.path.basename(tpl_path)} (当前匹配度仅 {max_val:.2f}，达不到 {threshold})")
        return False


def detect_game_state(screen_bgr):
    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    THRESHOLD = 0.85

    for state, tpl_paths in ICON_TEMPLATES.items():
        for tpl_path in tpl_paths:
            if not os.path.exists(tpl_path):
                continue
            tpl_img = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
            res = cv2.matchTemplate(screen_gray, tpl_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val >= THRESHOLD:
                return state
    return "UNKNOWN"


def find_all_card_rects(img, search_zone):
    sx, sy, sw, sh = search_zone
    roi = img[sy:sy + sh, sx:sx + sw]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # 提取所有纯白色区域（利用暗牌是紫黑色的特点主动忽略暗牌）
    white_mask = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))

    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # 尺寸过滤：只保留像卡牌那么大的白块
        if w > 100 and h > 150:
            rects.append((sx + x, sy + y, w, h))
    return rects


# ---------------------------------------------------------
# OCR 引擎 1：用于提取浅紫底色上的黄色数字 (加入强制纠偏机制)
# ---------------------------------------------------------
def read_screen_number(img, search_zone):
    sx, sy, sw, sh = search_zone
    if sw == 0 or sh == 0:
        return 0

    roi = img[sy:sy + sh, sx:sx + sw]

    # 1. 提取黄色区域
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_yellow = np.array([15, 50, 50])
    upper_yellow = np.array([45, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # 🚀 核心修复：在超大搜索框中自动捕捉黄色像素的真实边界（紧致裁切）
    points = cv2.findNonZero(yellow_mask)
    if points is None:
        return 0  # 画面中完全没有黄色元素

    x, y, w, h = cv2.boundingRect(points)

    # 过滤微小的噪点颗粒（至少要像个数字的宽高）
    if w < 10 or h < 10:
        return 0

    # 留 8 像素的外边距，避免贴边裁剪损伤字形
    pad = 8
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(yellow_mask.shape[1], x + w + pad)
    y2 = min(yellow_mask.shape[0], y + h + pad)

    cropped_mask = yellow_mask[y1:y2, x1:x2]

    # 2. 颜色反转（变为白底黑字）并放大到 OCR 最适宜的尺寸
    perfect_img = cv2.bitwise_not(cropped_mask)
    perfect_img = cv2.resize(perfect_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

    _, img_bytes = cv2.imencode('.png', perfect_img)
    text = ocr.classification(img_bytes.tobytes())

    # 3. 强制字符纠偏
    text = text.upper()
    text = text.replace('O', '0').replace('Q', '0').replace('D', '0').replace('U', '0')
    text = text.replace('I', '1').replace('L', '1')
    text = text.replace('S', '5')
    text = text.replace('Z', '2')
    text = text.replace('B', '8')

    try:
        return int(''.join(filter(str.isdigit, text)))
    except ValueError:
        return 0

# ---------------------------------------------------------
# OCR 引擎 2：用于纯白底浅蓝字 (最终 RESULT 结算界面的 Coins)
# ---------------------------------------------------------
def read_result_number(img, search_zone):
    sx, sy, sw, sh = search_zone
    if sw == 0 or sh == 0:
        return 0

    roi = img[sy:sy + sh, sx:sx + sw]
    roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    _, img_bytes = cv2.imencode('.png', gray)
    text = ocr.classification(img_bytes.tobytes())

    try:
        return int(''.join(filter(str.isdigit, text)))
    except ValueError:
        return 0


# ================= 3. 数据与主循环 =================
def load_daily_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("date") == time.strftime("%Y-%m-%d"):
                    return data.get("coins", 0), data.get("fails", 0)
        except Exception:
            pass
    return 0, 0


def save_daily_data(coins, fails):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({"coins": coins, "fails": fails, "date": time.strftime("%Y-%m-%d")}, f)


def auto_play_loop():
    global upcoming_card_val
    counter = HighLowCounter()
    card_rec = CardRecognizer("templates")
    daily_coins, daily_fails = load_daily_data()
    net_profit = daily_coins - (daily_fails * 50)
    print(f"开始自动挂机... 当日累计代币: {daily_coins} | 累计失败: {daily_fails} 次 | 今日净利润: {net_profit}")

    has_tallied = False
    has_recorded_fail = False  # 防止在 FAIL 动画期间重复扣除门票

    while daily_coins < 20000 and bot_running :
        img, win_left, win_top = capture_game_window()
        if img is None:
            print("未找到游戏窗口，请确保游戏没有被完全最小化...")
            time.sleep(1)
            continue

        current_state = detect_game_state(img)

        if current_state != "RESULT":
            has_tallied = False
        if current_state != "FAIL":
            has_recorded_fail = False

        # === 实时渲染 GUI 画面 ===
        display_img = img.copy()
        cv2.putText(display_img, f"State: {current_state}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        cv2.putText(display_img, f"Coins: {daily_coins} / {TARGET_LIMIT}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                    (0, 255, 255), 3)
        if current_state == "UNKNOWN":
            cv2.putText(display_img, "Waiting for match...", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        #cv2.imshow("Auto Bot GUI", display_img)

        #if cv2.waitKey(1) & 0xFF == ord('q'):
            #print("收到退出指令，结束挂机。")
            #break
        # =========================

        if current_state == "UNKNOWN":
            time.sleep(0.5)
            continue

        if current_state == "START_BET":
            print("\n[状态] 初始下注")
            counter.reset()
            upcoming_card_val = None

            # 遍历尝试点击当前语言的 Start 图标
            for tpl in ICON_TEMPLATES["START_BET"]:
                if find_and_click_icon(img, tpl, win_left, win_top):
                    break
            time.sleep(1)

        elif current_state == "HOLD_CARDS":
            print("\n[状态] 留牌阶段")
            recognized_cards, rects = card_rec.recognize(img)
            if len(recognized_cards) == 5:
                hand_ids = [c.card_id for c in recognized_cards]
                card_values = [get_real_card_value(c) for c in recognized_cards if c.card_id != JOKER_ID]
                counter.remove_cards(card_values)

                best, _ = calculate_best(hand_ids, "standard")

                for idx in best.held_indices:
                    x, y, w_box, h_box = rects[idx]
                    safe_click(x + w_box // 2, y + h_box // 2, win_left, win_top)
                    time.sleep(0.15)

                time.sleep(0.3)
                find_and_click_icon(img, "templates/icons/tpl_replace.png", win_left, win_top)
                time.sleep(1)

        elif current_state == "TAP_TO_PROCEED":
            h, w = img.shape[:2]
            safe_click(w // 2, h // 2, win_left, win_top)
            time.sleep(0.6)








        elif current_state == "ASK_CHALLENGE":

            real_reward = read_screen_number(img, REWARD_ZONE)

            next_reward = real_reward if real_reward > 0 else 200

            current_cashout = next_reward // 2

            print(f"\n[账房] 当前在手现金: {current_cashout} | 挑战成功后将变为: {next_reward}")

            if upcoming_card_val is not None:

                _, win_rate = counter.get_best_choice_and_rate(upcoming_card_val)

                print(f"[风控] 基于预判，下一轮真实胜率为: {win_rate:.2%}")

            else:

                win_rate = 1.0

                print("[风控] 第一轮或盲盒状态，默认直接挑战！")

            # === 终极风控：智能垫刀 / 极限冲刺 ===

            # 【规则 1：冲刺期】账户金币已达 19800，目标是实际到手现金 >= 10000

            if daily_coins >= 19800:

                if current_cashout >= 10000:

                    print(f"🎉 终极目标达成！在手奖金已达 {current_cashout} (超1w)，安全提现大丰收！")

                    find_and_click_icon(img, "templates/icons/tpl_cross.png", win_left, win_top)

                else:

                    print(f"🚀 冲刺期继续追击（无视胜率，目标在手1w）！当前在手仅 {current_cashout}，冲刺 {next_reward}！")

                    find_and_click_icon(img, "templates/icons/tpl_check.png", win_left, win_top, threshold=0.55)


            # 【规则 2：平稳垫刀期】总金币未达到 19800，严格控分慢慢垫

            else:

                # 1. 核心修复：当前这笔在安全线内，但再翻倍就会爆破 19800 -> 立即刹车提现垫刀！

                if daily_coins + current_cashout <= 19800 and daily_coins + next_reward > 19800:

                    print(
                        f"🛑 警报：提现(+{current_cashout})在安全线内，但再翻倍(+{next_reward})总额将达 {daily_coins + next_reward} 提前破限！果断收手垫刀！")

                    find_and_click_icon(img, "templates/icons/tpl_cross.png", win_left, win_top)


                # 2. 如果当前现金已经不慎超过了 19800（极端天胡开局）

                elif daily_coins + current_cashout > 19800:

                    if current_cashout >= 10000:

                        print(f"🎉 意外天胡！垫刀途中在手直接达 {current_cashout} (超1w)，直接收手大丰收！")

                        find_and_click_icon(img, "templates/icons/tpl_cross.png", win_left, win_top)

                    else:

                        print(
                            f"⚠️ 提现此笔(+{current_cashout})总额将达 {daily_coins + current_cashout} 破限且未破万！拒绝提现，强行搏翻倍！")

                        find_and_click_icon(img, "templates/icons/tpl_check.png", win_left, win_top, threshold=0.55)


                # 3. 正常发育，胜率低见好就收

                elif win_rate < 0.60:

                    print(f"🛑 发育局胜率太低 ({win_rate:.2%})，提现 {current_cashout} 垫刀！")

                    find_and_click_icon(img, "templates/icons/tpl_cross.png", win_left, win_top)


                # 4. 利润安全且下一把翻倍仍在安全线内，继续追击

                else:

                    print(f"🔥 利润安全且再翻倍不会超限，普通局继续追击翻倍！")

                    find_and_click_icon(img, "templates/icons/tpl_check.png", win_left, win_top, threshold=0.55)

            time.sleep(0.6)
        elif current_state == "HIGH_LOW":
            try:
                # 1. 用新引擎搜出所有白色卡牌
                rects = find_all_card_rects(img, HIGH_LOW_SEARCH_ZONE)

                if rects:
                    # 按 X 坐标排序，拿到最右侧的一张明牌
                    rects.sort(key=lambda r: r[0])
                    current_rect = rects[-1]

                    old_right_x = current_rect[0]

                    single_card = card_rec.recognize_card(img, current_rect)
                    if single_card.card_id != JOKER_ID:
                        current_card_val = get_real_card_value(single_card)
                        counter.remove_cards([current_card_val])
                        best_choice, rate = counter.get_best_choice_and_rate(current_card_val)

                        print(f"\n明牌: {single_card.rank}, 选: {best_choice.upper()} (胜率: {rate:.2%})")

                        if best_choice == "high":
                            find_and_click_icon(img, "templates/icons/tpl_high.png", win_left, win_top)
                        else:
                            find_and_click_icon(img, "templates/icons/tpl_low.png", win_left, win_top)

                        # === 2. 状态对比追踪连拍 ===
                        print("[预判] 启动多帧对比追踪...")
                        upcoming_card_val = None
                        os.makedirs("debug", exist_ok=True)

                        for i in range(25):
                            time.sleep(0.04)
                            flip_img, _, _ = capture_game_window()

                            if flip_img is not None:
                                try:
                                    new_rects = find_all_card_rects(flip_img, HIGH_LOW_SEARCH_ZONE)
                                    if new_rects:
                                        # 拿到连拍画面中最右侧的白牌
                                        new_rects.sort(key=lambda r: r[0])
                                        newest_rect = new_rects[-1]

                                        # 核心判定：如果新画面最右边白牌的 X 坐标，比明牌突增了 50 个像素以上
                                        # 证明有新卡翻过来变白了
                                        if newest_rect[0] > old_right_x + 50:
                                            newest_card = card_rec.recognize_card(flip_img, newest_rect)
                                            if newest_card.card_id != JOKER_ID:
                                                upcoming_card_val = get_real_card_value(newest_card)
                                                print(
                                                    f"[预判] 第 {i + 1} 帧追踪到新卡牌！下一张将是: {newest_card.rank}")

                                                cx, cy, cw, ch = newest_rect
                                                cv2.imwrite("debug/2_next_card.png",
                                                            flip_img[max(0, cy - 40):cy + ch + 40,
                                                            max(0, cx - 40):cx + cw + 40])
                                                break
                                except Exception:
                                    continue

                        if upcoming_card_val is None:
                            print("[预判] 连拍追踪超时，未能看清下一张牌。")

                        time.sleep(0.6)
                else:
                    print("\n[警告] 画面中未识别到任何白色卡牌，请确认画面处于 HIGH_LOW 状态且搜索区正常。")
            except Exception as e:
                print(f"\n[异常] 猜高低逻辑崩溃: {e}")

        elif current_state == "FAIL":
            if not has_recorded_fail:
                daily_fails += 1
                net_profit = daily_coins - (daily_fails * 50)
                save_daily_data(daily_coins, daily_fails)
                print(
                    f"\n💔 对局失败！累计失败: {daily_fails} 次 (门票损失: {daily_fails * 50}) | 今日净利润: {net_profit}")
                has_recorded_fail = True

            time.sleep(0.8)
            find_and_click_icon(img, "templates/icons/tpl_check.png", win_left, win_top, threshold=0.55)
            time.sleep(1)

        elif current_state == "RESULT":
            if not has_tallied:
                print("\n[状态] 结算界面，正在核对账目...")
                earned = read_result_number(img, RESULT_REWARD_ZONE)
                if earned > 0:
                    daily_coins += earned
                    net_profit = daily_coins - (daily_fails * 50)
                    print(
                        f"💰 成功入账: {earned} ! 当前总金币: {daily_coins} | 累计失败: {daily_fails} 次 | 今日净利润: {net_profit}")
                else:
                    print("⚠️ 未能识别到结算界面的金币数字")

                save_daily_data(daily_coins, daily_fails)
                has_tallied = True

            time.sleep(0.8)
            find_and_click_icon(img, "templates/icons/tpl_check.png", win_left, win_top, threshold=0.55)
            time.sleep(1)


if __name__ == "__main__":
    auto_play_loop()