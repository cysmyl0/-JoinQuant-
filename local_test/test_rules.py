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


# 基础下跌结构：30 根横盘 + 4 根下跌，第 4 根（idx33）是有效大阴线
# （detect_setup 要求至少 20 根日线，所以前置 pad 用 30 根）
BASE = pad(30) + [
    bar(28.00, 27.10),   # idx30 跌
    bar(27.00, 26.10),   # idx31 跌（与前根实体重叠）
    bar(26.20, 25.20),   # idx32 跌（与前根实体重叠，不是 L）
    bar(24.90, 24.00),   # idx33 有效大阴线：跌幅3.75%，间隙0.30 > 0.01×24.00=0.24
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
    check('12a 等于5日均量 → 不买', S.volume_ok(1000, 1000, 1000) is False)
    check('12b 放量适中 → 买', S.volume_ok(1500, 1000, 1000) is True)
    check('12c 达到2倍10日均量 → 不买', S.volume_ok(2000, 1000, 1000) is False)
    check('12d 不到5日均量 → 不买', S.volume_ok(900, 1000, 1000) is False)

    check('13a 收盘价≥前低', S.no_new_low(23.00, 22.50) is True)
    check('13b 收盘价<前低', S.no_new_low(22.40, 22.50) is False)

    check('14a 盈亏比=2.0', abs(S.risk_reward(30.0, 25.0, 22.5) - 2.0) < 1e-9)
    check('14b 2.08≥2 → 通过', S.rr_ok(30.0, 25.0, 22.6) is True)
    check('14c 1.92<2 → 否决', S.rr_ok(30.0, 25.0, 22.4) is False)
    check('14d 取上方最近压力区的下沿',
          S.pick_target([(20.0, 21.0), (26.0, 27.0), (30.0, 31.0)], 25.0) == 26.0)
    check('14e 上方无压力区 → None',
          S.pick_target([(20.0, 21.0), (24.0, 24.5)], 25.0) is None)
    check('14f 买入价已在压力区内 → 取上沿',
          S.pick_target([(25.0, 25.1), (28.0, 28.5)], 25.05) == 25.1)

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
