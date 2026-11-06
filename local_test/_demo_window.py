# -*- coding: utf-8 -*-
"""
演示：窗口内某天站上过 L、但那天量不够没买成，今天还能不能买。
运行：python local_test\\_demo_window.py

当前口径（用户 2026-11-06 定的）：L 之后 4 根（有放缓 6 根）窗口内，
【任意一天】只要当天收盘 > L 且当天量能/涨幅达标就能买；"曾经站上过 L"不再让结构作废。
同一个结构只买一次（ONE_TRADE_PER_SETUP）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import jq_strong_structure as S


def bar(o, c, vol=1000.0):
    return (o, c, max(o, c) + 0.05, min(o, c) - 0.05, vol)


def build(break_day_close=None):
    """30 根横盘 + 4 根急跌（L = 最后一根的开盘价），然后按 break_day_close 造突破。"""
    rows = [(28.0, 28.0, 28.05, 27.95, 1000.0)] * 30
    rows += [bar(28.60, 28.00),        # 急跌 1
             bar(27.80, 27.20),        # 急跌 2
             bar(27.00, 26.40),        # 急跌 3
             bar(26.20, 25.60)]        # 急跌 4 → L = 26.20（这根的开盘价）
    # 之后三天：第 1 天没站上、第 2 天（可能）站上、第 3 天回落
    rows.append(bar(25.60, 26.10))     # 第1天：26.10 < L=26.20，没站上
    if break_day_close is None:
        rows.append(bar(26.10, 26.15))  # 第2天：26.15 < 26.20，也没站上
    else:
        rows.append(bar(26.10, break_day_close))   # 第2天：站上 L
    rows.append(bar(26.30, 26.05))     # 第3天：回落
    # 注意：detect_setup 的入参最后一根 = 昨天(T-1)，今天由 n = len(c) 代表，
    # 所以这里不能补"今天"那根，否则窗口会整体后移一位。
    a = np.array(rows, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]


def show(tag, rows, today_price, today_vol):
    o, c, h, l, v = rows
    st = S.detect_setup(o, c, h, l, v)
    print('\n' + tag)
    if st is None:
        print('   → 结构作废（撞上"重合超1%且创新低"或已出窗口）→ 今天不买')
        return
    v5, v10 = st['v5'], st['v10']
    k = st['wlen'] - st['wleft']
    r1 = today_price > st['L']
    r2 = S.volume_ok(today_vol, v5, v10)
    r3 = S.no_new_low(today_price, st['p_low'])
    r4 = S.stand_gain_ok(today_price, st['prev_close'])
    print('   L=%.2f，今天=第%d/%d根，前低=%.2f，昨收=%.2f'
          % (st['L'], k, st['wlen'], st['p_low'], st['prev_close']))
    print('   ① 收盘 %.2f > L %.2f        %s'
          % (today_price, st['L'], '✅' if r1 else '❌'))
    print('   ② 量 %.0f 在 (%.0f, %.0f) 内   %s'
          % (today_vol, v5 * (1 - S.VOL_S_TOL), v10 * S.VOL_CAP, '✅' if r2 else '❌'))
    print('   ③ 收盘 ≥ 前低              %s'
          % ('✅' if r3 else '❌'))
    print('   ④ 相对昨收涨幅 > 1%%         %s（%+.2f%%）'
          % ('✅' if r4 else '❌', (today_price / st['prev_close'] - 1) * 100))
    print('   → %s' % ('买入' if (r1 and r2 and r3 and r4) else '不买'))


# 情形 A：第 2 天就站上了 L，但那天量不够（成交量 1000，没放量）→ 今天第 4 根量够了
show('A 第2天站上过L（那天量不够，没买成）；今天第4根站上且量够',
     build(break_day_close=26.50), 26.60, 1200.0)

# 情形 B：前 3 天都没站上，今天（第 4 根）站上且量够
show('B 前3天都没站上；今天第4根站上且量够',
     build(break_day_close=None), 26.60, 1200.0)

# 情形 C：同 B，但今天量不够
show('C 前3天都没站上；今天第4根站上但量不够',
     build(break_day_close=None), 26.60, 800.0)
