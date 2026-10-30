# -*- coding: utf-8 -*-
"""
================================================================================
强势结构 · 聚宽(JoinQuant)回测策略   v1.0
================================================================================
规则来源：本地《总体原则：.txt》+ 用户逐条确认后的 v7 硬口径（见底部"规则对照表"）。

一句话逻辑：
    急跌 → 找到"有效大阴线 L"（L = 该阴线开盘价）→ 在 L 之后 4 根（有放缓时 6 根）
    窗口内，某天 14:55 价格站上 L 且量能适中、不创新低 → 买入；
    价格到上方最近的强压力区卖出，跌破前低止损。

【你定的硬口径（全部按此实现，无歧义）】
1.  L 的取法：下跌段中【最后一根】满足下面三条的阴线，L = 它的开盘价（实体上沿）
      a) 阴线：close < open
      b) 实体跌幅 > 1% 股价：(open - close) / close > 1%
      c) 与前一根实体不重叠 > 1% 股价：(前一根实体下沿 - 本根实体上沿) > 1% × close
         （跌停板豁免：本根跌幅 ≥ 9.8% 时，c) 不作要求）
2.  站上 L：收盘价 > L，严格大于，不含盘中，14:55 的价视为当日收盘价。
3.  窗口：从 L 之后第 1 根起数，含买入当天、不含 L。
       - 无放缓：4 根，即 L 后第 4 根仍未过 L 则作废
       - 有放缓：6 根。放缓 = L 之后出现连续 3 根 |涨跌幅| ≤ 1% 的窄幅 K 线（视为 1 根）
4.  量能：MA5(VOL) < 当日 VOL < 2 × MA10(VOL)    ← 必须放量过 5 日均量，但不到 2 倍 10 日均量
       （MA5/MA10 取截至前一根已收盘K线的均量；当日 VOL 用 14:55 时点的当日累计量估计全日量）
5.  不创新低：14:55 价 ≥ P_low，P_low = 从 L 到买入前一天的最低收盘价
6.  盈亏比：目标 = 买入价上方最近的强压力区；盈亏比 = (目标 - 买入) / (买入 - P_low) 必须 ≥ 2
7.  强压力区：窗口 = 从【上一个最高价那根】一直数到【昨天】—— 整个下跌阶段都算
       - 窗口内 ≥ 3 根【放量K线】的价格区间 [最低价, 最高价] 有重合 → 重合的那一段就是强压力区
       - 价格区间用整根K线的最高/最低，**影线和实体都算**（不是只看收盘价）
       - 放量 = 该根成交量 > 买入当天量 V0
       - 窗口内任意一根成交量 ≥ 2 × V0 → 这一根本身整段也算强压力区
       - 目标 = 买入价上方最近的那条压力区的【下沿】（价格第一次碰到压力区的价位）
8.  否决项：成交量 ≥ 2 倍 10 日均量的 K 线（买入当天）不买
9.  不用 ST / 市值 / 价格过滤
10. 所有买入和卖出都在每天 14:55 执行（1 分钟级回测 + run_daily 定时任务）
11. 持仓期间：某天成交量 > 2 × MA10(VOL)（与第 4 条同一条线的另一侧）→ 当天卖出 1/3 持仓
       - 先看止盈/止损，两者都没触发才减仓；同一天不会既减仓又清仓
       - 1/3 向下取整到 100 股整手；持仓不足 200 股不减（留给止盈/止损一次清掉）
       - 同一条规则可以多次触发：每次放量都是再卖 1/3（按当时的剩余持仓算）

【用户已默认接受的实现假设（可在一处改）】
- 急跌条件（原文三条，逐条落到代码里，后两条可用开关关掉）：
    ① 至少 3 根连续收跌，且区间累计跌幅 ≥ 3%（把"下跌比较猛"量化）
    ② 段内每相邻两根K线实体不重叠 > 1% 股价（跳空下跌），跌停板豁免   ← REQUIRE_GAP
    ③ 第一根跌幅 > 1% 或 收盘破前 20 根最低收盘                        ← REQUIRE_FIRST_DROP
- A 股 1 手 = 100 股，手工取整；单票仓位上限 25%，最多同时持有 5 只
- 卖出遇到跌停（价格 ≤ 跌停价×1.001）、买入遇到涨停（价格 ≥ 涨停价×0.999）则放弃该笔
================================================================================
"""

import numpy as np
import pandas as pd

try:                                     # 聚宽环境
    from jqdata import *                 # noqa: F401,F403
except Exception:                        # 本地跑单测时允许缺失
    pass


