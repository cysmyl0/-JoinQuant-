# -*- coding: utf-8 -*-
"""
本地离线单测（不连聚宽，只测纯函数层）。

运行：
    python local_test\test_rules.py

覆盖 17 项：
  1  find_L 找到最后一根有效大阴线，且 L = 该根开盘价
  2  实体间隙差一点点（0.20 < 1%×25.40=0.254）→ 不算有效阴线
  3  实体跌幅 ≤ 1% → 不算
  4  跌停板豁免：实体无间隙但跌幅≥9.8% → 仍算有效
  5  阳线 → 不算
  6  无放缓：L 后第 4 根仍在窗口（wleft=0）
  7  无放缓：L 后第 5 根失效（None）
  8  有放缓：同样 4 根，wleft=1 仍可买（窗口放宽到 6 根）
  9  有放缓：第 7 根失效（None）
 10  窗口内站上过 L 后，今天自己达标仍可买（窗口内任意一天都能买）
 11  急跌：连跌 4 根累计 -14% → True；只连跌 2 根 → False
 12  量能三态：等于均量 / 适中 / 2 倍均量
 13  不创新低
 14  盈亏比与最近压力区
 15  强压力区：三根放量K线价格区间重合 / 影线重合实体不重合也算 / 只有2根不算 /
      最高价之前的重合不算 / 单根2倍量整根算 / 没有放量K线则无
 16  卖出逻辑：T+1、止损、止盈
 17  持仓放量减仓：当日量 > 2×MA10 才减、1/3 取整到 100 股、不足 2 手不减
 18  急跌三条口径：实体重合 ≤1% 才算（缺口/贴住/小幅重叠都算）/ 重合 >1% 不算 /
      第一根不足1%且没破前低不算 / 破了前低就算 / 跌停板豁免重叠
 19  站上 L 那根上涨K线的涨幅必须 > 1%（原文"上涨的k线也要>1%"）
 20  标的池剔除 ST / *ST（is_st 接口优先，退化按简称，接口挂了不乱杀）
 21  止盈：到压力区卖 2/3、留 1/3 跟 20 日线、不够拆全卖
 22  20 日均线跌破容差 1%
 23  主板识别（60x + 000/001/002/003，排除创业板/科创板/北交所/B股）
 24  排除上市未满 3 年（次新股）
"""

import os
import sys
import datetime
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)          # 让 jqdata 占位模块可被找到

import jq_strong_structure as S   # noqa: E402

FAILED = []
PASSED = [0]


def check(name, cond, detail=''):
    if cond:
        PASSED[0] += 1
        print('  PASS  %s' % name)
    else:
        FAILED.append(name)
        print('  FAIL  %s   %s' % (name, detail))


def mk(rows):
    o = np.array([r[0] for r in rows], dtype=float)
    c = np.array([r[1] for r in rows], dtype=float)
    h = np.array([r[2] for r in rows], dtype=float)
    l = np.array([r[3] for r in rows], dtype=float)
    v = np.array([r[4] for r in rows], dtype=float)
    return o, c, h, l, v


def pad(k, price=28.0, vol=1000.0):
    """k 根横盘小K线"""
    return [(price, price, price + 0.05, price - 0.05, vol)] * k


def bar(o, c, vol=1500.0):
    h = max(o, c) + 0.05
    l = min(o, c) - 0.05
    return (o, c, h, l, vol)


# 基础下跌结构：30 根横盘 + 4 根跳空急跌（每根实体之间都有 1% 以上的缺口），
# 第 4 根（idx33）是有效大阴线。缺口是原文"实体不重叠超过1%"的要求（REQUIRE_GAP）。
BASE = pad(30) + [
    bar(28.00, 27.10),   # idx30 跌 -3.2%（第一根，跌幅>1%）
    bar(26.80, 26.10),   # idx31 跌，缺口 27.10-26.80=0.30 > 0.01×26.10=0.261
    bar(25.80, 25.20),   # idx32 跌，缺口 26.10-25.80=0.30 > 0.01×25.20=0.252
    bar(24.90, 24.00),   # idx33 有效大阴线：缺口 25.20-24.90=0.30 > 0.24
]
L_IDX = 33
L_PRICE = 24.90


