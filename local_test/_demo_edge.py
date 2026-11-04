# -*- coding: utf-8 -*-
r"""
边界情形演示（不连聚宽，直接跑纯函数，用真实数字说明代码会怎么走）。

运行：
    python local_test\_demo_edge.py

演示三件事：
  情形1+2  放缓三根里有一根「收盘在 ±1% 内、但实体重合超过 1%」，而且这根还创新低
           → 放缓不算，窗口回到 4 根；它同时被当成"反转那根"，前低被它自己的低收盘拉低
  情形3    同一位置，那根K线不创新低而是往上顶 → 前低冻结在它之前
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import jq_strong_structure as S          # noqa: E402
from test_rules import BASE, mk, bar     # noqa: E402

L_IDX = 33


def show(title, rows):
    o, c, h, l, v = mk(rows)
    st = S.detect_setup(o, c, h, l, v)
    rev = S.find_reversal_idx(o, c, L_IDX)
    print('\n' + '=' * 74)
    print(title)
    print('-' * 74)
    print('L = %.2f（第 %d 根，实体 %.2f~%.2f，收盘 %.2f）'
          % (o[L_IDX], L_IDX, min(o[L_IDX], c[L_IDX]), max(o[L_IDX], c[L_IDX]), c[L_IDX]))
    for i in range(L_IDX + 1, len(c)):
        print('  第%d根 开%.2f 收%.2f 实体上沿%.2f | 相对昨收%+.2f%% | 重合%.2f(%.2f%%)%s'
              % (i, o[i], c[i], max(o[i], c[i]),
                 (c[i] / c[i - 1] - 1) * 100,
                 S.body_overlap(o, c, i - 1, i),
                 S.body_overlap(o, c, i - 1, i) / c[i] * 100,
                 '  ← 反转那根' if rev == i else ''))
    print('-' * 74)
    print('find_reversal_idx = %s' % rev)
    print('放缓成立? %s → wlen=%s' %
          ('是' if S.slow_run_ok(o, c, L_IDX) else '否',
           S.window_size(o, c, L_IDX)))
    # 结构挂掉的原因（按代码顺序判）
    why = None
    for i in range(L_IDX + 1, len(c)):
        if c[i] > o[L_IDX]:
            why = '第%d根收盘 %.2f 已站上 L=%.2f → 结构已用掉' % (i, c[i], o[L_IDX])
            break
        if (not S.overlap_ok(o, c, i - 1, i)) and S.makes_new_low(c, L_IDX, i):
            why = ('第%d根 重合超1%%(%.2f%%) 且创新低(%.2f < 此前最低 %.2f) '
                   '→ 新的下跌结构，从它重新数三根急跌'
                   % (i, S.body_overlap(o, c, i - 1, i) / c[i] * 100, c[i],
                      min(c[L_IDX:i])))
            break
    if st is None:
        print('结论：今天不买 —— %s' % (why or '出窗口（L 之后已经超过 %d 根）'
                                      % S.window_size(o, c, L_IDX)))
    else:
        print('p_low（前低/止损位）= %.2f' % st['p_low'])
        print('  若今天买在 L=%.2f 上方：风险 = %.2f，目标 = 买价 + 2×%.2f'
              % (st['L'], st['L'] - st['p_low'], st['L'] - st['p_low']))
        print('  不冻结（全窗口最低）= %.2f' % min(c[L_IDX:]))


# 情形1+2：三根收盘都在 ±1% 内，第三根实体往上顶 2.9%，且它自己创了新低
show('情形1+2：放缓三根里出现"重合超1%"的K线，而且它创了新低',
     BASE + [bar(24.20, 24.20),      # 34 磨底  +0.83%
             bar(24.15, 24.10),      # 35 磨底  -0.41%
             bar(24.80, 23.90)])     # 36 高开低走：收 23.90（新低，-0.83%），实体上沿 24.80

# 情形3：同一位置，但那根是往上顶的，之后再回踩更深
show('情形3：那根"重合超1%"的K线是往上顶的（不创新低），之后回踩更深',
     BASE + [bar(24.20, 24.20),      # 34 磨底
             bar(24.50, 24.70),      # 35 反转那根（收 24.70）
             bar(24.10, 23.90)])     # 36 回踩，收 23.90 比之前最低 24.00 还低

print('\n' + '=' * 74)