# =============================================================================
# 一、参数区（所有可调参数都在这里，改完重新回测即可）
# =============================================================================

# ---------- 规则参数（对应你确认的口径，一般不要改） ----------
PCT          = 0.01     # "1% 股价"的百分比
BODY_GAP_PCT = 0.01     # 实体不重叠要求的比例（1%）
LIMIT_DROP   = 0.098    # 跌停豁免阈值：单根跌幅 ≥ 9.8% 视为跌停
NARROW_PCT   = 0.01     # 放缓：单根涨跌幅绝对值 ≤ 1%
NARROW_RUN   = 3        # 放缓：连续 3 根
W_NO_SLOW    = 4        # 无放缓 → 窗口 4 根
W_SLOW       = 6        # 有放缓 → 窗口 6 根
VOL_S        = 5        # 短均量 5 日
VOL_L        = 10       # 长均量 10 日
VOL_CAP      = 2.0      # 2 倍量
RR_MIN       = 2.0      # 盈亏比 2:1
DECLINE_BARS = 3        # 急跌：至少连续下跌根数
DECLINE_PCT  = 0.03     # 急跌：累计跌幅至少 3%（把原文"下跌比较猛"量化）
REQUIRE_GAP        = True   # 急跌：下跌段每相邻两根K线实体必须不重叠 >1%（跳空下跌），跌停豁免
REQUIRE_FIRST_DROP = True   # 急跌：下跌段第一根跌幅 >1% 或 收盘破前低
FIRST_DROP_BACK    = 20     # "破前低"参照的前 N 根最低收盘价
LOOKBACK_L   = 10       # 只在最近 10 根里找有效大阴线 L（否则 L 太老无意义）
HIGH_BACK    = 250      # 往前找"上一个最高价"的回溯根数（压力区窗口 = 最高价那根 → 昨天）

# ---------- 选股 / 仓位 / 费率 ----------
UNIVERSE     = 'hs300'    # 'all' 全市场(约5000只) | 'hs300' | 'zz500' | 'zz1000'
IDX_MAP      = {'hs300': '000300.XSHG', 'zz500': '000905.XSHG', 'zz1000': '000852.XSHG'}
MIN_LIST_DAYS = 500     # 上市满 500 个自然日（约 340 个交易日）才纳入
BARS_SCAN    = 60       # 第一步扫描用日线根数（够算 detect_setup + 均量）
BARS_FULL    = 300      # 第二轮算强压力区用日线根数（需覆盖 HIGH_BACK）
MAX_CAND     = 500      # 单日候选上限（控制 14:55 的耗时）
MAX_POS      = 5        # 最多同时持有 5 只
MAX_POS_PCT  = 0.25     # 单票最多占总资产 25%
SLIP_PCT     = 0.002    # 滑点 0.2%
TAX          = 0.0005   # 卖出印花税 0.05%
COMMISSION   = 0.0003   # 佣金 万3
MIN_COMM     = 5        # 最低佣金 5 元
MAX_HOLD_DAYS = 0       # 最大持有天数，0 = 不启用

# ---------- 持仓中的减仓规则（m00216 新增） ----------
REDUCE_RATIO   = 1.0 / 3.0   # 当日量 > 该倍数时，卖出 1/3 持仓
REDUCE_VOL_CAP = 2.0         # 触发减仓的量能倍数：当日量 > 2 × MA10(量)
REDUCE_LOT     = 100         # 减仓股数取整手

USE_MINUTE_VOL = True   # True: 用 1 分钟线累加当日量（更准）；False: 用 attribute_history(1,'1d')

# ---------- 调试开关 ----------
VERBOSE = True          # 每天打印候选数量 / 买入卖出明细


# =============================================================================
# 二、纯函数层（不依赖聚宽，本地可单测）
# =============================================================================

def is_bear(o, c, i):
    """第 i 根是否为阴线。"""
    return c[i] < o[i]


def is_limit_down(c, i):
    """第 i 根是否近似跌停（用于实体不重叠豁免）。"""
    if i < 1:
        return False
    return c[i] <= c[i - 1] * (1.0 - LIMIT_DROP)


def body_low(o, c, i):
    return min(o[i], c[i])


def body_top(o, c, i):
    return max(o[i], c[i])


def is_valid_bear(o, c, i):
    """第 i 根是否为"有效大阴线"（阴线 + 实体跌幅>1% + 与前一根实体不重叠>1%，跌停豁免）。"""
    if i < 1:
        return False
    if not is_bear(o, c, i):
        return False
    if (o[i] - c[i]) / c[i] <= PCT:                 # 实体跌幅不够
        return False
    gap = body_low(o, c, i - 1) - body_top(o, c, i)  # 与前一根实体的垂直间隙
    if gap <= PCT * c[i] and not is_limit_down(c, i):
        return False
    return True


