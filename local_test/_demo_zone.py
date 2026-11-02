# -*- coding: utf-8 -*-
"""
压力区新口径 demo（`python local_test/_demo_zone.py`）：
把几段合成走势的强压力区、目标价、盈亏比打出来看，便于肉眼核对规则。
口径：只有下降波段才有压力；后面出现 ≥ 本根最高价的最高价（整根被覆盖）→ 该根释放；
      前高（最后一次由涨转跌那根）左边 3 根无条件保留。
"""
import sys, os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import jq_strong_structure as S


def bar(p, vol=1000.0, pad=0.05):
    return (p, p, p + pad, p - pad, vol)


def show(title, rows, v0, buy_price, p_low):
    o = np.array([r[0] for r in rows], float)
    c = np.array([r[1] for r in rows], float)
    h = np.array([r[2] for r in rows], float)
    l = np.array([r[3] for r in rows], float)
    v = np.array([r[4] for r in rows], float)
    zs = S.find_strong_zones(h, l, v, v0)
    tgt = S.pick_target(zs, buy_price)
    print('=' * 70)
    print(title)
    print('  n=%d  昨收=%.2f  V0=%.0f  买入价=%.2f  前低=%.2f'
          % (len(rows), c[-1], v0, buy_price, p_low))
    print('  被释放 %d 根 / %d' % (int(S.released_mask(h).sum()), len(h)))
    print('  前高（最后一次由涨转跌）= 第 %d 根 %.2f'
          % (S.find_recent_swing_high(h), h[S.find_recent_swing_high(h)]))
    print('  压力区: %s' % (['(%.2f~%.2f)' % z for z in zs] or '无'))
    if tgt is None:
        print('  目标 = None  → 不买（买入价已在压力区内 / 上方没压力区）')
    else:
        rr = (tgt - buy_price) / (buy_price - p_low)
        print('  目标 = %.2f   盈亏比 = (%.2f-%.2f)/(%.2f-%.2f) = %.2f  → %s'
              % (tgt, tgt, buy_price, buy_price, p_low, rr,
                 '可买' if rr >= 2 else '盈亏比不够，不买'))
    z0 = S.find_strong_zones(h, l, v, v0, keep_prev_high=0)
    print('  （关掉前高3根）: %s' % (['(%.2f~%.2f)' % z for z in z0] or '无'))


# ---------- A. 你举的例子：25 → 10 → 回升到 15 → 再跌到 10 ----------
rows = [bar(25.0)]
for i, p in enumerate(np.linspace(24.6, 10.2, 24)):      # 25→10，跌的时候放量
    rows.append(bar(float(p), 1500.0 if i % 2 else 900.0))
for p in np.linspace(10.4, 15.0, 12):                   # 10→15 回升，缩量
    rows.append(bar(float(p), 1000.0))
for p in np.linspace(14.7, 10.0, 12):                   # 15→10 再跌
    rows.append(bar(float(p), 1500.0 if i % 2 else 900.0))
show('A 25→10→回升15→再跌10（下跌段放量 1500、回升段缩量 1000）',
     rows, v0=1200.0, buy_price=10.10, p_low=9.90)

# ---------- B. 横盘：价格在 25 上下反复震（全部放量） ----------
rows = [bar(28.0)]
for p in [25.2, 25.3, 25.1, 25.4, 25.15, 25.35, 25.05, 25.45, 25.1, 25.25, 25.0, 25.3]:
    rows.append(bar(float(p), 1500.0))
show('B 横盘 25 附近来回震（每根都放量 1500）',
     rows, v0=1200.0, buy_price=25.50, p_low=25.0)

# ---------- C. 最近这一跌放量（2 倍以上 V0）→ 每根都算压力，紧贴买价 ----------
rows = [bar(30.0)]
for p in np.linspace(29.5, 18.0, 20):
    rows.append(bar(float(p), 900.0))
for p in np.linspace(17.8, 15.0, 6):
    rows.append(bar(float(p), 2600.0))
show('C 前面缩量下跌，最后 6 根 2 倍量砸下来',
     rows, v0=1200.0, buy_price=15.10, p_low=14.90)

# ---------- D. 一路缩量下跌（没有放量K线）→ 只剩前高 3 根 ----------
rows = [bar(30.0)]
for p in np.linspace(29.5, 20.0, 20):
    rows.append(bar(float(p), 800.0))
show('D 一路缩量下跌（没有一根放量）',
     rows, v0=1200.0, buy_price=20.10, p_low=19.90)
