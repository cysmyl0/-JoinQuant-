# -*- coding: utf-8 -*-
"""
演示：两个峰（30.00 与 26.50）时，"前高左边 3 根"到底保留了谁。
运行：python local_test\\_demo_supply.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import jq_strong_structure as S


def bar(h, l, v):
    return (float(h), float(l), float(v))


def build():
    """120 根：上到 30（峰 60）→ 跌到 22 → 反弹到 26.5（峰 104）→ 跌回 23.8。"""
    rows = []
    # 0..59：27.5 → 30.0 缓涨，量 1000（不构成放量）
    for i in range(60):
        c = 27.5 + (30.0 - 27.5) * i / 59.0
        rows.append(bar(c + 0.10, c - 0.10, 1000.0))
    # 60：最高价那根
    rows.append(bar(30.00, 29.20, 3000.0))
    # 61..90：30 → 22 的下跌段
    for i in range(30):
        c = 30.0 - (30.0 - 22.0) * (i + 1) / 30.0
        rows.append(bar(c + 0.15, c - 0.15, 1000.0))
    # 让 40~45 这一段变成"三根以上放量重合"，制造一个真实压力区（约 28~29.5）
    for t in (40, 41, 42, 43, 44, 45):
        hh, ll, vv = rows[t]
        rows[t] = bar(max(hh, 29.4), min(ll, 28.1), 2500.0)
    # 91..104：22 → 26.5 的反弹段
    for i in range(14):
        c = 22.0 + (26.5 - 22.0) * (i + 1) / 14.0
        rows.append(bar(c + 0.10, c - 0.10, 1000.0))
    # 104 是反弹的峰（26.50），给一根 2 倍量
    hh, ll, vv = rows[104]
    rows[104] = bar(26.50, 25.90, 2000.0)
    # 105..119：26.5 → 23.8 再跌
    for i in range(15):
        c = 26.5 - (26.5 - 23.8) * (i + 1) / 15.0
        rows.append(bar(c + 0.10, c - 0.10, 1000.0))
    a = np.array(rows, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2]


H, L, V = build()
n = len(H)
v0 = 1000.0                      # 假设买入当天的量 = 1000（与历史"平量"相同）
print('总根数 %d，最高价那根 = %d（%.2f），v0=%.0f' % (n, S.find_peak_idx(H), H[S.find_peak_idx(H)], v0))

peak = S.find_peak_idx(H)
rel = S.released_mask(H[peak:])
print('\n窗口 = %d → %d，其中被上涨收复（整根作废）%d 根，保留 %d 根'
      % (peak, n - 1, int(rel.sum()), int((~rel).sum())))

keep_idx = [peak + i for i in np.where(~rel)[0]]
print('保留的K线区间（价格）: %s' % (
    ', '.join('%d:%.1f~%.1f' % (i, L[i], H[i]) for i in keep_idx[:14]) + (' ...' if len(keep_idx) > 14 else '')))

p = S.find_recent_swing_high(H)
print('\nfind_recent_swing_high → %d（high=%.2f）' % (p, H[p]))
print('它左边 3 根（不含自己，无条件保留）→ %d/%d/%d：%s'
      % (p - 3, p - 2, p - 1,
         ', '.join('%.2f~%.2f' % (L[t], H[t]) for t in range(p - 3, p))))
print('30.00 那根（%d）左边 3 根是 %d/%d/%d：%s  ← 不在"无条件保留"里'
      % (peak, peak - 3, peak - 2, peak - 1,
         ', '.join('%.2f~%.2f' % (L[t], H[t]) for t in range(peak - 3, peak))))

zones = S.find_strong_zones(H, L, V, v0)
print('\n最终压力区（合并后）:')
for lo, hi in zones:
    print('   [%.2f, %.2f]' % (lo, hi))

print('\n买入价 23.80 → 状态 %s，目标 %s'
      % (S.zone_status(zones, 23.80), S.pick_target(zones, 23.80)))
print('买入价 28.50 → 状态 %s' % S.zone_status(zones, 28.50))

# ---- 对照：如果"每一个峰"都保留左边 3 根，会多出什么 ----
print('\n[对照] 若对每个局部峰都保留左 3 根：')
extra = []
for i in range(1, n - 1):
    if H[i] >= H[i - 1] and H[i] >= H[i + 1] and H[i] >= np.max(H[i + 1:]):
        for t in range(max(0, i - 3), i):
            extra.append((L[t], H[t], i))
for lo, hi, src in extra:
    print('   峰 %d 的左邻居 → [%.2f, %.2f]' % (src, lo, hi))