def find_L(o, c, lookback=LOOKBACK_L):
    """
    在最近 lookback 根里找【最后一根】有效大阴线，返回其索引；找不到返回 None。
    L 的价格 = 该K线开盘价（由调用方取 o[idx]）。
    """
    n = len(c)
    if n < 3:
        return None
    lo = max(1, n - lookback)
    for i in range(n - 1, lo - 1, -1):
        if is_valid_bear(o, c, i):
            return i
    return None


def decline_run_start(c, L_idx):
    """
    从 L 往回找"连续收跌"段的起点：返回段内第一根的索引。
    段内每根都满足 close[t] < close[t-1]，一直连到 close=close 或 收涨 为止。
    """
    j = L_idx
    while j >= 1 and c[j] < c[j - 1]:
        j -= 1
    return j + 1


def has_body_gaps(o, c, start, end):
    """
    下跌段 [start, end] 内，每相邻两根K线的实体都不重叠（间隙 > 1% 股价）。
    跌停板豁免（原文"跌停板可以除外"）。
    """
    for t in range(start + 1, end + 1):
        gap = body_low(o, c, t - 1) - body_top(o, c, t)
        if gap <= PCT * c[t] and not is_limit_down(c, t):
            return False
    return True


def first_bar_sharp(o, c, start, back=FIRST_DROP_BACK):
    """
    下跌段第一根：跌幅 > 1% 或 收盘破前低（前 back 根的最低收盘）。
    原文："第一根 k 线下跌幅度是超过股价的 1% 或者破前低"。
    """
    if start < 1:
        drop_ok = (o[start] - c[start]) / c[start] > PCT
    else:
        drop_ok = (c[start - 1] - c[start]) / c[start] > PCT
    if drop_ok:
        return True
    lo = max(0, start - back)
    if lo >= start:
        return False
    return float(c[start]) < float(np.min(c[lo:start]))


def is_sharp_decline(o, c, L_idx):
    """
    急跌判定（按原文三条，可开关）：
      ① 至少 DECLINE_BARS 根连续收跌，且累计跌幅 ≥ DECLINE_PCT（"下跌比较猛"）
      ② REQUIRE_GAP=True 时：段内每相邻两根实体不重叠 > 1% 股价（跳空下跌，跌停豁免）
      ③ REQUIRE_FIRST_DROP=True 时：第一根跌幅 > 1% 或 破前低
    """
    if L_idx < 1:
        return False

    start = decline_run_start(c, L_idx)
    cnt = L_idx - start + 1
    if cnt < DECLINE_BARS:
        return False

    ref = float(c[start - 1]) if start >= 1 else float(c[start])
    drop = float(c[L_idx]) / ref - 1.0
    if (-drop) < DECLINE_PCT:
        return False

    if REQUIRE_GAP and not has_body_gaps(o, c, start, L_idx):
        return False
    if REQUIRE_FIRST_DROP and not first_bar_sharp(o, c, start):
        return False
    return True


def slow_run_ok(c, L_idx, n=None):
    """
    放缓判定：L 之后的窗口内，存在连续 NARROW_RUN 根 |涨跌幅| ≤ NARROW_PCT 的窄幅K线。
    n = 已收盘K线数量（索引 0..n-1）。
    """
    if n is None:
        n = len(c)
    start = L_idx + 1
    stop = min(L_idx + 1 + W_NO_SLOW, n - NARROW_RUN + 1)   # 只在"4根窗口"范围内找放缓
    for k in range(start, stop):
        if k - 1 < 0 or k + NARROW_RUN - 1 > n - 1:
            continue
        ok = True
        for t in range(k, k + NARROW_RUN):
            r = c[t] / c[t - 1] - 1.0
            if abs(r) > NARROW_PCT:
                ok = False
                break
        if ok:
            return True
    return False


def window_size(c, L_idx, n=None):
    """返回窗口根数：有放缓 6，无放缓 4。"""
    return W_SLOW if slow_run_ok(c, L_idx, n) else W_NO_SLOW


