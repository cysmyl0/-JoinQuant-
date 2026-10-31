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
 10  窗口内已经站上过 L → None（不追）
 11  急跌：连跌 4 根累计 -14% → True；只连跌 2 根 → False
 12  量能三态：等于均量 / 适中 / 2 倍均量
 13  不创新低
 14  盈亏比与最近压力区
 15  强压力区：三根放量K线价格区间重合 / 影线重合实体不重合也算 / 只有2根不算 /
      最高价之前的重合不算 / 单根2倍量整根算 / 没有放量K线则无
 16  卖出逻辑：T+1、止损、止盈
 17  持仓放量减仓：当日量 > 2×MA10 才减、1/3 取整到 100 股、不足 2 手不减
 18  急跌三条口径：首尾相接不算 / 跳空才算 / 第一根不足1%且没破前低不算 /
      破了前低就算 / 跌停板豁免缺口
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

    # 2 间隙 0.20 < 0.254（1%×25.40）→ 无效
    o2, c2, _, _, _ = mk([bar(27.00, 26.00), bar(25.80, 25.40)])
    check('2 实体间隙不足', S.is_valid_bear(o2, c2, 1) is False, 'gap=0.20 need 0.254')
    # 对照：间隙 0.30 > 0.254 → 有效
    o3, c3, _, _, _ = mk([bar(27.00, 26.00), bar(25.70, 25.40)])
    check('2b 实体间隙足够 → 有效', S.is_valid_bear(o3, c3, 1) is True)

    # 3 跌幅 0.39% ≤ 1% → 无效
    o4, c4, _, _, _ = mk([bar(27.00, 26.00), bar(25.60, 25.50)])
    check('3 实体跌幅不足1%', S.is_valid_bear(o4, c4, 1) is False, 'drop=0.39%')

    # 4 跌停豁免：实体零间隙但跌幅 10%
    o5, c5, _, _, _ = mk([bar(27.00, 26.00), bar(26.00, 23.40)])
    check('4 跌停板豁免', S.is_valid_bear(o5, c5, 1) is True,
          'is_limit_down=%s' % S.is_limit_down(c5, 1))

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
          and S.window_size(c, L_IDX) == 4)

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
          and S.window_size(c, L_IDX) == 6)

    # 10 窗口内已站上过 L → 结构已触发，不再追
    rows10 = BASE + [bar(25.10, 25.10), bar(25.00, 25.00)]
    o, c, h, l, v = mk(rows10)
    check('10 已触发不追', S.detect_setup(o, c, h, l, v) is None, 'close>L at idx34')

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

    print('\n[15] 强压力区（价格区间重合，含影线）')
    V0 = 1200.0          # 买入当天量：放量K线 2000 > 1200，但 2000 < 2×1200=2400（避免触发2倍量）

    # 15a 三根放量K线的 [最低价,最高价] 交集 = [25.0, 25.1]
    rows = pad(10, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)          # 上一个最高价在这根
    rows += [
        (24.90, 25.10, 25.20, 24.80, 2000.0),
        (25.00, 25.05, 25.10, 24.90, 2000.0),
        (25.05, 25.20, 25.30, 25.00, 2000.0),
        (25.20, 25.20, 25.40, 25.10, 1000.0),           # 不放量，不参与
    ]
    o, c, h, l, v = mk(rows)
    check('15a 峰值定位正确', S.find_peak_idx(h) == 0, 'peak=%d' % S.find_peak_idx(h))
    zones = S.find_strong_zones(h, l, v, v0=V0)
    check('15a 三根放量区间重合 → 25.00~25.10',
          len(zones) == 1 and abs(zones[0][0] - 25.0) < 1e-9
          and abs(zones[0][1] - 25.1) < 1e-9, 'zones=%s' % zones)

    # 15b 实体完全不重合，但上/下影线重合 → 仍然算强压力区（关键：不只看收盘价）
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [
        (24.00, 24.50, 25.00, 23.80, 2000.0),           # 实体24.0~24.5，上影到25.0
        (25.20, 25.50, 25.60, 24.90, 2000.0),           # 实体25.2~25.5，下影到24.9
        (24.80, 25.00, 25.10, 24.40, 2000.0),
    ]
    o, c, h, l, v = mk(rows)
    zones = S.find_strong_zones(h, l, v, v0=V0)
    check('15b 影线重合、实体不重合 → 仍算压力区',
          len(zones) == 1 and abs(zones[0][0] - 24.9) < 1e-9
          and abs(zones[0][1] - 25.0) < 1e-9, 'zones=%s' % zones)

    # 15c 只有两根放量K线重合 → 不够三根，不算
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [
        (24.00, 24.50, 25.00, 23.80, 2000.0),
        (25.20, 25.50, 25.60, 24.90, 2000.0),
        (24.80, 25.00, 25.10, 24.40, 1000.0),           # 第三根不放量
    ]
    o, c, h, l, v = mk(rows)
    check('15c 只有2根放量 → 不算', S.find_strong_zones(h, l, v, v0=V0) == [],
          'zones=%s' % S.find_strong_zones(h, l, v, v0=V0))

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
    check('15d 最高价之前的重合不算', S.find_strong_zones(h, l, v, v0=V0) == [],
          'zones=%s' % S.find_strong_zones(h, l, v, v0=V0))

    # 15e 单根 2 倍量 → 整根 [最低价, 最高价] 都算压力区
    rows = pad(6, price=27.0, vol=1000.0)
    rows[0] = (30.0, 30.0, 30.5, 29.5, 1000.0)
    rows += [(26.0, 26.1, 26.2, 25.8, 2500.0)]
    o, c, h, l, v = mk(rows)
    zones = S.find_strong_zones(h, l, v, v0=V0)
    check('15e 单根2倍量 → 25.80~26.20',
          len(zones) == 1 and abs(zones[0][0] - 25.8) < 1e-9
          and abs(zones[0][1] - 26.2) < 1e-9, 'zones=%s' % zones)

    # 15f v0 太大（没有K线放量）→ 无压力区
    o, c, h, l, v = mk(rows)
    check('15f 没有放量K线 → 无压力区',
          S.find_strong_zones(h, l, v, v0=5000.0) == [])

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
    check('17h 200股 → 至少卖1手', S.reduce_shares(200) == 100)
    check('17i 150股（不足2手）→ 不减', S.reduce_shares(150) == 0)
    check('17j 300股减完还剩200股（不会清仓）',
          S.reduce_shares(300) < 300 and 300 - S.reduce_shares(300) > 0)

    print('\n[18] 急跌三条口径（可开关）')
    g0, f0 = S.REQUIRE_GAP, S.REQUIRE_FIRST_DROP
    try:
        # 18a/18b 首尾相接（实体零缺口）三连阴：按原文不算急跌，关掉缺口要求才算
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(30.00, 29.60), bar(29.60, 29.20), bar(29.20, 28.80)])
        S.REQUIRE_GAP = True
        check('18a 首尾相接无缺口 → 不算急跌', S.is_sharp_decline(o, c, 7) is False)
        S.REQUIRE_GAP = False
        check('18b 关掉缺口要求 → 算急跌', S.is_sharp_decline(o, c, 7) is True)
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

        # 18g 三根跌停板（实体完全重叠，零缺口）→ 跌停豁免 → 算
        o, c, h, l, v = mk(pad(5, price=30.0) +
                           [bar(30.00, 27.00), bar(27.00, 24.30), bar(24.30, 21.87)])
        check('18g 跌停板豁免缺口 → 算急跌', S.is_sharp_decline(o, c, 7) is True)
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

    print('\n[21] 止盈：到压力区卖 2/3，剩下 1/3 跟 20 日线')
    check('21a 1000股 → 卖600', S.tp_sell_shares(1000) == 600)
    check('21b 500股 → 卖300（取整手）', S.tp_sell_shares(500) == 300)
    check('21c 300股 → 卖200', S.tp_sell_shares(300) == 200)
    check('21d 200股 → 卖100（剩1手）', S.tp_sell_shares(200) == 100)
    check('21e 100股 → 不够拆，全卖', S.tp_sell_shares(100) == 100)
    check('21f 0股 → 0', S.tp_sell_shares(0) == 0)

    ent = {'p_low': 24.0, 'target': 27.95, 'buy': 25.0}
    d0 = datetime.date(2024, 6, 3)
    bd = datetime.date(2024, 5, 30)
    check('21g 到压力区且站上20日线 → 只卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=26.98)[0] == 'part')
    check('21h 到压力区但价 == 20日线 → 还在容差内 → 仍卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=27.95)[0] == 'part')
    check('21i 到压力区但价格在20日线下方 → 全卖',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=28.50)[0] == 'all')
    check('21j 到压力区但拿不到20日线 → 全卖',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=None)[0] == 'all')
    check('21k 卖过2/3后 跌破20日线 → 清掉剩下的1/3',
          S.sell_decision(26.00, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == 'all')
    check('21l 卖过2/3后 仍在20日线上方 → 继续持有',
          S.sell_decision(27.50, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == '')
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

    print('\n[22] 20 日均线跌破容差 1%（价 < MA20×0.99 才算跌破）')
    check('22a 容差线 = MA20×0.99', abs(S.ma_band(26.98) - 26.7102) < 1e-6,
          str(S.ma_band(26.98)))
    check('22b 尾巴价 26.80（在容差内）→ 继续持有',
          S.sell_decision(26.80, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == '')
    check('22c 尾巴价 26.70（跌破容差线 26.71）→ 清仓',
          S.sell_decision(26.70, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == 'all')
    check('22d 到压力区时价 27.95 在均线 28.00 下方但只差 0.18% → 仍卖 2/3',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=28.00)[0] == 'part')
    check('22e 到压力区时价 27.95 比均线 28.50 低 1.9% → 全卖',
          S.sell_decision(27.95, dict(ent), d0, bd, ma20=28.50)[0] == 'all')
    t0 = S.MA20_TOL
    try:
        S.MA20_TOL = 0.02
        check('22f 容差改成 2% → 26.60 不再算跌破（26.44 以下才算）',
              S.sell_decision(26.60, dict(ent, tp2_done=True), d0, bd, ma20=26.98)[0] == '')
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