def run():
    print('\n[1-5] 有效大阴线 L 的判定')

    o, c, h, l, v = mk(BASE)
    i = S.find_L(o, c)
    check('1 找到 L 且 L=开盘价', i == L_IDX and abs(o[i] - L_PRICE) < 1e-9,
          'i=%s L=%s' % (i, None if i is None else o[i]))

    # 2 有跳空缺口（实体不重合）→ 有效（原文只限制"重合"上限，不要求缺口）
    o2, c2, _, _, _ = mk([bar(27.00, 26.00), bar(25.80, 25.40)])
    check('2 有跳空缺口 → 有效', S.is_valid_bear(o2, c2, 1) is True, 'gap=0.20')
    # 2b 首尾相接（重合 0）→ 有效
    o3, c3, _, _, _ = mk([bar(27.00, 26.00), bar(26.00, 25.40)])
    check('2b 首尾相接（重合0）→ 有效', S.is_valid_bear(o3, c3, 1) is True)
    # 2c 重合 0.20 = 0.79%×25.40 ≤ 1% → 有效
    o3b, c3b, _, _, _ = mk([bar(27.00, 26.00), bar(26.20, 25.40)])
    check('2c 重合 0.20（0.79%）→ 有效', S.is_valid_bear(o3b, c3b, 1) is True,
          'overlap=%s need ≤%s' % (S.body_overlap(o3b, c3b, 0, 1),
                                   S.PCT * c3b[1]))
    # 2d 重合 0.30 = 1.18% > 1% → 无效
    o3c, c3c, _, _, _ = mk([bar(27.00, 26.00), bar(26.30, 25.40)])
    check('2d 重合 0.30（1.18%）→ 无效', S.is_valid_bear(o3c, c3c, 1) is False,
          'overlap=%s > %s' % (S.body_overlap(o3c, c3c, 0, 1),
                               S.PCT * c3c[1]))

    # 3 跌幅 0.39% ≤ 1% → 无效
    o4, c4, _, _, _ = mk([bar(27.00, 26.00), bar(25.60, 25.50)])
    check('3 实体跌幅不足1%', S.is_valid_bear(o4, c4, 1) is False, 'drop=0.39%')

    # 4 跌停豁免：实体重合 0.50 > 1%（0.234）但跌幅 12.3% → 豁免 → 有效
    o5, c5, _, _, _ = mk([bar(27.00, 26.00), bar(26.50, 23.40)])
    check('4 跌停板豁免', S.is_valid_bear(o5, c5, 1) is True,
          'overlap=%s is_limit_down=%s' % (S.body_overlap(o5, c5, 0, 1),
                                           S.is_limit_down(c5, 1)))

    # 5 阳线 → 无效
    o6, c6, _, _, _ = mk([bar(27.00, 26.00), bar(25.00, 25.50)])
    check('5 阳线不算', S.is_valid_bear(o6, c6, 1) is False)

    print('\n[6-10] 窗口与放缓')

    # 6 无放缓，L 后 3 根 → n=37，wleft = 33+4-37 = 0（第 4 根，最后机会）
    rows6 = BASE + [bar(24.30, 24.30), bar(24.05, 24.05), bar(24.35, 24.35)]
    o, c, h, l, v = mk(rows6)
    st = S.detect_setup(o, c, h, l, v)
    check('6 第4根仍在窗口', st is not None and st['wleft'] == 0 and st['wlen'] == 4,
          'st=%s' % st)

    # 7 无放缓，L 后 4 根 → wleft = -1 → 失效
    rows7 = rows6 + [bar(24.00, 24.00)]
    o, c, h, l, v = mk(rows7)
    check('7 第5根失效', S.detect_setup(o, c, h, l, v) is None
          and S.window_size(o, c, L_IDX) == 4)

    # 8 有放缓：连续 3 根 ±1% 内 → 窗口 6 根，同样 4 根仍有 wleft=1（n=38）
    rows8 = BASE + [bar(24.20, 24.20), bar(24.25, 24.25),
                    bar(24.10, 24.10), bar(24.40, 24.40)]
    o, c, h, l, v = mk(rows8)
    st = S.detect_setup(o, c, h, l, v)
    check('8 放缓后窗口6根', st is not None and st['wlen'] == 6 and st['wleft'] == 1,
          'st=%s' % st)

    # 9 有放缓，L 后 6 根 → wleft = -1 → 失效
    rows9 = rows8 + [bar(24.15, 24.15), bar(24.45, 24.45)]
    o, c, h, l, v = mk(rows9)
    check('9 放缓后第7根失效', S.detect_setup(o, c, h, l, v) is None
          and S.window_size(o, c, L_IDX) == 6)

    # 8b 三根收盘都在 ±1% 内，但其中一根实体压过前一根 1% → 不算放缓（窗口仍 4 根）
    rows8b = BASE + [bar(24.60, 24.20),   # 高开长上影：收盘 +0.83% 算窄幅，但实体压过 L 0.60（2.5%）
                     bar(24.15, 24.20),
                     bar(24.25, 24.30)]
    o, c, h, l, v = mk(rows8b)
    check('8b 窄幅但实体重合>1% → 不算放缓',
          S.slow_run_ok(o, c, L_IDX) is False and S.window_size(o, c, L_IDX) == 4,
          'overlap(33,34)=%s' % S.body_overlap(o, c, 33, 34))
    # 8c 同样三根收盘，把第一根改成贴合（实体不压过 1%）→ 算放缓
    rows8c = BASE + [bar(24.20, 24.20),
                     bar(24.15, 24.20),
                     bar(24.25, 24.30)]
    o, c, h, l, v = mk(rows8c)
    check('8c 窄幅且实体贴合 → 放缓 6 根', S.window_size(o, c, L_IDX) == 6,
          'wlen=%s' % S.window_size(o, c, L_IDX))

    # 10 窗口内【站上过 L】不让结构作废：今天仍在窗口内、今天自己达标就能买
    rows10 = BASE + [bar(25.10, 25.10), bar(25.00, 25.00)]
    o, c, h, l, v = mk(rows10)
    st = S.detect_setup(o, c, h, l, v)
    check('10 第2天站上过L，今天(第3根)仍可买',
          st is not None and st['wleft'] == 1, 'st=%s' % st)

    # 10a 用户场景：第 2 天收盘在 L 上方但量能不够没买成，今天第 4 根再达标 → 仍然可以买
    rows10a = BASE + [bar(25.10, 25.10), bar(25.00, 25.00), bar(25.20, 25.20)]
    o, c, h, l, v = mk(rows10a)
    st = S.detect_setup(o, c, h, l, v)
    check('10a 第2天站上过L，今天(第4根)仍可买',
          st is not None and st['wleft'] == 0, 'st=%s' % st)

    print('\n[10b] 前低：磨底阶段小实体新低是允许的，前低跟着下移；反转之后才冻结')
    # 34/35/36 每根都创一点新低，但实体都贴着（重合≤1%）→ 还在磨底，结构不废，前低一路下移到 23.90
    rows10b = BASE + [bar(24.20, 24.10),
                      bar(24.10, 23.95),
                      bar(24.00, 23.90)]
    o, c, h, l, v = mk(rows10b)
    st = S.detect_setup(o, c, h, l, v)
    check('10b 磨底小实体连续新低 → 结构不废，前低跟着下移到 23.90',
          st is not None and abs(st['p_low'] - 23.90) < 1e-9,
          'p_low=%s rev=%s' % (None if st is None else st['p_low'],
                               S.find_reversal_idx(o, c, L_IDX)))
    # 35 往上顶（重合 2.02%、没创新低）= 反转那根 → 前低冻结在 24.00；36 回踩到 23.90 跌破它 → 作废
    rows10b2 = BASE + [bar(24.20, 24.10),
                       bar(24.50, 24.70),
                       bar(24.10, 23.90)]
    o, c, h, l, v = mk(rows10b2)
    check('10b2 反转之后跌破冻结前低(=止损位) → 新的下跌结构，重新数三根急跌',
          S.detect_setup(o, c, h, l, v) is None
          and S.find_reversal_idx(o, c, L_IDX) == 35,
          'rev=%s c36=%.2f' % (S.find_reversal_idx(o, c, L_IDX), c[36]))
    # 同样有反转那根，但 36 只回踩到 24.05（守住冻结的前低）→ 结构还在，前低 = 24.00
    rows10c = BASE + [bar(24.20, 24.10),
                      bar(24.50, 24.70),
                      bar(24.10, 24.05)]
    o, c, h, l, v = mk(rows10c)
    st = S.detect_setup(o, c, h, l, v)
    check('10c 反转后守住冻结前低 → 结构有效，前低=24.00',
          st is not None and abs(st['p_low'] - 24.00) < 1e-9
          and S.find_reversal_idx(o, c, L_IDX) == 35,
          'p_low=%s rev=%s' % (None if st is None else st['p_low'],
                               S.find_reversal_idx(o, c, L_IDX)))

    print('\n[10d] 重合超1%又创新低 → 不是反转，是新的下跌结构')
    # 收盘 -0.83%（在 ±1% 内，本来算窄幅），但实体上沿 24.80 压过前一根 2.93%，且收 23.90 破前低
    rows10d = BASE + [bar(24.20, 24.20),
                      bar(24.15, 24.10),
                      bar(24.80, 23.90)]
    o, c, h, l, v = mk(rows10d)
    check('10d 重合超1%且创新低 → 结构作废（重新数三根急跌）',
          S.detect_setup(o, c, h, l, v) is None
          and S.makes_new_low(c, L_IDX, 36) is True
          and S.find_reversal_idx(o, c, L_IDX) is None,
          'rev=%s newlow=%s' % (S.find_reversal_idx(o, c, L_IDX),
                                S.makes_new_low(c, L_IDX, 36)))
    # 同样一根创新低，但实体几乎贴住（重合 0.21%）→ 还是磨底，不算新的下跌段，前低只是跟着低到 23.90
    rows10e = BASE + [bar(24.20, 24.20),
                      bar(24.15, 24.10),
                      bar(23.95, 23.90)]
    o, c, h, l, v = mk(rows10e)
    st = S.detect_setup(o, c, h, l, v)
    check('10e 创新低但重合≤1% → 算磨底，结构不废（前低降到 23.90）',
          st is not None and abs(st['p_low'] - 23.90) < 1e-9
          and S.find_reversal_idx(o, c, L_IDX) is None,
          'p_low=%s rev=%s' % (None if st is None else st['p_low'],
                               S.find_reversal_idx(o, c, L_IDX)))


    # 跳空低开、跌幅 >1% 的那根本身就是有效大阴线 → 它自己会变成新的 L，轮不到"放过"
    rows10f = BASE + [bar(24.20, 24.20),
                      bar(24.15, 24.10),
                      bar(23.60, 23.30)]
    o, c, h, l, v = mk(rows10f)
    check('10f 跳空低开且跌幅>1% → 它自己就是新 L（find_L 直接选它）',
          S.is_valid_bear(o, c, 36)
          and S.find_L(o, c) == 36
          and abs(o[S.find_L(o, c)] - 23.60) < 1e-9,
          'find_L=%s L=%.2f 跌幅%.2f%% 重合%.2f%%'
          % (S.find_L(o, c), o[S.find_L(o, c)],
             (o[36] - c[36]) / c[36] * 100,
             S.body_overlap(o, c, 35, 36) / c[36] * 100))

    print('\n[11] 急跌判定')
    o, c, h, l, v = mk(BASE)
    check('11a 连跌4根累计-14% → True', S.is_sharp_decline(o, c, L_IDX) is True)
    rows11 = pad(10) + [bar(28.00, 27.10), bar(26.00, 25.20)]
    o, c, h, l, v = mk(rows11)
    check('11b 只有2根下跌 → False', S.is_sharp_decline(o, c, 11) is False)

    print('\n[12-14] 量能 / 不创新低 / 盈亏比')
    check('12a 等于5日均量 → 有10%容差，算过', S.volume_ok(1000, 1000, 1000) is True)
    check('12b 放量适中 → 买', S.volume_ok(1500, 1000, 1000) is True)
    check('12c 达到2倍10日均量 → 不买', S.volume_ok(2000, 1000, 1000) is False)
    check('12d 只有5日均量的90% → 不买（严格大于）', S.volume_ok(900, 1000, 1000) is False)
    check('12e 均量的95% → 落在容差内，算过', S.volume_ok(950, 1000, 1000) is True)
    check('12f 均量的89% → 容差外，不买', S.volume_ok(890, 1000, 1000) is False)

    check('13a 收盘价≥前低', S.no_new_low(23.00, 22.50) is True)
    check('13b 收盘价<前低', S.no_new_low(22.40, 22.50) is False)

    check('14a 盈亏比=2.0', abs(S.risk_reward(30.0, 25.0, 22.5) - 2.0) < 1e-9)
    check('14b 2.08≥2 → 通过', S.rr_ok(30.0, 25.0, 22.6) is True)
    check('14c 1.92<2 → 否决', S.rr_ok(30.0, 25.0, 22.4) is False)
    check('14d 取上方最近压力区的下沿',
          S.pick_target([(20.0, 21.0), (26.0, 27.0), (30.0, 31.0)], 25.0) == 26.0)
    check('14e 上方无压力区 → None',
          S.pick_target([(20.0, 21.0), (24.0, 24.5)], 25.0) is None)
    check('14f 买入价已在压力区内 → 不给目标（压力太近，不买）',
          S.pick_target([(25.0, 25.1), (28.0, 28.5)], 25.05) is None)
    check('14g 买入价正好压着下沿 → 不给目标',
          S.pick_target([(25.0, 25.5)], 25.0) is None)
    check('14h 买入价在区内但上方另有压力区 → 仍然不买',
          S.pick_target([(25.0, 25.5), (30.0, 31.0)], 25.2) is None)

    # 14i 三态判定：压力区在上方 / 买入价已在区内 / 上方一条都没有
    check('14i 上方有压力区 → above',
          S.zone_status([(26.0, 27.0)], 25.0) == 'above')
    check('14i 买入价已在区内 → inside',
          S.zone_status([(25.0, 25.5)], 25.2) == 'inside')
    check('14i 压力区全在买入价下方 → none',
          S.zone_status([(18.0, 19.0), (20.0, 21.0)], 25.0) == 'none')
    check('14i 一条压力区都没算出来 → none', S.zone_status([], 25.0) == 'none')

    # 14j 上方没压力区时的兜底：按固定 2:1 算目标，但必须落在 120 日最高价之内
    check('14j 120日高点有空间 → 目标 = 买入 + 2×(买入-前低) = 30.0',
          abs(S.fallback_target(25.0, 22.5, 40.0) - 30.0) < 1e-9)
    check('14j 250日最高价正好等于目标 → 边界通过',
          abs(S.fallback_target(25.0, 22.5, 30.0) - 30.0) < 1e-9)
    check('14j 250日最高价不够 2:1（29.0 < 30.0）→ 不买',
          S.fallback_target(25.0, 22.5, 29.0) is None)
    check('14j 买入价已在 120 日最高价上 → 没有空间，不买',
          S.fallback_target(25.0, 24.0, 25.0) is None)
    check('14j 前低 ≥ 买入价（没有风险度）→ 不买',
          S.fallback_target(25.0, 25.0, 40.0) is None)
    check('14j 没给 120 日最高价 → 不买',
          S.fallback_target(25.0, 22.5, None) is None)

    # 14k 到价判定：持仓期跳空（开盘价已在目标价之上）怎么处理
    #   签名：target_hit(price, target, day_open, day_high, day_low, gap_hold)
    check('14k 高开在目标之上、全天没回落 → 不卖',
          S.target_hit(28.80, 27.95, 28.60, 29.00, 28.20) is False)
    check('14k 高开在目标之上、盘中回落到目标价 → 卖（跳空回踩）',
          S.target_hit(28.50, 27.95, 28.60, 29.00, 27.80) is True)
    check('14k 高开在目标之上、盘中最低正好等于目标价 → 卖',
          S.target_hit(28.50, 27.95, 28.60, 29.00, 27.95) is True)
    check('14k 开盘低于目标、盘中最高摸到 → 卖',
          S.target_hit(27.20, 27.95, 27.00, 28.10, 26.90) is True)
    check('14k 开盘低于目标、盘中也没摸到 → 不卖',
          S.target_hit(27.20, 27.95, 27.00, 27.50, 26.90) is False)
    check('14k 没有当日高低价 → 退回用 14:55 价判',
          S.target_hit(27.95, 27.95, None, None, None) is True
          and S.target_hit(27.90, 27.95, None, None, None) is False)
    check('14k 关掉 GAP_UP_HOLD（旧口径）→ 高开在目标之上就直接卖',
          S.target_hit(28.80, 27.95, 28.60, 29.00, 28.20, gap_hold=False) is True)
    check('14k 没给目标价 → 不卖', S.target_hit(28.80, None) is False)

    print('\n[15] 强压力区（只算没被上涨收复的下降段）')
    V0 = 1200.0          # 买入当天量：放量K线 2000 > 1200，但 2000 < 2×1200=2400（不触发2倍量）
    NO_PH = 0            # 关掉"前高3根"，单独测重合逻辑

    # 15a 三根放量、高点逐根递减（没被收复）→ 交集 24.90~25.10
    rows = pad(10, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)          # 上一个最高价在这根
    rows += [
        (24.90, 25.10, 25.30, 24.80, 2000.0),
        (25.00, 25.05, 25.20, 24.90, 2000.0),
        (25.05, 25.20, 25.10, 24.80, 2000.0),
        (24.95, 24.95, 25.00, 24.85, 1000.0),           # 不放量，不参与
    ]
    o, c, h, l, v = mk(rows)
    check('15a 峰值定位正确', S.find_peak_idx(h) == 0, 'peak=%d' % S.find_peak_idx(h))
    zones = S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH)
    check('15a 三根放量区间重合 → 24.90~25.10',
          len(zones) == 1 and abs(zones[0][0] - 24.90) < 1e-9
          and abs(zones[0][1] - 25.10) < 1e-9, 'zones=%s' % zones)

    # 15b 实体完全不重合，但上/下影线重合 → 仍然算强压力区（不只看收盘价）
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [
        (24.00, 24.40, 25.60, 23.80, 2000.0),           # 实体24.00~24.40，上影到25.60
        (24.90, 25.20, 25.25, 24.85, 2000.0),           # 实体24.90~25.20
        (24.40, 24.70, 25.15, 24.30, 2000.0),           # 实体24.40~24.70
    ]
    o, c, h, l, v = mk(rows)
    zones = S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH)
    check('15b 影线重合、实体不重合 → 仍算压力区',
          len(zones) == 1 and abs(zones[0][0] - 24.85) < 1e-9
          and abs(zones[0][1] - 25.15) < 1e-9, 'zones=%s' % zones)

    # 15c 只有两根放量K线重合 → 不够三根，不算
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [
        (24.00, 24.40, 25.60, 23.80, 2000.0),
        (24.90, 25.20, 25.25, 24.85, 2000.0),
        (24.40, 24.70, 25.15, 24.30, 1000.0),           # 第三根不放量
    ]
    o, c, h, l, v = mk(rows)
    check('15c 只有2根放量 → 不算',
          S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH) == [],
          'zones=%s' % S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH))

    # 15d 窗口起点：最高价之前的三根重合不算（下跌阶段才看）
    rows = [
        (28.0, 28.0, 28.2, 27.8, 2000.0),
        (28.0, 28.0, 28.2, 27.8, 2000.0),
        (28.0, 28.0, 28.2, 27.8, 2000.0),               # 这三根在最高价之前
        (30.0, 30.0, 30.5, 29.5, 1000.0),               # 最高价这根 → 窗口从这里起
        (29.0, 28.5, 29.2, 28.3, 1000.0),
        (28.0, 27.5, 28.2, 27.3, 1000.0),
    ]
    o, c, h, l, v = mk(rows)
    check('15d 最高价之前的重合不算',
          S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH) == [],
          'zones=%s' % S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH))

    # 15e 单根 2 倍量 → 整根 [最低价, 最高价] 都算压力区
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [(26.0, 26.1, 26.2, 25.8, 2500.0)]
    o, c, h, l, v = mk(rows)
    zones = S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH)
    check('15e 单根2倍量 → 25.80~26.20',
          len(zones) == 1 and abs(zones[0][0] - 25.8) < 1e-9
          and abs(zones[0][1] - 26.2) < 1e-9, 'zones=%s' % zones)

    # 15f v0 太大（没有K线放量）→ 无压力区
    o, c, h, l, v = mk(rows)
    check('15f 没有放量K线 → 无压力区',
          S.find_strong_zones(h, l, v, v0=5000.0, keep_prev_high=NO_PH) == [])

    # 15g 后面又涨回三根K线之上（整根被覆盖）→ 压力释放，不算
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [
        (24.90, 25.10, 25.30, 24.80, 2000.0),
        (25.00, 25.05, 25.20, 24.90, 2000.0),
        (25.05, 25.20, 25.10, 24.80, 2000.0),
        (25.40, 25.50, 25.60, 25.30, 1000.0),           # 最高价 25.60 ≥ 上面三根 → 全释放
    ]
    o, c, h, l, v = mk(rows)
    check('15g 被上涨整根覆盖 → 不算压力区',
          S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH) == [],
          'zones=%s' % S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH))

    # 15h 最近这一跌（最后一段下降）的放量K线仍算压力
    rows = pad(4, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    for p in [28, 26, 24, 22, 20, 18, 16]:              # 一路跌到 16，不放量
        rows.append((p, p, p + 0.05, p - 0.05, 1000.0))
    rows += [
        (13.00, 12.80, 13.20, 12.60, 2000.0),
        (12.80, 12.60, 13.00, 12.40, 2000.0),
        (12.60, 12.40, 12.80, 12.20, 2000.0),
    ]
    o, c, h, l, v = mk(rows)
    zones = S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH)
    check('15h 最近一跌的放量K线 → 12.60~12.80',
          len(zones) == 1 and abs(zones[0][0] - 12.60) < 1e-9
          and abs(zones[0][1] - 12.80) < 1e-9, 'zones=%s' % zones)

    # 15i 前高（最近一次下跌的起点）左边 3 根无条件保留
    rows = pad(4, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    for p in [28, 26, 24, 22, 20, 18, 16, 14, 12, 10]:  # 跌到 10
        rows.append((p, p, p + 0.05, p - 0.05, 1000.0))
    for p in [11, 12, 13, 14, 15]:                      # 回升到 15（前高）
        rows.append((p, p, p + 0.05, p - 0.05, 1000.0))
    for p in [14.5, 14, 13.5, 13, 12.5, 12]:            # 再跌到 12
        rows.append((p, p, p + 0.05, p - 0.05, 1000.0))
    o, c, h, l, v = mk(rows)
    sw = S.find_recent_swing_high(h)
    check('15i 前高 = 回升到 15 的那根（不是 30 那根）',
          abs(h[sw] - 15.05) < 1e-9, 'idx=%d high=%.2f' % (sw, h[sw]))
    zones = S.find_strong_zones(h, l, v, v0=V0)         # 默认保留每个峰左 3 根
    check('15i 每个下跌起点的左边 3 根都保留 → 12/13/14 + 27（28 那根下跌起点）',
          len(zones) == 4
          and abs(zones[0][0] - 11.95) < 1e-9
          and abs(zones[1][0] - 12.95) < 1e-9
          and abs(zones[2][0] - 13.95) < 1e-9
          and abs(zones[3][0] - 26.95) < 1e-9, 'zones=%s' % zones)
    check('15i 关掉前高 3 根 → 无压力区（全是缩量）',
          S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH) == [],
          'zones=%s' % S.find_strong_zones(h, l, v, v0=V0, keep_prev_high=NO_PH))

    # 15i2 两个峰（29→30 →跌到22 → 反弹26.5 → 跌回23.8）：两段下跌的起点都要保留左 3 根
    hh = np.array([29.0, 29.4, 29.8, 30.0, 29.0, 28.0, 27.0, 26.0, 25.0, 24.0,
                   23.0, 22.0, 22.5, 23.0, 23.5, 24.0, 24.5, 25.0, 25.5, 26.0,
                   26.5, 26.0, 25.0, 24.0, 23.8], float)
    ll = hh - 0.20
    vv = np.full(len(hh), 1000.0)
    sw = S.find_all_swing_highs(hh)
    check('15i2 两个峰都识别成下跌起点（30 与 26.5）',
          len(sw) == 2 and abs(hh[sw[0]] - 30.0) < 1e-9
          and abs(hh[sw[1]] - 26.5) < 1e-9, 'idx=%s' % sw)
    check('15i2 find_recent_swing_high 仍取最后一个峰',
          S.find_recent_swing_high(hh) == sw[-1],
          'idx=%d' % S.find_recent_swing_high(hh))
    z2 = S.find_strong_zones(hh, ll, vv, v0=1000.0)
    check('15i2 两段下跌的各 3 根都进压力区（28.8~29.8 与 24.8~26.0）',
          any(abs(lo - 28.80) < 1e-9 for lo, hi in z2)
          and any(abs(hi - 26.00) < 1e-9 for lo, hi in z2), 'zones=%s' % z2)

    # 15j released_mask 单元测试：后面的最高价 ≥ 本根最高价 → 释放
    m = S.released_mask([10.0, 11.0, 9.0])
    check('15j 后面涨到 11 ≥ 本根 10 → 释放', list(m) == [True, False, False], str(m))
    m = S.released_mask([10.0, 9.0, 8.0])
    check('15j 高点严格递减 → 都没释放', list(m) == [False, False, False], str(m))
    m = S.released_mask([10.0, 9.0, 9.0])
    check('15j 后一根持平前一根 → 前一根释放', list(m) == [False, True, False], str(m))
    m = S.released_mask([10.0, 10.0])
    check('15j 后面持平也算覆盖 → 释放', list(m) == [True, False], str(m))

    # 15k find_recent_swing_high：25→10→回升15→再跌到10
    hh = np.array([25, 20, 15, 13, 11, 10, 11, 13, 15, 13, 11, 10], float)
    check('15k 前高 = 回升到 15 那根（idx 8）',
          S.find_recent_swing_high(hh) == 8,
          'idx=%d' % S.find_recent_swing_high(hh))
    hh2 = np.array([30, 29, 28, 27, 26], float)
    check('15k 单边下跌 → 退化为最高价那根（idx 0）',
          S.find_recent_swing_high(hh2) == 0, 'idx=%d' % S.find_recent_swing_high(hh2))

    print('\n[16] 卖出逻辑')
    d0 = datetime.date(2024, 1, 2)
    d1 = datetime.date(2024, 1, 3)
    entry = {'p_low': 22.5, 'target': 30.0, 'buy': 25.0}
    ok, why = S.should_sell(29.0, entry, d0, d0)
    check('16a T+1：当天不能卖', ok is False, why)
    ok, why = S.should_sell(22.40, entry, d1, d0)
    check('16b 跌破前低 → 卖出', ok is True and '止损' in why, why)
    ok, why = S.should_sell(30.10, entry, d1, d0)
    check('16c 到压力区 → 卖出', ok is True and '止盈' in why, why)
    ok, why = S.should_sell(26.00, entry, d1, d0)
    check('16d 中间价 → 不卖', ok is False, why)

    print('\n[17] 持仓放量减仓（当日量 > 2×MA10 → 卖 1/3）')
    check('17a 1.5倍均量 → 不减', S.vol_exceed(1500.0, 1000.0) is False)
    check('17b 正好2倍均量 → 不减（严格大于才减）',
          S.vol_exceed(2000.0, 1000.0) is False)
    check('17c 2.5倍均量 → 减', S.vol_exceed(2500.0, 1000.0) is True)
    check('17d 均量为0/缺失 → 不减',
          S.vol_exceed(2500.0, 0.0) is False and S.vol_exceed(2500.0, None) is False)

    check('17e 300股 → 卖100股', S.reduce_shares(300) == 100)
    check('17f 1000股 → 卖300股', S.reduce_shares(1000) == 300)
    check('17g 1200股 → 卖400股', S.reduce_shares(1200) == 400)
    check('17h 200股（1/3不足1手）→ 卖一半 100股', S.reduce_shares(200) == 100)
    check('17i 150股（卖一半后剩75股不足1手）→ 全卖 150股', S.reduce_shares(150) == 150)
    check('17i2 200股第一次卖100，剩100股再触发 → 全卖100股',
          S.reduce_shares(200) == 100 and S.reduce_shares(100) == 100)
    check('17i3 100股（只有1手）→ 一次全卖 100股', S.reduce_shares(100) == 100)
    check('17j 300股减完还剩200股（不会清仓）',
          S.reduce_shares(300) < 300 and 300 - S.reduce_shares(300) > 0)
    # 份额按【最初仓位】算，不按剩余：最初 1200，剩 600 → 卖 400（不是 200）
    check('17k 最初1200/剩600 → 卖400（按最初仓位）',
          S.reduce_shares(600, 1200) == 400)
    # 1/3 最初仓位 ≥ 剩余 → 改卖一半；剩的还有 1 手就留着
    check('17l 最初1200/剩300 → 卖150（剩150仍≥1手）',
          S.reduce_shares(300, 1200) == 150
          and 300 - S.reduce_shares(300, 1200) >= 100)
    # 到目标价：卖到只剩 1/3 最初仓位，已卖部分抵扣
    check('17m 最初1000/已减300 → 再卖300（累计600，留400）',
          S.tp_part_shares(1000, 300, 700) == 300)
    check('17n 最初1000/没减过 → 卖600（留400）',
          S.tp_part_shares(1000, 0, 1000) == 600)
    check('17o 最初1000/已减600 → 已够2/3，不再卖',
          S.tp_part_shares(1000, 600, 400) == 0)

    print('\n[18] 急跌三条口径（可开关）')
    g0, f0 = S.REQUIRE_GAP, S.REQUIRE_FIRST_DROP
    try:
        # 18a/18b 首尾相接（重合 0）三连阴：按"重合上限"新口径 → 算急跌
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(30.00, 29.60), bar(29.60, 29.20), bar(29.20, 28.80)])
        S.REQUIRE_GAP = True
        check('18a 首尾相接（重合0）→ 算急跌', S.is_sharp_decline(o, c, 7) is True)
        S.REQUIRE_GAP = False
        check('18b 关掉缺口要求 → 仍算急跌', S.is_sharp_decline(o, c, 7) is True)
        S.REQUIRE_GAP = True

        # 18b2 每根小幅重叠 0.20（约 0.7%×29 元）→ 仍在 1% 以内 → 算
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(30.00, 29.60), bar(29.80, 29.00), bar(29.20, 28.40)])
        check('18b2 小幅重叠 0.20（<1%）→ 算急跌',
              S.is_sharp_decline(o, c, 7) is True,
              'ov=%s,%s 限=%s' % (S.body_overlap(o, c, 5, 6),
                                  S.body_overlap(o, c, 6, 7), S.PCT * c[7]))

        # 18b3 重叠 1.00（约 3.3%×30 元）> 1% → 不算；关掉 REQUIRE_GAP 才算
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(30.00, 29.60), bar(30.60, 29.00), bar(29.00, 28.40)])
        check('18b3 重叠 1.00（>1%）→ 不算急跌',
              S.is_sharp_decline(o, c, 7) is False)
        S.REQUIRE_GAP = False
        check('18b4 关掉缺口要求 → 算急跌', S.is_sharp_decline(o, c, 7) is True)
        S.REQUIRE_GAP = True

        # 18c 跳空三连阴（每根之间实体缺口 > 1%）→ 算
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(29.50, 29.00), bar(28.60, 28.10), bar(27.70, 27.20)])
        check('18c 跳空三连阴 → 算急跌', S.is_sharp_decline(o, c, 7) is True)

        # 18d/18e 跳空三连阴，但第一根只跌 0.34% 且没破前低
        rise = [bar(28.00 + 0.10 * i, 28.00 + 0.10 * i) for i in range(20)]
        o, c, h, l, v = mk(rise +
                           [bar(29.90, 29.80), bar(29.50, 29.20), bar(28.90, 28.60)])
        S.REQUIRE_FIRST_DROP = True
        check('18d 第一根跌幅<1%且没破前低 → 不算',
              S.is_sharp_decline(o, c, 22) is False)
        S.REQUIRE_FIRST_DROP = False
        check('18e 关掉第一根要求 → 算急跌', S.is_sharp_decline(o, c, 22) is True)
        S.REQUIRE_FIRST_DROP = True

        # 18f 第一根只跌 0.67%，但收盘破了前 20 根最低收盘 → 算
        o, c, h, l, v = mk(pad(20, price=30.0) +
                           [bar(30.00, 29.80), bar(29.50, 29.10), bar(28.80, 28.40)])
        check('18f 第一根跌0.67%但破前低 → 算急跌',
              S.is_sharp_decline(o, c, 22) is True)

        # 18g 三根跌停板（第 2 根实体上沿压进第 1 根 1.00 > 1%）→ 跌停豁免 → 算
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(30.00, 27.00), bar(28.00, 24.30), bar(24.30, 21.87)])
        check('18g 跌停板豁免重叠 → 算急跌', S.is_sharp_decline(o, c, 7) is True,
              'overlap=%s limit=%s' % (S.body_overlap(o, c, 6, 7),
                                       S.is_limit_down(c, 7)))
    finally:
        S.REQUIRE_GAP, S.REQUIRE_FIRST_DROP = g0, f0

    print('\n[19] 站上 L 的那根上涨K线涨幅必须 > 1%')
    g1 = S.REQUIRE_STAND_GAIN
    try:
        S.REQUIRE_STAND_GAIN = True
        check('19a 涨幅 1.5% → 通过', S.stand_gain_ok(25.375, 25.0) is True)
        check('19b 涨幅正好 1% → 不通过（严格大于）',
              S.stand_gain_ok(25.25, 25.0) is False)
        check('19c 涨幅 0.28% → 不通过', S.stand_gain_ok(25.07, 25.0) is False)
        check('19d 下跌 -1.5% → 不通过', S.stand_gain_ok(24.625, 25.0) is False)
        check('19e 昨收缺失/为0 → 不通过',
              S.stand_gain_ok(25.5, None) is False and S.stand_gain_ok(25.5, 0.0) is False)
        S.REQUIRE_STAND_GAIN = False
        check('19f 关掉开关 → 只要价 > L 就通过', S.stand_gain_ok(24.95, 25.0) is True)
    finally:
        S.REQUIRE_STAND_GAIN = g1

    print('\n[20] ST / *ST 剔除')
    check('20a 名称带 ST → 是', S.is_st_name('ST康得') is True)
    check('20b 星号 ST → 是', S.is_st_name('*ST海润') is True)
    check('20c S*ST 也算', S.is_st_name('S*ST前锋') is True)
    check('20d 普通简称 → 不是', S.is_st_name('平安银行') is False)
    check('20e 空名称 → 不是', S.is_st_name(None) is False)
    check('20f is_st 标记为 True 的剔除',
          S.strip_st(['A.SH', 'B.SZ'], st_flags={'B.SZ': True}) == ['A.SH'])
    check('20g is_st 明确为 False 的保留（哪怕名字怪）',
          S.strip_st(['A.SH', 'B.SZ'], st_flags={'A.SH': False, 'B.SZ': False}) == ['A.SH', 'B.SZ'])
    check('20h 没有 is_st 时按名称剔除',
          S.strip_st(['A.SH', 'B.SZ'], names={'A.SH': '浦发银行', 'B.SZ': '*ST康得'}) == ['A.SH'])
    check('20i is_st=False 优先于名称（接口说不是 ST 就保留）',
          S.strip_st(['B.SZ'], names={'B.SZ': '*ST康得'}, st_flags={'B.SZ': False}) == ['B.SZ'])
    check('20j 两个信息都没有 → 原样保留（不乱删）',
          S.strip_st(['A.SH', 'B.SZ']) == ['A.SH', 'B.SZ'])
    e0 = S.EXCLUDE_ST
    try:
        S.EXCLUDE_ST = False
        check('20k 关掉开关 → 不剔除',
              S.strip_st(['B.SZ'], st_flags={'B.SZ': True}) == ['B.SZ'])
    finally:
        S.EXCLUDE_ST = e0

    print('\n[21] 止盈：到压力区卖到剩 1/3 最初仓位，剩下 1/3 跟 20 日线')
    check('21a 1000股 没减过仓 → 卖600', S.tp_part_shares(1000, 0, 1000) == 600)
    check('21b 1000股 已减300 → 只补300', S.tp_part_shares(1000, 300, 700) == 300)
    check('21c 1000股 已卖够600 → 不再卖', S.tp_part_shares(1000, 600, 400) == 0)
    check('21d 700股 已减300 → 补到600，卖300',
          S.tp_part_shares(1000, 300, 700) == 300)
    check('21e 300股 没减过 → 卖200（留1手）', S.tp_part_shares(300, 0, 300) == 200)
    check('21f 0股 → 0', S.tp_part_shares(0, 0, 0) == 0)
    check('21f2 500股 没减过 → 卖300（取整手）', S.tp_part_shares(500, 0, 500) == 300)

    ent = {'p_low': 24.0, 'target': 27.95, 'buy': 25.0}
    d0 = datetime.date(2024, 6, 3)
    bd = datetime.date(2024, 5, 30)
    check('21g 到压力区且站上20日线 → 只卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=26.98)[0] == 'part')
    check('21h 到压力区但价 == 20日线 → 还在容差内 → 仍卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=27.95)[0] == 'part')
    check('21i 到压力区但已跌破20日线×0.99（没站上）→ 当天全卖，不留尾巴',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=28.50)[0] == 'all')
    check('21i2 刚好压在容差线上（既不高于也不低于）→ 仍卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd,
                          ma20=27.95 / 0.99)[0] == 'part')
    check('21j 到压力区但拿不到20日线 → 全卖',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=None)[0] == 'all')
    check('21k 压力区尾巴 跌破20日线 → 照旧清掉（不需要先突破）',
          S.sell_decision(26.00, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == 'all')
    fe = lambda **kw: dict(ent, tp2_done=True, target_src=S.SRC_FALLBACK, **kw)
    check('21k2 兜底尾巴 从没突破过 + 仍在成本上方 → 跌破均线也不管',
          S.sell_decision(26.00, fe(), d0, bd, ma20=26.98)[0] == '')
    check('21k3 兜底尾巴 从没突破过 + 已跌破成本价 → 全卖（止损:跌破成本价）',
          S.sell_decision(24.50, fe(), d0, bd, ma20=26.98)[1] == '止损:跌破成本价')
    check('21l 兜底尾巴 站上20日线 → 打上 tail_armed、继续持有',
          (lambda e: (S.sell_decision(27.50, e, d0, bd, ma20=26.98)[0] == ''
                      and e.get('tail_armed') is True))(fe()))
    check('21l2 兜底尾巴 已经突破过 → 重新跌破 MA20×0.99 就清掉',
          S.sell_decision(26.60, fe(tail_armed=True), d0, bd, ma20=26.98)[0] == 'all')
    check('21l3 兜底尾巴 已经突破过 → 还在均线上方 → 继续拿',
          S.sell_decision(27.20, fe(tail_armed=True), d0, bd, ma20=26.98)[0] == '')
    check('21m 卖过2/3后 跌破前低 → 照样止损',
          S.sell_decision(23.90, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == 'all')
    check('21n T+1 当天不能卖',
          S.sell_decision(27.95, dict(ent), d0, d0, ma20=26.98)[0] == '')
    f0 = S.TP_FOLLOW_MA
    try:
        S.TP_FOLLOW_MA = False
        check('21o 关掉开关 → 到压力区仍全清（旧行为）',
              S.sell_decision(27.95, dict(ent), d0, bd, ma20=26.98)[0] == 'all')
    finally:
        S.TP_FOLLOW_MA = f0

    # ---- 120 日高点兜底的目标价：不看 MA20（"跌破均线就全卖"这条不适用） ----
    fent = dict(ent, target=27.60, target_src=S.SRC_FALLBACK)
    check('21p 兜底目标到价 + 站上20日线 → 卖 2/3 留尾巴',
          S.sell_decision(27.60, dict(fent), d0, bd, ma20=26.98)[0] == 'part')
    check('21p2 兜底目标到价 + 已跌破20日线 → 仍然卖 2/3（不因均线全卖）',
          S.sell_decision(27.60, dict(fent), d0, bd, ma20=28.50)[0] == 'part')
    check('21p3 兜底目标到价的 reason 说明是 120 日高点',
          '120日高点' in S.sell_decision(27.60, dict(fent), d0, bd,
                                          ma20=28.50)[1])
    check('21q 兜底目标到价 + 拿不到均线 → 全卖（这条不变）',
          S.sell_decision(27.60, dict(fent), d0, bd, ma20=None)[0] == 'all')
    check('21r 兜底目标没到 → 不动',
          S.sell_decision(27.50, dict(fent), d0, bd, ma20=26.98)[0] == '')
    check('21s 压力区目标 + 已跌破20日线 → 当天全卖（这条只给压力区用）',
          S.sell_decision(27.95, dict(ent, target_src=S.SRC_ZONE), d0, bd,
                          ma20=28.50)[0] == 'all')
    check('21t 兜底目标但已跌破前低 → 止损优先',
          S.sell_decision(23.90, dict(fent), d0, bd, ma20=26.98)[1] ==
          '止损:跌破前低')

    print('\n[22] 20 日均线跌破容差 1%（价 < MA20×0.99 才算跌破）')
    check('22a 容差线 = MA20×0.99', abs(S.ma_band(26.98) - 26.7102) < 1e-6,
          str(S.ma_band(26.98)))
    check('22b 压力区尾巴 价 26.80（在容差内）→ 继续持有',
          S.sell_decision(26.80, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == '')
    check('22c 压力区尾巴 价 26.70（跌破容差线 26.71）→ 清仓',
          S.sell_decision(26.70, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == 'all')
    check('22d 到压力区时价 27.95 在均线 28.00 下方但只差 0.18% → 仍卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=28.00)[0] == 'part')
    check('22e 到压力区时价 27.95 比均线 28.50 低 1.9%（跌破容差线）→ 全卖',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=28.50)[0] == 'all')
    t0 = S.MA20_TOL
    try:
        S.MA20_TOL = 0.02
        check('22f 容差改成 2% → 26.60 不再算跌破（26.44 以下才算）',
              S.sell_decision(26.60, dict(ent, tp2_done=True, target_src=S.SRC_FALLBACK,
                                          tail_armed=True), d0, bd, ma20=26.98)[0] == '')
    finally:
        S.MA20_TOL = t0

    print('\n[23] 主板识别（沪 600/601/603/605 + 深 000/001/002/003，排除创业板/科创板/北交所/B股）')
    check('23a 600000.XSHG（沪主板）→ 是', S.is_main_board('600000.XSHG') is True)
    check('23b 601318.XSHG（沪主板）→ 是', S.is_main_board('601318.XSHG') is True)
    check('23c 603288.XSHG（沪主板）→ 是', S.is_main_board('603288.XSHG') is True)
    check('23d 605499.XSHG（沪主板）→ 是', S.is_main_board('605499.XSHG') is True)
    check('23e 000001.XSHE（深主板）→ 是', S.is_main_board('000001.XSHE') is True)
    check('23f 001979.XSHE（深主板）→ 是', S.is_main_board('001979.XSHE') is True)
    check('23g 002415.XSHE（原中小板，现属深主板）→ 是', S.is_main_board('002415.XSHE') is True)
    check('23h 003816.XSHE（深主板）→ 是', S.is_main_board('003816.XSHE') is True)
    check('23i 300750.XSHE（创业板）→ 否', S.is_main_board('300750.XSHE') is False)
    check('23j 301029.XSHE（创业板）→ 否', S.is_main_board('301029.XSHE') is False)
    check('23k 688981.XSHG（科创板）→ 否', S.is_main_board('688981.XSHG') is False)
    check('23l 689009.XSHG（科创板）→ 否', S.is_main_board('689009.XSHG') is False)
    check('23m 830799.XSHE（北交所）→ 否', S.is_main_board('830799.XSHE') is False)
    check('23n 900901.XSHG（沪B股）→ 否', S.is_main_board('900901.XSHG') is False)
    check('23o 不带后缀的 002415 → 是', S.is_main_board('002415') is True)
    check('23p None / 空串 / 乱码 → 否',
          S.is_main_board(None) is False and S.is_main_board('') is False
          and S.is_main_board('ABCDEF') is False)

    print('\n[24] 排除上市未满 3 年（1095 个自然日）')
    ref = datetime.date(2024, 6, 1)
    check('24a 恰好满 1095 天 → 纳入',
          S.listed_long_enough(ref - datetime.timedelta(days=1095), ref) is True)
    check('24b 1094 天（差一天）→ 剔除',
          S.listed_long_enough(ref - datetime.timedelta(days=1094), ref) is False)
    check('24c 上市 2 年 → 剔除',
          S.listed_long_enough(ref - datetime.timedelta(days=730), ref) is False)
    check('24d 上市 8 年 → 纳入',
          S.listed_long_enough(ref - datetime.timedelta(days=2920), ref) is True)
    check('24e 上市日期缺失 → 剔除（拿不准就不买）',
          S.listed_long_enough(None, ref) is False)
    check('24f 参考日期缺失 → 剔除',
          S.listed_long_enough(ref - datetime.timedelta(days=2000), None) is False)
    check('24g 乱码日期 → 剔除',
          S.listed_long_enough('not-a-date', ref) is False)
    check('24h 天数阈值可改：days=180 → 半年前的票也算老股',
          S.listed_long_enough(ref - datetime.timedelta(days=200), ref, days=180) is True)
    check('24i 时间倒挂（上市日期在未来）→ 剔除',
          S.listed_long_enough(ref + datetime.timedelta(days=10), ref) is False)

    print('\n' + '=' * 60)
    total = PASSED[0] + len(FAILED)
    if FAILED:
        print('结果：%d/%d 通过，失败 %d 项：%s'
              % (PASSED[0], total, len(FAILED), ', '.join(FAILED)))
        return 1
    print('结果：%d/%d 全部通过 ✅' % (PASSED[0], total))
    return 0


if __name__ == '__main__':
    sys.exit(run())