def detect_setup(o, c, h, l, v):
    """
    输入：已收盘日线（最后一根 = 昨天 T-1）的 numpy 数组。
    输出：None 或 dict，代表"今天(T)是可以触发买入的一根"。
          L / L_idx / p_low / wlen / wleft / v5 / v10

    做三件事：
      1. 找出有效大阴线 L，并确认急跌结构
      2. 确认窗口没作废：今天(T)在 L 之后第 1..wlen 根之内
      3. 确认此前没有已经站上过 L（站过就算结构已用掉，不追）
    """
    n = len(c)
    if n < 20:
        return None

    Li = find_L(o, c)
    if Li is None:
        return None
    if not is_sharp_decline(o, c, Li):
        return None

    L = float(o[Li])
    p_low = float(np.min(c[Li:]))          # 从 L 到昨天收盘的最低价（收盘价口径）

    # 窗口内此前已经站上过 L → 结构已经触发过，今天不再买
    for t in range(Li + 1, n):
        if c[t] > L:
            return None

    wlen = window_size(c, Li, n)
    wleft = Li + wlen - n                  # 今天(索引 n)是第几根：>=0 表示还在窗口内
    if wleft < 0:
        return None

    v5 = float(np.mean(v[n - VOL_S:])) if n >= VOL_S else None
    v10 = float(np.mean(v[n - VOL_L:])) if n >= VOL_L else None

    return {
        'L': L, 'L_idx': Li, 'p_low': p_low,
        'wlen': wlen, 'wleft': wleft,
        'v5': v5, 'v10': v10,
    }


def volume_ok(vol_today, v5, v10, cap=VOL_CAP):
    """量能条件：MA5 < 当日量 < cap × MA10，且不能 ≥ cap × MA10（否决项）。"""
    if v5 is None or v10 is None or v10 <= 0:
        return False
    if vol_today <= 0:
        return False
    return (vol_today > v5) and (vol_today < cap * v10)


def no_new_low(price, p_low):
    """不创新低：收盘价 ≥ 前低（收盘价口径）。"""
    return price >= p_low


def risk_reward(target, buy, p_low):
    """盈亏比 = (目标 - 买入) / (买入 - 止损)。止损在买入价之上或相等时返回 0（不可买）。"""
    risk = buy - p_low
    if risk <= 0:
        return 0.0
    return (target - buy) / risk


def rr_ok(target, buy, p_low, need=RR_MIN):
    if target is None or target <= buy:
        return False
    return risk_reward(target, buy, p_low) >= need


def find_peak_idx(h, back=HIGH_BACK):
    """
    "上一个最高价"：最近 back 根里的最高价（用 high，含上影线）所在位置。
    这是强压力区窗口的起点。
    """
    n = len(h)
    s = max(0, n - back)
    return s + int(np.argmax(np.asarray(h[s:], dtype=float)))


def _merge_zones(zones):
    """把重叠/相邻的价格区间合并，返回按下沿升序的 [(lo, hi), ...]。"""
    if not zones:
        return []
    zs = sorted(zones, key=lambda x: (x[0], x[1]))
    out = [[zs[0][0], zs[0][1]]]
    for lo, hi in zs[1:]:
        if lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(float(a), float(b)) for a, b in out]


def find_strong_zones(h, l, v, v0, back=HIGH_BACK, touch=3, vol_cap=VOL_CAP):
    """
    计算"强压力区"列表，每条是一个价格区间 [(lo, hi), ...]（按 lo 升序）。

    h/l/v   : 已收盘日线（最后一根 = 昨天 T-1，不含今天）
    v0      : 买入当天那根K线的成交量
    back    : 往前找"上一个最高价"的回溯根数

    窗口    : 从【最高价那根】一直到【昨天】—— 就是这一整段下跌阶段
    判定    : 窗口内 ≥ touch(3) 根【放量K线】的价格区间 [最低价, 最高价] 有重合
              → 重合的这一段就是强压力区。
              价格区间用整根K线的最高/最低（含上下影线），实体和影线都算数。
    放量    : 该根成交量 > v0
    例外    : 窗口内任意一根成交量 ≥ vol_cap × v0 → 这一根自己就整段算强压力区
    """
    n = len(h)
    if n < 5:
        return []
    peak = find_peak_idx(h, back)

    H = np.asarray(h[peak:], dtype=float)
    Lw = np.asarray(l[peak:], dtype=float)
    V = np.asarray(v[peak:], dtype=float)
    if len(H) == 0:
        return []

    v0 = float(v0)
    big = V >= vol_cap * v0        # 单根 2 倍量
    loud = V > v0                  # 放量（big 必然也放量）

    zones = []

    # ---------- 1. 三根以上放量K线的价格区间互相重合 ----------
    if int(loud.sum()) >= touch:
        los = Lw[loud]
        his = H[loud]
        pts = np.unique(np.concatenate([los, his]))
        if len(pts) >= 2:
            # 每两个相邻端点之间，覆盖数恒定（用中点判定）
            mids = (pts[:-1] + pts[1:]) / 2.0
            cov = ((los[None, :] <= mids[:, None]) &
                   (his[None, :] >= mids[:, None])).sum(axis=1)
            covered = cov >= touch
            k = 0
            while k < len(covered):
                if covered[k]:
                    j = k
                    while j + 1 < len(covered) and covered[j + 1]:
                        j += 1
                    zones.append((float(pts[k]), float(pts[j + 1])))
                    k = j + 1
                else:
                    k += 1
        # 几根K线只在某一个价位点上相交的情况
        cov_pt = ((los[None, :] <= pts[:, None]) &
                  (his[None, :] >= pts[:, None])).sum(axis=1)
        for p, cnt in zip(pts, cov_pt):
            if cnt >= touch and not any(lo <= p <= hi for lo, hi in zones):
                zones.append((float(p), float(p)))

    # ---------- 2. 单根 2 倍量：整根K线都算压力区 ----------
    for i in np.where(big)[0]:
        zones.append((float(Lw[i]), float(H[i])))

    return _merge_zones(zones)


def pick_target(zones, buy):
    """
    买入价上方【最近】的强压力区价位；没有则 None。
    - 若某压力区整段在买入价上方 → 取它的下沿（价格第一次碰到压力区的位置）
    - 若买入价已经落在某个压力区里面 → 取该区上沿
    """
    if not zones:
        return None
    best = None
    for lo, hi in zones:
        if hi < buy:                 # 整段在下方，不是上方的压力
            continue
        edge = lo if buy < lo else hi
        if edge <= buy:
            continue
        if best is None or edge < best:
            best = edge
    return best


def sell_allowed(buy_date, today):
    """A 股 T+1：买入当天不能卖。"""
    return buy_date is not None and buy_date < today


def should_sell(price, entry, today, buy_date):
    """
    返回 (是否卖出, 原因)。entry = {'p_low':..., 'target':..., 'buy_date':...}
    """
    if entry is None:
        return False, ''
    if not sell_allowed(buy_date, today):
        return False, ''
    if price <= entry['p_low']:
        return True, '止损:跌破前低'
    if price >= entry['target']:
        return True, '止盈:到压力区'
    if MAX_HOLD_DAYS and (today - buy_date).days >= MAX_HOLD_DAYS:
        return True, '时间止损'
    return False, ''


def vol_exceed(vol_today, v10, cap=REDUCE_VOL_CAP):
    """
    当日成交量是否 > cap × 10日均量（放量出货信号 → 减仓 1/3）。
    注意方向：买入时要求 当日量 < 2×MA10（低于这条才买），
             持仓时 当日量 > 2×MA10 就要减仓，两者是同一条线的两侧。
    """
    if vol_today is None or v10 is None:
        return False
    try:
        v10 = float(v10)
        vt = float(vol_today)
    except (TypeError, ValueError):
        return False
    if v10 <= 0 or vt <= 0:
        return False
    return bool(vt > cap * v10)


def reduce_shares(total_amount, ratio=REDUCE_RATIO, lot=REDUCE_LOT):
    """
    "卖出 1/3 持仓"要卖多少股：向下取整到 100 股整手。
    持仓不足 2 手时返回 0（不拆，留给止盈/止损一次清掉）。
    剩余股数永远 > 0，不会把仓位误清空。
    """
    total = int(total_amount)
    if total < 2 * lot:
        return 0
    # +1e-9 是为了避免 300*(1/3)=99.99999 被截成 0 手这种浮点误差
    sh = int(np.floor(total * float(ratio) / lot + 1e-9)) * lot
    if sh <= 0:
        sh = lot
    if sh >= total:
        sh = total - lot
    return int(sh)


# =============================================================================
# 三、聚宽回测框架部分
# =============================================================================

def initialize(context):
    # 基准与选项
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 费用与滑点
    set_order_cost(OrderCost(
        open_tax=0, close_tax=TAX,
        open_commission=COMMISSION, close_commission=COMMISSION,
        close_today_commission=0, min_commission=MIN_COMM,
    ), type='stock')
    set_slippage(PriceRelatedSlippage(SLIP_PCT))

    log.set_level('order', 'error')

    # 记录表
    g.entry = {}      # code -> {'L','p_low','target','buy','rr','L_idx','buy_date'}
    g.buy_date = {}   # code -> date
    g.stat = {'days': 0, 'cand': 0, 'buy': 0, 'sell_win': 0, 'sell_lose': 0,
              'skip': 0, 'reduce': 0}
    g.no_minute_vol = 0

    log.info('强势结构策略初始化完成 | 窗口: 无放缓%d根/有放缓%d根 | 盈亏比≥%.1f'
             % (W_NO_SLOW, W_SLOW, RR_MIN))
    log.info('量能条件: MA%d < 当日量 < %.1f×MA%d | 标的池: %s'
             % (VOL_S, VOL_CAP, VOL_L, UNIVERSE))

    # 全流程统一在 14:55 执行
    run_daily(trade_1455, time='14:55')


def trade_1455(context):
    """每天 14:55：先卖，再买。"""
    g.stat['days'] += 1
    today = context.current_dt.date()

    # ---------- 第 0 步：卖出（止盈/止损清仓 + 放量减仓 1/3） ----------
    held_codes = [s for s in context.portfolio.positions.keys()
                  if context.portfolio.positions[s].total_amount > 0]
    if held_codes:
        h_price, h_vol = _today_stats(held_codes, context)
        _do_sell(context, today, h_price, h_vol)

    # ---------- 第 1 步：全市场扫描，找候选 ----------
    codes = _get_universe(context)
    if not codes:
        return
    hist = _fetch_daily(codes, context.previous_date, BARS_SCAN)
    if not hist:
        return

    cands = []
    for code, df in hist.items():
        if len(df) < 20:
            continue
        try:
            o = df['open'].values.astype(float)
            c = df['close'].values.astype(float)
            h = df['high'].values.astype(float)
            l = df['low'].values.astype(float)
            v = df['volume'].values.astype(float)
            st = detect_setup(o, c, h, l, v)
        except Exception:
            continue
        if st is not None:
            cands.append((code, st))

    g.stat['cand'] += len(cands)
    if not cands:
        if VERBOSE and len(context.portfolio.positions) > 0:
            log.info('[%s] 无候选' % today)
        return
    if len(cands) > MAX_CAND:
        cands = sorted(cands, key=lambda x: x[1]['wleft'])[:MAX_CAND]

    # ---------- 第 2 步：取今天 14:55 的价格与累计成交量 ----------
    price, vol_today = _today_stats([x[0] for x in cands], context)

    # ---------- 第 3 步：三条入场条件筛选 ----------
    survivors = []
    for code, st in cands:
        p = price.get(code)
        vt = vol_today.get(code)
        if p is None or vt is None or p <= 0:
            continue
        if not (p > st['L']):                       # 条件①：站上 L（严格大于）
            continue
        if not volume_ok(vt, st['v5'], st['v10']):  # 条件②：量能 + 否决项
            continue
        if not no_new_low(p, st['p_low']):          # 条件③：不创新低
            continue
        survivors.append((code, st, p, vt))

    if not survivors:
        return
    if VERBOSE:
        log.info('[%s] 候选 %d 只 → 通过三条硬条件 %d 只'
                 % (today, len(cands), len(survivors)))

    # ---------- 第 4 步：取 300 根日线算强压力区与盈亏比 ----------
    full = _fetch_daily([x[0] for x in survivors], context.previous_date, BARS_FULL)

    picks = []
    for code, st, p, vt in survivors:
        df = full.get(code)
        if df is None or len(df) < 20:
            continue
        try:
            h = df['high'].values.astype(float)
            l = df['low'].values.astype(float)
            v = df['volume'].values.astype(float)
            zones = find_strong_zones(h, l, v, vt)
        except Exception:
            continue
        target = pick_target(zones, p)
        if target is None:
            continue
        rr = risk_reward(target, p, st['p_low'])
        if rr < RR_MIN:
            continue
        picks.append((rr, code, p, st, target, vt))

    if not picks:
        return
    picks.sort(key=lambda x: -x[0])

    # ---------- 第 5 步：下单 ----------
    _do_buy(context, today, picks)


def _get_universe(context):
    """标的池：剔除停牌。不做 ST/市值/价格过滤（按你的要求）。"""
    d = context.previous_date
    try:
        if UNIVERSE in IDX_MAP:
            codes = list(get_index_stocks(IDX_MAP[UNIVERSE], date=d))
        else:
            df = get_all_securities(types=['stock'], date=d)
            if len(df) == 0:
                return []
            cutoff = pd.Timestamp(d) - pd.Timedelta(days=MIN_LIST_DAYS)
            df = df[df['start_date'].apply(lambda x: pd.Timestamp(x) <= cutoff)]
            codes = list(df.index)
    except Exception as e:
        log.error('取标的池失败: %s' % e)
        return []

    cd = get_current_data()
    out = []
    for s in codes:
        try:
            if cd[s].paused:
                continue
        except Exception:
            continue
        out.append(s)
    return out


def _fetch_daily(codes, end_date, count):
    """
    批量取日线（前复权），返回 {code: DataFrame(open,close,high,low,volume)}。
    skip_paused=True：停牌日不产生K线。
    """
    res = {}
    if not codes:
        return res
    step = 800
    for i in range(0, len(codes), step):
        chunk = codes[i:i + step]
        try:
            df = get_price(chunk, end_date=end_date, count=count,
                           fields=['open', 'close', 'high', 'low', 'volume'],
                           skip_paused=True, fq='pre', panel=False)
        except Exception as e:
            log.warn('get_price 失败(%d~%d): %s' % (i, i + len(chunk), e))
            continue
        if df is None or len(df) == 0:
            continue
        try:
            for code, sub in df.groupby('code'):
                res[code] = sub
        except Exception:
            continue
    return res


def _today_stats(codes, context):
    """
    返回 (price_dict, volume_dict)：今天 14:55 时点的价格与当日累计成交量。
    成交量优先用 1 分钟线累加；失败则退回 attribute_history(1,'1d')。
    """
    price, vol = {}, {}
    if not codes:
        return price, vol

    cd = get_current_data()
    for s in codes:
        try:
            p = cd[s].last_price
            price[s] = float(p) if p else None
        except Exception:
            price[s] = None

    if USE_MINUTE_VOL:
        try:
            df = history(240, '1m', 'volume', codes, df=True, skip_paused=False)
            if df is not None and len(df) > 0:
                idx = pd.to_datetime(df.index)
                todays = idx.normalize() == pd.Timestamp(context.current_dt.date())
                sub = df.loc[todays]
                if len(sub) > 0:
                    for s in sub.columns:
                        try:
                            vol[s] = float(sub[s].fillna(0).sum())
                        except Exception:
                            pass
        except Exception as e:
            g.no_minute_vol += 1
            log.warn('分钟量获取失败(%s)，改用日线兜底' % e)

    # 兜底：日线最后一条
    for s in codes:
        if s in vol and vol[s] > 0:
            continue
        try:
            h = attribute_history(s, 1, '1d', ['volume'], skip_paused=True, df=False)
            vol[s] = float(h['volume'][-1])
        except Exception:
            vol[s] = None
    return price, vol


def _hist_vol_ma(code, n=VOL_L):
    """
    持仓股的 n 日均量（截至昨天，不含今天）——用于判断"当日量 > 2×MA10"。
    取不到返回 None。
    """
    try:
        h = attribute_history(code, n, '1d', ['volume'], skip_paused=True, df=False)
        arr = np.asarray(h['volume'], dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        if len(arr) == 0:
            return None
        return float(arr.mean())
    except Exception:
        return None


def _do_sell(context, today, price=None, vol_today=None):
    """
    卖出，14:55 执行，优先级：
      1) 到压力区 / 跌破前低 / 时间止损  → 全部清仓
      2) 当日成交量 > 2×MA10(量)         → 卖出 1/3 持仓（放量减仓）
    注意 2) 只在 1) 不成立时执行；同一天不会既减仓又清仓。
    """
    price = price or {}
    vol_today = vol_today or {}
    for s in list(context.portfolio.positions.keys()):
        pos = context.portfolio.positions[s]
        if pos.total_amount == 0:
            continue
        entry = g.entry.get(s)
        if entry is None:
            continue
        buy_date = g.buy_date.get(s)
        try:
            d = get_current_data()[s]
            p = d.last_price
            if d.paused or not p:
                continue
            # 跌停卖不出
            if d.low_limit and p <= d.low_limit * 1.001:
                continue
        except Exception:
            continue

        ok, why = should_sell(p, entry, today, buy_date)
        if ok:
            order_target(s, 0)
            ret = (p / entry['buy'] - 1.0) * 100 if entry['buy'] else 0.0
            g.stat['sell_win' if ret > 0 else 'sell_lose'] += 1
            log.info('卖出 %s @%.2f %s 收益%.2f%% (买%.2f 止损%.2f 目标%.2f)'
                     % (s, p, why, ret, entry['buy'], entry['p_low'], entry['target']))
            g.entry.pop(s, None)
            g.buy_date.pop(s, None)
            continue

        # ---------- 放量减仓：当日量 > 2 × MA10(量) → 卖 1/3 ----------
        if not sell_allowed(buy_date, today):
            continue
        vt = vol_today.get(s)
        v10 = _hist_vol_ma(s)
        if not vol_exceed(vt, v10):
            continue
        sh = reduce_shares(pos.total_amount)
        if sh <= 0:
            continue
        order_target(s, int(pos.total_amount - sh))
        g.stat['reduce'] += 1
        log.info('减仓 %s @%.2f 卖%d股(1/3持仓) 当日量%.0f > %.1f×MA%d(%.0f)'
                 % (s, p, sh, vt, REDUCE_VOL_CAP, VOL_L, v10))


def _do_buy(context, today, picks):
    """买入：按盈亏比从高到低，填满空仓位。"""
    held = [s for s in context.portfolio.positions.keys()
            if context.portfolio.positions[s].total_amount > 0]
    slots = MAX_POS - len(held)
    if slots <= 0 or not picks:
        return

    total_value = context.portfolio.total_value
    cd = get_current_data()
    bought = 0

    for rr, code, p, st, target, vt in picks:
        if slots <= 0:
            break
        if code in held:
            continue
        try:
            d = cd[code]
            if d.paused or not d.last_price:
                continue
            if d.high_limit and d.last_price >= d.high_limit * 0.999:   # 涨停买不到
                continue
        except Exception:
            continue

        cash = context.portfolio.available_cash
        per = min(cash / slots * 0.98, total_value * MAX_POS_PCT)
        if per < 10000:
            break

        order_target_value(code, per)
        pos = context.portfolio.positions[code] if code in context.portfolio.positions else None
        amt = pos.total_amount if pos else 0
        if amt <= 0:
            g.stat['skip'] += 1
            continue

        cost = pos.avg_cost if pos.avg_cost > 0 else p
        g.entry[code] = {
            'L': st['L'], 'p_low': st['p_low'], 'target': target,
            'buy': float(cost), 'rr': rr, 'L_idx': st['L_idx'], 'buy_date': today,
        }
        g.buy_date[code] = today
        g.stat['buy'] += 1
        slots -= 1
        bought += 1
        log.info('买入 %s @%.2f | L=%.2f(第%d根) 前低=%.2f 目标=%.2f 盈亏比=%.2f | 窗口第%d/%d根'
                 % (code, cost, st['L'], st['L_idx'], st['p_low'], target, rr,
                    st['wlen'] - st['wleft'], st['wlen']))

    if bought and VERBOSE:
        log.info('[%s] 本日买入 %d 只，当前持仓 %d 只'
                 % (today, bought, len([s for s in context.portfolio.positions
                                        if context.portfolio.positions[s].total_amount > 0])))


# =============================================================================
# 四、规则对照表（代码 ↔ 原文）
# =============================================================================
#
# 原文                                     代码
# ---------------------------------------- ------------------------------------
# 阴线的下跌值 > 1% 的股价                   is_valid_bear() 的 (o-c)/c > 1%
# K线实体不重叠超过1%（25元→0.25）           is_valid_bear() 的 gap > 1%×close
# 跌停板可以除外                            is_valid_bear() 的 is_limit_down()
# 倒数第二根阴线 → L                        find_L() 最后一根有效大阴线，L = open
# 至少三根K线下跌比较猛                      is_sharp_decline()：连跌≥3根且累计≥3%
# 段内实体互不重叠（跳空下跌）               has_body_gaps()，REQUIRE_GAP 开关
# 第一根跌幅>1%或破前低                     first_bar_sharp()，REQUIRE_FIRST_DROP 开关
# 四根k线内完全站上                        detect_setup() 的窗口 wleft >= 0
# 连续三根k线在1%以内算放缓                  slow_run_ok()：窗口放宽到 6 根
# 同时不可以创新低                          no_new_low()：price >= p_low
# 价格到达压力区就卖出                       should_sell()：price >= target
# 不能买：两倍十日成交量的K线                volume_ok()：VOL 必须 < 2×MA10(VOL)
# 上一个强压力区很近，盈亏比不满足2:1         risk_reward() >= 2.0
# 强压力区：同一股价三根放量K线               find_strong_zones() touch=3（价格区间重合≥3根）
# 影线也算，实体也算                        find_strong_zones() 用 [low, high]，不只看收盘价
# 最高价到昨天这一整段下跌阶段都算            find_strong_zones() 窗口 = [find_peak_idx(), 昨天]
# 压力区很近 → 目标取最近的那个              pick_target()：上方最近压力区的下沿
# 成交量 > 买入当天那根K线的成交量           find_strong_zones(v0=买入当天量)
# 买入后遇当日量 > 2×MA10 → 卖 1/3 持仓      _do_sell()：vol_exceed() + reduce_shares()
#
# =============================================================================
