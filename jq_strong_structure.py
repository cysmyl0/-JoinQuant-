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
      c) 与前一根实体【重合】不超过 1% 股价：(本根实体上沿 - 前一根实体下沿) ≤ 1% × close
         即允许贴住甚至小幅重叠，只要重叠量不到 1% 就不算破坏；缺口当然更算过。
         例：25 块则不可重叠 0.25，重叠 0.20 可以，重叠 0.30 不行。
         （跌停板豁免：本根跌幅 ≥ 9.8% 时，c) 不作要求）
2.  站上 L：收盘价 > L，严格大于，不含盘中，14:55 的价视为当日收盘价。
3.  窗口：从 L 之后第 1 根起数，含买入当天、不含 L。
       - 无放缓：4 根，即 L 后第 4 根仍未过 L 则作废
       - 有放缓：6 根。放缓 = L 之后出现连续 3 根窄幅 K 线（视为 1 根）
         窄幅 = 今天收盘价相对昨天收盘价的偏离 ≤ 1%，收盘对收盘，不看实体大小，也不是 (开-收)/收
          另：这 3 根的实体彼此也要"重合不超过 1%"，压过 1% 视为已开始反转 → 不算放缓，窗口仍是 4 根
       - 窗口内【任意一天】都可以是买入日：只要当天的收盘 > L 且当天量能/涨幅达标。
         不要求是"第一次站上 L"的那天；某天站上过、但当天量能不够没买成，
         后面的第 2/3/4 根只要自己达标，照样买（同一结构只买一次，见 ONE_TRADE_PER_SETUP）。
4.  量能：MA5(VOL)×(1-10%) < 当日 VOL < 2 × MA10(VOL)
       ← 必须放量过 5 日均量（给 10% 容差：当日量 > 均量的 90% 就算过），且不到 2 倍 10 日均量
       （MA5/MA10 取截至前一根已收盘K线的均量；当日 VOL 用 14:55 时点的当日累计量估计全日量）
5.  不创新低：14:55 价 ≥ P_low，P_low = 从 L 到买入前一天的最低收盘价
        （磨底阶段小实体贴在下沿慢慢新低是允许的，前低跟着下移；
         一旦出现"反转那根"——实体重合超过 1% 且没创新低的第一根K线——前低就冻结在 L 到那根之间，
         之后回踩不再下移止损位）
        作废（= 新的下跌结构，重新数三根急跌）的两种情形：
        ① 反转之前出现"重合>1% 又创新低"的砸盘大阴线
        ② 反转之后任何一根收盘跌破冻结的前低（不看重合）
5b. 站上那根要够强：站上 L 的那根上涨K线，涨幅（相对前一天收盘）> 1%
       ← 原文"（阴线的下跌值>1%的股价，上涨的k线也要>1%）"
6.  盈亏比：目标 = 买入价上方最近的强压力区；盈亏比 = (目标 - 买入) / (买入 - P_low) 必须 ≥ 2
       - 若买入价已经落在某压力区内（或正好压着下沿）→ 压力区太近，直接不买
       - 若上方【一条压力区都没有】→ 用 120 日最高价兜底：先按固定 2:1 算目标价
         （买入 + 2 × (买入 - P_low)），这个目标价在 120 日最高价之内就照做，
         连 2:1 的空间都没有就不买（USE_HIGH_FALLBACK 开关）
7.  强压力区：只有【下降波段】才有压力，一旦被上涨收复，压力就释放了
       - 先过"收复"筛子：某根K线之后若出现过更高的最高价（≥ 本根最高价，整根被覆盖）
         → 这根的压力已释放，不再算；没被覆盖的才继续算压力
       - 窗口 = 【上一个最高价那根】→【昨天】，窗口内 ≥ 3 根【放量K线】的
         价格区间 [最低价, 最高价] 有重合 → 重合的那一段就是强压力区
       - 价格区间用整根K线的最高/最低，**影线和实体都算**（不是只看收盘价）
       - 放量 = 该根成交量 > 买入当天量 V0
       - 窗口内任意一根成交量 ≥ 2 × V0 → 这一根本身整段也算强压力区
       - 每一段下跌的起点（每个"后面再没被超过的峰"）左边 3 根K线整根【无条件】算压力区
         —— 顶部供给，上涨也释放不掉
       - 目标 = 买入价上方最近的那条压力区的【下沿】（价格第一次碰到压力区的价位）
8.  否决项：成交量 ≥ 2 倍 10 日均量的 K 线（买入当天）不买
9.  标的池：默认【沪深主板】（沪 600/601/603/605 + 深 000/001/002/003）
        - 剔除 ST / *ST、剔除停牌、上市满 3 年（1095 个自然日）；不做市值/价格过滤
        - 不含创业板(300/301)、科创板(688/689)、北交所、B股
10. 所有买入和卖出都在每天 14:55 执行（1 分钟级回测 + run_daily 定时任务）
11. 持仓期间：某天成交量 > 2 × MA10(VOL)（与第 4 条同一条线的另一侧）→ 当天减仓
       - 先看止盈/止损，两者都没触发才减仓；同一天不会既减仓又清仓
       - 每次减的都是【最初仓位】的 1/3（不是剩余仓位的 1/3）：1000 股 → 每次都卖 300
       - 剩余不足 2 手（< 200 股）→ 改卖【剩余的一半】（剩 200 卖 100；再触发时剩 100，
        一半是 50、剩 50 不足 1 手 → 直接全卖 100）
       - 【再次触发的台阶】：第一次减仓后记下触发价 vol_anchor，之后必须
            股价 ≥ vol_anchor × 1.05（REDUCE_REARM_GAIN，每次减仓后基准更新为本次触发价），或
            当天相对【昨收】涨幅 > 5%（REDUCE_REARM_DAY_PCT）
         两个都不满足就不减，避免连跌中天天爆量天天减
12. 止盈：价格到上方最近强压力区时，卖到只剩【最初仓位的 1/3】：
       - 「到价」按 target_hit() 判（GAP_UP_HOLD=True）：
           开盘价已在目标价之上（跳空突破）→ 开盘不卖，等盘中回落到目标价（当日最低价 ≤ 目标价）才卖；
           一天都没回过目标价 → 不卖，继续持有；
           开盘价低于目标价 → 当日最高价 ≥ 目标价就卖。
           拿不到开盘/最高/最低价 → 退回「14:55 价 ≥ 目标价」。
           「到目标价止盈」由 handle_data() 在盘中每分钟执行（GAP_WATCH_SELL）：开盘价已在目标价之上 → 等
           回落到目标价才卖；开盘价没到目标价 → 等涨到目标价就卖。止损（跌破前低）、放量减仓、买入
           仍然只在 14:55 处理。
       - 卖多少只看【最初仓位】：累计卖到 2/3 初始为止（tp_part_shares()）
           没减过仓：1000 股 → 卖 600、留 400
           之前因爆量减过：已减 300 剩 700 → 目标价只再卖 300（累计 600、留 400）
           之前已卖够 2/3 → 不再卖，只打 tp2_done 标记，转入跟 20 日线
       - 站上 20 日线（价 ≥ MA20×0.99）→ 卖到剩 1/3 最初仓位，尾巴跟 20 日线
      - 已在线下（价 < MA20×0.99）→ 当天直接全卖，不留尾巴过夜
      - 拿不到 20 日线数据 → 全卖
       - 剩下的 1/3：收盘价【跌破 MA20×(1-1%)】就卖掉（跟随止盈）
       - 卖过 2/3 之后，剩下的 1/3 仍然受【跌破前低止损】保护，并且【照样按放量减仓】
       - MA20 默认含当天（MA20_INCLUDE_TODAY=True，用 14:55 价当今天收盘）

【用户已默认接受的实现假设（可在一处改）】
- 急跌条件（原文三条，逐条落到代码里，后两条可用开关关掉）：
    ① 至少 3 根连续收跌，且区间累计跌幅 ≥ 3%（把"下跌比较猛"量化）
    ② 段内每相邻两根K线实体【重合不超过 1% 股价】（贴住/小重叠/跳空都算过），跌停板豁免   ← REQUIRE_GAP
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
BODY_GAP_PCT = 0.01     # 实体【重合】上限比例（1%），超过才算破坏结构
LIMIT_DROP   = 0.098    # 跌停豁免阈值：单根跌幅 ≥ 9.8% 视为跌停
NARROW_PCT   = 0.01     # 放缓：今天收盘价相对昨天收盘价的偏离 ≤ 1%（收盘对收盘，不是实体大小）
NARROW_RUN   = 3        # 放缓：连续 3 根
NARROW_OVERLAP = True   # 放缓：这 3 根彼此的实体也要【重合不超过 1%】，压过 1% 视为已开始反转 → 不算放缓
W_NO_SLOW    = 4        # 无放缓 → 窗口 4 根
W_SLOW       = 6        # 有放缓 → 窗口 6 根
ONE_TRADE_PER_SETUP = True  # 同一个结构（同一个 L）只买一次：止损出局后，窗口内再满足条件也不回头买
VOL_S        = 5        # 短均量 5 日
VOL_L        = 10       # 长均量 10 日
VOL_CAP      = 2.0      # 2 倍量
VOL_S_TOL    = 0.10     # 买入时对"放量过 5 日均量"的容差：当日量 > MA5×(1-10%) 即算过
RR_MIN       = 2.0      # 盈亏比 2:1
USE_HIGH_FALLBACK = True   # 上方找不到压力区时，用"120 日最高价"兜底：空间够 2:1 就按固定 2:1 止盈
GAP_UP_HOLD  = True     # 持仓期【开盘价已在目标价之上】（跳空突破）→ 不在开盘卖，等盘中回落到目标价再卖
GAP_WATCH_SELL = True   # 止盈挪到盘中：handle_data 每分钟盯 "到目标价" 就卖（止损/减仓仍只在 14:55）
REQUIRE_STAND_GAIN = True  # 站上 L 的那根上涨K线，涨幅必须 > STAND_GAIN_PCT
STAND_GAIN_PCT = 0.01   # 原文"上涨的k线也要>1%"
DECLINE_BARS = 3        # 急跌：至少连续下跌根数
DECLINE_PCT  = 0.03     # 急跌：累计跌幅至少 3%（把原文"下跌比较猛"量化）
REQUIRE_GAP        = True   # 急跌：下跌段每相邻两根K线实体重合不超过 1%（贴住/小重叠/跳空都算过），跌停豁免
REQUIRE_FIRST_DROP = True   # 急跌：下跌段第一根跌幅 >1% 或 收盘破前低
FIRST_DROP_BACK    = 20     # "破前低"参照的前 N 根最低收盘价
LOOKBACK_L   = 10       # 只在最近 10 根里找有效大阴线 L（否则 L 太老无意义）
HIGH_BACK    = 120      # 往前找"上一个最高价"的回溯根数（压力区窗口 = 最高价那根 → 昨天）
ZONE_KEEP_PREV_HIGH = 3 # 每个下跌起点（前高）左边【无条件】保留几根K线当压力区

# ---------- 选股 / 仓位 / 费率 ----------
UNIVERSE     = 'main_board'  # 'main_board' 沪深主板（默认）| 'all' 全市场 | 'hs300' | 'zz500' | 'zz1000'
IDX_MAP      = {'hs300': '000300.XSHG', 'zz500': '000905.XSHG', 'zz1000': '000852.XSHG'}
MAIN_BOARD_PREFIXES = ('600', '601', '603', '605',   # 沪市主板
                       '000', '001', '002', '003')   # 深市主板（含 2021 年并入的原中小板 002/003）
EXCLUDE_ST   = True     # True: 剔除 ST / *ST（用 get_extras('is_st') 判，取不到再看股票名称）
MIN_LIST_YEARS = 3      # 上市满 3 年才纳入
MIN_LIST_DAYS = 365 * MIN_LIST_YEARS   # = 1095 个自然日（按自然日算，不是交易日）
BARS_SCAN    = 60       # 第一步扫描用日线根数（够算 detect_setup + 均量）
BARS_FULL    = 200      # 第二轮算强压力区用日线根数（需覆盖 HIGH_BACK=120，留点余量）
MAX_CAND     = 500      # 单日候选上限（控制 14:55 的耗时）
MAX_POS      = 5        # 最多同时持有 5 只
MAX_POS_PCT  = 0.25     # 单票最多占总资产 25%
SLIP_PCT     = 0.002    # 滑点 0.2%
TAX          = 0.0005   # 卖出印花税 0.05%
COMMISSION   = 0.0003   # 佣金 万3
MIN_COMM     = 5        # 最低佣金 5 元
MAX_HOLD_DAYS = 0       # 最大持有天数，0 = 不启用

# ---------- 持仓中的减仓规则（m00216 新增） ----------
REDUCE_RATIO   = 1.0 / 3.0   # 每次减仓卖出【最初仓位】的 1/3（剩余不足 2 手时改卖一半，卖完剩不足 1 手就清仓）
REDUCE_VOL_CAP = 2.0         # 触发减仓的量能倍数：当日量 > 2 × MA10(量)
REDUCE_LOT     = 100         # 减仓股数取整手
REDUCE_REARM_GAIN = 1.05     # 再次减仓的台阶：股价要 ≥ 上次减仓价 × 1.05
REDUCE_REARM_DAY_PCT = 0.05  # 或者当天相对昨收涨幅 > 5%

# ---------- 止盈：到压力区只卖到剩 1/3【最初仓位】，尾巴跟 20 日线 ----------
TP_FOLLOW_MA = True       # True: 到压力区卖到剩 1/3 跟 20 日线；False: 到压力区全清（旧行为）
TP_RATIO     = 2.0 / 3.0  # 到压力区时，累计应卖掉的最初仓位占比
TP_LOT       = 100        # 止盈卖出取整手（`tp_part_shares()` 用）
MA20_N       = 20         # 跟踪止盈用的均线天数
MA20_INCLUDE_TODAY = True   # MA20 是否把今天(14:55 价)算进去；True = 含当天（更贴近实盘）
MA20_TOL     = 0.01       # 跌破 20 日均线的容差：价 < MA20×(1-1%) 才算真跌破（过了线不算）

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
    """第 i 根是否近似跌停（用于实体重合豁免）。"""
    if i < 1:
        return False
    return c[i] <= c[i - 1] * (1.0 - LIMIT_DROP)


def body_low(o, c, i):
    return min(o[i], c[i])


def body_top(o, c, i):
    return max(o[i], c[i])


def body_overlap(o, c, prev, i):
    """
    第 i 根实体相对前一根(prev)实体的【重合量】（价格计）：
        本根实体上沿 - 前一根实体下沿
    > 0 表示两根实体有重合，< 0 表示有跳空缺口。
    """
    return body_top(o, c, i) - body_low(o, c, prev)


def overlap_ok(o, c, prev, i, tol=None):
    """
    原文「K 线实体不重叠超过 1%，例如股票 25 块则不可重叠 0.25」：
    允许两根实体最多重合 tol × 股价，超过才算破坏结构（贴住、有缺口都算过）。
    tol=None 时读全局 PCT。
    """
    if tol is None:
        tol = PCT
    return body_overlap(o, c, prev, i) <= tol * float(c[i])


def makes_new_low(c, lo, i):
    """第 i 根收盘价是否创了 lo..i-1 的新低（收盘价口径，和前低 p_low 同一把尺）。"""
    if i <= lo:
        return False
    return float(c[i]) < float(np.min(c[lo:i]))


def find_reversal_idx(o, c, L_idx, n=None):
    """
    "反转那根"：第一根【实体重合超过 1%】且【没有创新低】的K线。
    磨底阶段的K线都贴在前一根实体下沿附近，一旦有根K线明显往上顶、又没跌破前面已经走过的低点，
    就是止跌反转开始 → 前低的窗口就截到它为止。
    创新低（收盘低于 L 到前一根的最低收盘）说明下跌还没走完，不算反转，跳过继续往后找。
    找不到返回 None。
    """
    if n is None:
        n = len(c)
    for t in range(L_idx + 1, n):
        if not overlap_ok(o, c, t - 1, t) and not makes_new_low(c, L_idx, t):
            return t
    return None


def is_valid_bear(o, c, i):
    """第 i 根是否为"有效大阴线"（阴线 + 实体跌幅>1% + 与前一根实体重合不超过1%，跌停豁免）。"""
    if i < 1:
        return False
    if not is_bear(o, c, i):
        return False
    if (o[i] - c[i]) / c[i] <= PCT:                 # 实体跌幅不够
        return False
    if not overlap_ok(o, c, i - 1, i) and not is_limit_down(c, i):
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
    下跌段 [start, end] 内，每相邻两根实体【重合都不超过 1% 股价】（贴住/缺口都算过），
    原文："K 线实体不重叠超过 1%"。跌停板豁免（原文"跌停板可以除外"）。
    """
    for t in range(start + 1, end + 1):
        if not overlap_ok(o, c, t - 1, t) and not is_limit_down(c, t):
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
      ② REQUIRE_GAP=True 时：段内每相邻两根实体重合不超过 1% 股价（贴住/小重叠/跳空都算过，跌停豁免）
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


def slow_run_ok(o, c, L_idx, n=None):
    """
    放缓判定：L 之后的窗口内，存在连续 NARROW_RUN 根窄幅K线，且这几根彼此实体【重合不超过 1%】。
      窄幅   = abs(c[t]/c[t-1] - 1) <= NARROW_PCT，即【今天收盘价相对昨天收盘价】的偏离，
               不是 (开-收)/收 那种实体涨跌幅，也不看实体大小。
      不重合 = overlap_ok()：实体上沿 - 前一根实体下沿 <= 1%×close。
               实体压过 1%（含跳空/长影线）说明已经开始反转，不算放缓 → 窗口仍是 4 根。
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
            if abs(r) > NARROW_PCT:          # 收盘对收盘偏太多 → 不算窄幅
                ok = False
                break
            if NARROW_OVERLAP and not overlap_ok(o, c, t - 1, t):   # 实体重合超过 1% → 已经在走，不是磨底
                ok = False
                break
        if ok:
            return True
    return False


def window_size(o, c, L_idx, n=None):
    """返回窗口根数：有放缓 6，无放缓 4。"""
    return W_SLOW if slow_run_ok(o, c, L_idx, n) else W_NO_SLOW


def detect_setup(o, c, h, l, v):
    """
    输入：已收盘日线（最后一根 = 昨天 T-1）的 numpy 数组。
    输出：None 或 dict，代表"今天(T)是可以触发买入的一根"。
          L / L_idx / p_low / wlen / wleft / v5 / v10

    做三件事：
      1. 找出有效大阴线 L，并确认急跌结构
      2. 确认窗口没作废：今天(T)在 L 之后第 1..wlen 根之内
      3. 确认下跌没有走完（作废条件见下）

    注意：窗口内【站上过 L】不再让结构作废。窗口内任意一天，只要当天收盘 > L
    且量能/涨幅达标就能买（不要求是第一天站上那根）。窗口 = L 之后第 1..wlen 根，
    过了窗口还没买成，这段结构就作废、重新数三根急跌。

    "结构作废"三件事（都在 L 之后、到昨天为止这一段里判）：
      ① 反转【之前】出现"实体重合>1% 又创新低"的砸盘大阴线 → 下跌还没走完
         （磨底阶段小实体贴着下沿慢慢新低是允许的：那还是放缓，不算新结构，
          前低跟着下移即可）
      ② 反转【之后】任何一根收盘跌破冻结的前低（= 止损位）→ 新的下跌段，不看重合
      ③ 窗口跑完还没达标（今天已是 L 后第 5/6 根之外）
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

    # 前低（止损位）= L 到昨天的最低收盘价；
    # 一旦出现"反转那根"（重合超 1% 且没创新低），前低冻结为 L 到那根之间的最低收盘价，
    # 之后回踩的更低收盘价不再下移止损位（否则反转之后随便一个小坑都会把止损拉低、把盈亏比算差）。
    p_low = float(np.min(c[Li:]))
    rev = find_reversal_idx(o, c, Li, n)
    if rev is not None:
        p_low = float(np.min(c[Li:rev + 1]))

    # 结构还在不在：
    #   ① 反转之前：砸下去的大阴线（重合>1%）又创新低 → 旧 L 作废；
    #      小实体磨底新低（重合≤1%）不算新结构，前低照上面的算法跟着下移
    #   ② 反转之后：收盘跌破冻结的前低（= 止损位）→ 也算新的下跌段（这一条不看重合）
    # （曾经还有一条"窗口内站上过 L 就作废"，已删除：现在窗口内任意一天都能买。）
    for t in range(Li + 1, n):
        if (not overlap_ok(o, c, t - 1, t)) and makes_new_low(c, Li, t):
            return None
        if rev is not None and t > rev and float(c[t]) < p_low:
            return None

    wlen = window_size(o, c, Li, n)
    wleft = Li + wlen - n                  # 今天(索引 n)是第几根：>=0 表示还在窗口内
    if wleft < 0:
        return None

    v5 = float(np.mean(v[n - VOL_S:])) if n >= VOL_S else None
    v10 = float(np.mean(v[n - VOL_L:])) if n >= VOL_L else None

    return {
        'L': L, 'L_idx': Li, 'p_low': p_low,
        'wlen': wlen, 'wleft': wleft,
        'v5': v5, 'v10': v10,
        'prev_close': float(c[-1]),        # 昨天收盘，用来算"站上那根的涨幅"
    }


def volume_ok(vol_today, v5, v10, cap=VOL_CAP, tol=None):
    """
    量能条件：MA5×(1-tol) < 当日量 < cap × MA10，且不能 ≥ cap × MA10（否决项）。
    tol = 0.10：对"放量过 5 日均量"给 10% 容差（当日量 > 均量的 90% 就算过）。
    tol=None 时读全局 VOL_S_TOL。
    """
    if tol is None:
        tol = VOL_S_TOL
    if v5 is None or v10 is None or v10 <= 0:
        return False
    if vol_today <= 0:
        return False
    return (vol_today > v5 * (1.0 - tol)) and (vol_today < cap * v10)


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


def _suffix_max_after(arr):
    """
    对每个 i 返回 arr[i+1:] 的最大值（不含自己）；最后一根返回 -inf。
    也就是"这根K线之后，价格最高跑到过哪里"。
    """
    a = np.asarray(arr, dtype=float)
    n = len(a)
    out = np.full(n, -np.inf)
    if n >= 2:
        out[:-1] = np.maximum.accumulate(a[::-1])[::-1][1:]
    return out


def released_mask(h):
    """
    "压力是否已经被上涨释放"。用【最高价】判定，且必须把整根K线全覆盖掉才算释放。

    对第 i 根：M_i = 它之后（i+1 ～ 昨天）出现过的最高价
      M_i >= high[i]  → 价格已经涨回这根K线的最高点、整根被覆盖 → 压力释放
      M_i <  high[i]  → 还没收复 → 整根保留，仍然算压力

    效果 = "只有下降波段才有压力"：一段下跌一旦被后面的上涨收复，
    这一段K线的压力就整体作废；没被收复的部分继续压着。
    """
    H = np.asarray(h, dtype=float)
    return _suffix_max_after(H) >= H


def find_recent_swing_high(h, back=HIGH_BACK):
    """
    "最近一次下跌的起点"（前高）：find_all_swing_highs() 里最靠右的那个
    —— 也就是最后一次由涨转跌的那根K线（它后面必须真的还有K线，才谈得上"起点"）。
    用来定位"前高那几根K线"。
    找不到（例如整段单边下跌）就退化成窗口内的最高价那根。
    """
    n = len(h)
    if n == 0:
        return 0
    s = max(0, n - back)
    H = np.asarray(h[s:], dtype=float)
    after = _suffix_max_after(H)
    # 从倒数第二根开始：最后一根后面没有K线，不可能是一次下跌的起点
    for i in range(len(H) - 2, 0, -1):
        if H[i] >= H[i - 1] and H[i] >= after[i]:
            return s + i
    return s + int(np.argmax(H))


def find_all_swing_highs(h, back=HIGH_BACK):
    """
    "每一段下跌的起点"（所有由涨转跌的顶）：窗口内满足
        high[i] >= high[i-1]   且   high[i] >= 它之后所有 high 的最大值
    的全部下标（升序）。也就是【每一个后面再没被超过的峰】。

    这就是"上涨转成下跌"的判据：一根K线的最高价不低于左邻、也不低于右边任何
    一根的最高价 —— 说明它是这段行情的局部顶，后面再没涨回去过。
    一个都找不到（例如整段单边下跌）时退化成窗口内最高价那根。
    """
    n = len(h)
    if n == 0:
        return []
    s = max(0, n - back)
    H = np.asarray(h[s:], dtype=float)
    after = _suffix_max_after(H)
    # 首根（左边没K线）和最后一根（后面没K线）都不算"下跌的起点"
    out = [s + i for i in range(1, len(H) - 1)
           if H[i] >= H[i - 1] and H[i] >= after[i]]
    if not out:
        out = [s + int(np.argmax(H))]
    return out


def find_strong_zones(h, l, v, v0, back=HIGH_BACK, touch=3, vol_cap=VOL_CAP,
                      keep_prev_high=None):
    """
    计算"强压力区"列表，每条是一个价格区间 [(lo, hi), ...]（按 lo 升序）。

    h/l/v   : 已收盘日线（最后一根 = 昨天 T-1，不含今天）
    v0      : 买入当天那根K线的成交量
    back    : 往前找"上一个最高价"的回溯根数

    压力只存在于【下降波段】里 —— 一旦上涨把这段失地收复，压力就释放了：
      0) 收复筛子：一根K线只有在它之后从没出现过更高的最高价时才还带压力；
         后面的最高价 ≥ 本根最高价（整根被覆盖）→ 这根的压力释放，不再算。
      1) 窗口 = 上一个最高价那根 → 昨天（这段下跌）
      2) 窗口内 ≥ touch(3) 根【放量K线】的价格区间 [最低价, 最高价] 有重合
         → 重合段就是强压力区；价格用整根K线（实体+上下影线都算）
         放量 = 该根成交量 > v0
      3) 任意一根成交量 ≥ vol_cap × v0 → 这一根整根算强压力区
      4) 每段下跌的起点（每一个"后面再没被超过的峰"）左边 keep_prev_high(3) 根K线，
         整根【无条件】算压力区 —— 上涨能释放下面的压力，但每个顶部这几根始终是供给，必须留着
    """
    n = len(h)
    if n < 5:
        return []
    if keep_prev_high is None:
        keep_prev_high = ZONE_KEEP_PREV_HIGH
    peak = find_peak_idx(h, back)

    zones = []

    H = np.asarray(h[peak:], dtype=float)
    Lw = np.asarray(l[peak:], dtype=float)
    V = np.asarray(v[peak:], dtype=float)

    # ---------- 0. 只留下还没被上涨收复的K线 ----------
    if len(H) > 0:
        keep = ~released_mask(H)
        Hk = H[keep]
        Lk = Lw[keep]
        Vk = V[keep]

        v0 = float(v0)
        # ---------- 2. 三根以上放量K线的价格区间互相重合 ----------
        if Hk.size:
            big = Vk >= vol_cap * v0        # 单根 2 倍量
            loud = Vk > v0                  # 放量（big 必然也放量）

            if int(loud.sum()) >= touch:
                los = Lk[loud]
                his = Hk[loud]
                pts = np.unique(np.concatenate([los, his]))
                if len(pts) >= 2:
                    # 每两个相邻端点之间覆盖数恒定（用中点判定）
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
                for pv, cnt in zip(pts, cov_pt):
                    if cnt >= touch and not any(lo <= pv <= hi for lo, hi in zones):
                        zones.append((float(pv), float(pv)))

            # ---------- 3. 单根 2 倍量：整根K线都算压力区 ----------
            for i in np.where(big)[0]:
                zones.append((float(Lk[i]), float(Hk[i])))

    # ---------- 4. 每个下跌起点（峰）左边那几根：无条件保留 ----------
    for p in find_all_swing_highs(h, back):
        for t in range(max(0, p - int(keep_prev_high)), p):
            zones.append((float(l[t]), float(h[t])))

    return _merge_zones(zones)


def zone_status(zones, buy):
    """
    买入价相对强压力区的位置，三种状态：
      'inside' —— 买入价已经落在某个压力区内 / 正好压着它的下沿 → 压力太近，不买
      'above'  —— 上方还有压力区 → 可以拿它的下沿当目标
      'none'   —— 上方一条压力区都没有（全在买入价下方，或者压根没算出压力区）
    """
    if not zones:
        return 'none'
    for lo, hi in sorted(zones):
        if hi <= buy:        # 整段在买入价下方（或刚好在买入价）→ 不是上方压力
            continue
        if lo <= buy:        # 买入价已经在区内 / 压着下沿 → 压力太近
            return 'inside'
        return 'above'
    return 'none'


def pick_target(zones, buy):
    """
    买入价【上方最近】强压力区的下沿；没有 / 已在区内 → None。
    - 只认整个区间都在买入价上方的区（下沿 > 买入价）
    - 买入价已经落在某个压力区内、或正好压着它的下沿 → 返回 None
      （这就是原文"上一个强压力区很近"→不买，不硬凑一个目标价）
    """
    if zone_status(zones, buy) != 'above':
        return None
    for lo, hi in sorted(zones):
        if hi > buy and lo > buy:
            return lo
    return None


def fallback_target(buy, p_low, high_back_max, rr_min=RR_MIN):
    """
    上方一条压力区都没有时的兜底目标 —— 用【最高价还能涨多少】来判断值不值得做。

    做法：
      1. 先按"固定 rr_min:1"算出目标价：target = buy + rr_min × (buy - p_low)
      2. 再看这段空间是不是在历史最高价（默认最近 120 根的最高价）之内：
         target ≤ high_back_max  → 有这么多空间，就用这个目标（就按 rr_min:1 止盈）
         target >  high_back_max → 上方连 rr_min 倍的空间都没有 → 不做（返回 None）

    也就是：上面看不到真实压力，就按固定 2:1 止盈；连 2:1 的空间都没有，就不买。
    """
    if high_back_max is None:
        return None
    try:
        buy = float(buy)
        p_low = float(p_low)
        high_back_max = float(high_back_max)
    except (TypeError, ValueError):
        return None
    risk = buy - p_low
    if risk <= 0:
        return None
    target = buy + float(rr_min) * risk
    if target > high_back_max:
        return None
    return target


def stand_gain_ok(price, prev_close, need=STAND_GAIN_PCT):
    """
    站上 L 的那根上涨K线，涨幅（相对前一天收盘）必须 > need（默认 1%）。
    原文："阴线的下跌值 > 1% 的股价，上涨的 k 线也要 > 1%"。
    REQUIRE_STAND_GAIN=False 时此条不生效。
    """
    if not REQUIRE_STAND_GAIN:
        return True
    if price is None or prev_close is None or prev_close <= 0:
        return False
    gain = round(float(price) / float(prev_close) - 1.0, 10)   # 抹掉浮点误差
    return gain > need


def sell_allowed(buy_date, today):
    """A 股 T+1：买入当天不能卖。"""
    return buy_date is not None and buy_date < today


def ma_band(ma20, tol=None):
    """
    "跌破 20 日均线"的实际判定线 = MA20 × (1 - tol)。
    给 1% 容差：价格在均线上下来回蹭不算跌破，得真的跌下去 1% 才触发。
    tol=None 时读全局 MA20_TOL（这样运行时改参数也能生效）。
    """
    if ma20 is None:
        return None
    if tol is None:
        tol = MA20_TOL
    return float(ma20) * (1.0 - float(tol))


def target_hit(price, target, day_open=None, day_high=None, day_low=None,
               gap_hold=True):
    """
    "价格到压力区目标价"的触发判定 —— 分跳空和非跳空两种情形。

      A) 开盘价 > 目标价（高开一步跨过压力区 / 跳空突破）：
         gap_hold=True  → 开盘不卖，等【盘中回落到目标价】（当日最低价 ≤ 目标价）再卖；
                          一天都没回过目标价 → 不卖，继续持有（突破有效，让它跑）。
         gap_hold=False → 直接按"到目标价"卖（旧行为）。

      B) 开盘价 ≤ 目标价：盘中最高价 ≥ 目标价就卖（就是"到目标价就卖"）。

      C) 拿不到当日开盘价：退回用 14:55 的价判（price ≥ target），最保守。

    参数 price 是 14:55 的价，仅在 C / 缺数据时兜底用。
    """
    if target is None:
        return False
    try:
        target = float(target)
    except (TypeError, ValueError):
        return False

    op = None
    lo = None
    hi = None
    try:
        op = float(day_open) if day_open is not None else None
    except (TypeError, ValueError):
        op = None
    try:
        lo = float(day_low) if day_low is not None else None
    except (TypeError, ValueError):
        lo = None
    try:
        hi = float(day_high) if day_high is not None else None
    except (TypeError, ValueError):
        hi = None

    if op is not None and op > target:
        if not gap_hold:
            return True
        # 跳空突破：只有盘中回落到目标价才卖
        return lo is not None and lo <= target

    if hi is not None:
        return hi >= target

    try:
        return price is not None and float(price) >= target
    except (TypeError, ValueError):
        return False


def sell_decision(price, entry, today, buy_date, ma20=None,
                  day_open=None, day_high=None, day_low=None):
    """
    返回 (action, 原因)，action ∈ {'', 'all', 'part'}：
      ''    不动
      'all' 全部卖出
      'part' 卖到只剩【最初仓位的 1/3】（不是卖剩余 2/3）：具体股数由调用方的
             `tp_part_shares()` 按 qty0 - sold 算，剩下 1/3 继续持有、跟 20 日线

    规则（优先级从上到下）：
      1) T+1 没到 → 不动
      2) 跌破前低 → 全卖（止损永远优先，包括剩下的 1/3）
      3) 已经卖过 2/3（entry['tp2_done']）→ 价 < MA20×(1-1%) 就全卖，否则继续拿
      4) 到压力区（按 target_hit() 判，含跳空处理）：
           - 开盘就跳空到目标价之上 → 不卖，等盘中回落到目标价再卖
           - 开盘在目标价之下 → 盘中最高价到目标价就卖
           - 卖多少只看最初仓位：累计卖到 2/3 初始（tp_part_shares() 会抵扣已减的部分）
           - 站上 MA20（价 ≥ MA20×0.99）才留 1/3 尾巴；已跌破 → 当天全卖，不留过夜
           - 拿不到 MA20 数据时才全卖
      5) 时间止损（MAX_HOLD_DAYS，默认关闭）→ 全卖

    day_open / day_high / day_low = 当日开盘价、截至 14:55 的最高价、最低价；
    不传就退回"14:55 价 ≥ 目标价"的旧口径。
    """
    if entry is None:
        return '', ''
    if not sell_allowed(buy_date, today):
        return '', ''
    if price is None or price <= 0:
        return '', ''
    if price <= entry['p_low']:
        return 'all', '止损:跌破前低'

    band = ma_band(ma20)

    # 已经止盈过 2/3：剩下的 1/3 只看 20 日线（带 1% 容差）
    if entry.get('tp2_done'):
        if band is not None and price < band:
            return 'all', '跟踪止盈:跌破20日线'
        if MAX_HOLD_DAYS and (today - buy_date).days >= MAX_HOLD_DAYS:
            return 'all', '时间止损'
        return '', ''

    if target_hit(price, entry['target'], day_open, day_high, day_low,
                  GAP_UP_HOLD):
        gap = (day_open is not None and entry['target'] is not None
               and float(day_open) > float(entry['target']))
        tail = '(跳空回踩)' if gap else ''
        if not TP_FOLLOW_MA:
            return 'all', '止盈:到压力区' + tail
        if band is None:
            return 'all', '止盈:到压力区(无20日线,全卖)' + tail
        # 到目标价时已经跌破 20 日线（没站上）→ 当天就全卖，
        # 不留 1/3 过夜（否则次日 14:55 照样要清，白担一夜风险）。
        if price < band:
            return 'all', '止盈:到压力区(未站上MA20,全卖)' + tail
        # 站上 20 日线：只卖到【2/3 最初仓位】，留 1/3 尾巴跟 20 日线；
        # 之前因放量减仓已经卖掉的份额算在这 2/3 里（`tp_part_shares()` 会抵扣）。
        return 'part', '止盈:到压力区(卖到剩1/3,留尾巴)' + tail

    if MAX_HOLD_DAYS and (today - buy_date).days >= MAX_HOLD_DAYS:
        return 'all', '时间止损'
    return '', ''


def should_sell(price, entry, today, buy_date, ma20=None,
                day_open=None, day_high=None, day_low=None):
    """向后兼容的布尔版：只要 sell_decision 有动作就返回 True。"""
    act, why = sell_decision(price, entry, today, buy_date, ma20,
                             day_open, day_high, day_low)
    return (act != ''), why


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


def reduce_shares(total_amount, init_amount=None,
                  ratio=REDUCE_RATIO, lot=REDUCE_LOT):
    """
    放量减仓要卖多少股。份额按【最初仓位】算，不按剩余仓位（`init_amount` = 买入时的股数）。

      - 剩余 ≥ 2 手：卖 ratio（默认 1/3）× 最初仓位，向下取整到 1 手
      - 剩余 < 2 手，或 1/3 最初仓位不足 1 手 / 不小于剩余：直接卖【剩余的一半】
      - 卖完之后剩下的不足 1 手（碎股）→ 这一次直接把它一起卖掉，即清仓

    "剩余 200 股"的完整走法：第一次触发卖一半 100（剩 100 股，正好 1 手）；
    再触发时 100 的一半是 50，剩 50 不足 1 手 → 直接全卖 100。
    init_amount 不传就当作等于当前剩余（旧口径）。
    """
    total = int(total_amount)
    init = int(init_amount) if init_amount else total
    if total <= 1 or init <= 0:
        return 0
    # +1e-9 是为了避免 300*(1/3)=99.99999 被截成 0 手这种浮点误差
    third = int(np.floor(init * float(ratio) / lot + 1e-9)) * lot
    if total < 2 * lot or third < lot or third >= total:
        sh = int(total // 2)
    else:
        sh = third
    # 剩下的不足 1 手（碎股再触发也拆不动）→ 这次一起卖掉
    if total - sh < lot:
        return int(total)
    return int(max(sh, 0))


def tp_part_shares(init_amount, sold_amount, remain_amount,
                   ratio=TP_RATIO, lot=REDUCE_LOT):
    """
    到目标价时"卖到只剩 1/3 最初仓位"：先算总共该卖 ratio×最初仓位（向下取整到 1 手），
    再减掉之前已经因放量减仓卖掉的股数（`sold_amount`），就是要再卖的股数。
    已经卖够了返回 0（此时只标记 tp2_done，让剩下的尾巴跟 20 日线）。
    """
    init = int(init_amount)
    remain = int(remain_amount)
    if init <= 0 or remain <= 1:
        return 0
    total_tp = int(np.floor(init * float(ratio) / lot + 1e-9)) * lot
    sh = total_tp - int(sold_amount)
    sh = min(sh, remain - 1)
    return int(max(sh, 0))


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
    g.done = set()    # 已买过的 (code, L_idx)：同一个结构只买一次
    g.stat = {'days': 0, 'cand': 0, 'buy': 0, 'sell_win': 0, 'sell_lose': 0,
              'skip': 0, 'reduce': 0, 'tp_part': 0}
    g.no_minute_vol = 0

    log.info('强势结构策略初始化完成 | 窗口: 无放缓%d根/有放缓%d根 | 盈亏比≥%.1f'
             % (W_NO_SLOW, W_SLOW, RR_MIN))
    log.info('量能条件: MA%d < 当日量 < %.1f×MA%d | 标的池: %s | 剔除ST: %s'
             % (VOL_S, VOL_CAP, VOL_L, UNIVERSE, '是' if EXCLUDE_ST else '否'))

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
            if ONE_TRADE_PER_SETUP and (code, int(st['L_idx'])) in g.done:
                continue                      # 这个结构已经买过一次（后来止损出来了），不再回头
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
        if not stand_gain_ok(p, st.get('prev_close')):   # 条件④：站上那根涨幅 >1%
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
        status = zone_status(zones, p)
        if status == 'inside':
            # 买入价已经落在压力区内 / 压着下沿 → 压力太近，不买
            continue
        if status == 'above':
            target = pick_target(zones, p)
            src = '压力区'
        else:
            # 上方一条压力区都没有 → 用"120 日最高价"兜底：空间够 2:1 就按 2:1 止盈
            if not USE_HIGH_FALLBACK:
                continue
            high_max = float(np.max(h[-HIGH_BACK:])) if len(h) else None
            target = fallback_target(p, st['p_low'], high_max)
            src = '120日高点'
            if target is None:
                continue
        if target is None:
            continue
        rr = risk_reward(target, p, st['p_low'])
        if rr < RR_MIN - 1e-9:
            continue
        picks.append((rr, code, p, st, target, vt, src))

    if not picks:
        return
    picks.sort(key=lambda x: -x[0])

    # ---------- 第 5 步：下单 ----------
    _do_buy(context, today, picks)


def handle_data(context, data):
    """
    盘中（分钟回测下每分钟被调用一次）只干一件事：**止盈（到目标价）**。

      · 开盘价已经在目标价之上（跳空一步跨过压力区）→ 不卖，等它回落到目标价再卖；
      · 开盘价低于目标价 → 等它涨到目标价就卖。
      该卖 2/3 还是全卖，仍由 sell_decision() 按 20 日线决定。

    ⚠️ 只有止盈挪到了盘中。止损（跌破前低）、放量减仓、买入全都不在这里，
       仍然留在 14:55 的 trade_1455 里 —— 所以这里遇到"现价已经跌破前低"的票直接跳过。

    开关 GAP_WATCH_SELL = False 就关掉盘中监控，回到"14:55 用当日高低价回溯判断"。
    """
    if not GAP_WATCH_SELL:
        return
    dt = context.current_dt
    # 09:31 之前不干活（集合竞价阶段 day_open 还没定下来）
    if dt.hour < 9 or (dt.hour == 9 and dt.minute < 31):
        return
    if not g.entry:
        return
    today = dt.date()
    try:
        cd = get_current_data()
    except Exception:
        return

    for s in list(context.portfolio.positions.keys()):
        pos = context.portfolio.positions[s]
        if pos.total_amount == 0:
            continue
        entry = g.entry.get(s)
        if entry is None or entry.get('target') is None:
            continue
        # 已经止盈过 2/3：剩下的 1/3 只跟 20 日线，不再受"目标价"约束
        if entry.get('tp2_done'):
            continue
        buy_date = g.buy_date.get(s)
        if not sell_allowed(buy_date, today):
            continue
        try:
            d = cd[s]
        except Exception:
            continue
        if getattr(d, 'paused', False):
            continue

        # ★ 关键的那一层判断：开盘价跳过目标价 → 等回落；没跳过 → 等涨到目标价
        op = getattr(d, 'day_open', None)
        target = float(entry['target'])

        p = None
        if data is not None:
            try:
                p = float(data[s].close)
            except Exception:
                p = None
        if not p:
            p = getattr(d, 'last_price', None)
        if not p:
            continue
        # 跌停卖不出
        if getattr(d, 'low_limit', None) and p <= d.low_limit * 1.001:
            continue

        # 已经跌破前低：这是止损，不在盘中做，交给 14:55
        plow = entry.get('p_low')
        if plow is not None and float(p) <= float(plow):
            continue

        if op is not None and float(op) > target:
            # 高开一步跨过目标价：等回落到目标价（盘中没回落就一整天不卖）
            if float(p) > target:
                continue
            kind = '高开回踩'
        else:
            # 开盘价没到目标价：等涨到目标价
            if float(p) < target:
                continue
            kind = '盘中到价'

        ma20 = _hist_close_ma(s, MA20_N, p) if TP_FOLLOW_MA else None
        act, why = sell_decision(p, entry, today, buy_date, ma20,
                                 day_open=op, day_high=p, day_low=p)
        if act not in ('all', 'part'):
            continue
        ret = (p / entry['buy'] - 1.0) * 100 if entry['buy'] else 0.0
        log.info('盘中%s %s @%.2f (目标%.2f 开盘%.2f) %s'
                 % (kind, s, p, target, op if op is not None else float('nan'), why))
        _exec_sell(s, context, p, act, why, ma20, entry, ret)


def listed_long_enough(start_date, ref_date, days=None):
    """
    上市满 N 个自然日才算老股（默认 3 年 = 1095 天）。
    次新股/新股不参与：一方面历史K线太短，压力区和 20 日线算不准；
    另一方面上市初期的爆炒下跌跟"强势结构"不是一回事。
    """
    if days is None:
        days = MIN_LIST_DAYS
    if start_date is None or ref_date is None:
        return False
    try:
        s = pd.Timestamp(start_date)
        r = pd.Timestamp(ref_date)
        if pd.isna(s) or pd.isna(r):
            return False
        return (r - s).days >= int(days)
    except Exception:
        return False


def is_main_board(code):
    """
    是否沪深主板股票（按 6 位代码前缀判，带不带 .XSHG/.XSHE 都行）：
      沪市主板  600 / 601 / 603 / 605
      深市主板  000 / 001 / 002 / 003（2021 年中小板并入深市主板，所以 002/003 也算）
    排除：
      创业板    300 / 301
      科创板    688 / 689
      北交所    43x / 83x / 87x / 92x（8 开头、4 开头）
      B 股      900（沪）、200（深）
    """
    if code is None:
        return False
    s = str(code).split('.')[0].strip()
    if len(s) != 6 or not s.isdigit():
        return False
    return s[:3] in MAIN_BOARD_PREFIXES


def is_st_name(name):
    """
    股票简称里带 ST 就算 ST（含 *ST、ST、S*ST 等写法）。
    'ST' 出现位置不限，但要求是大写形式，避免把正常股票误伤。
    """
    if name is None:
        return False
    n = str(name).upper().replace(' ', '').replace('\u3000', '')
    return 'ST' in n


def strip_st(codes, names=None, st_flags=None):
    """
    剔除 ST / *ST。
      codes      : 待过滤的股票列表
      names      : {code: 股票简称}，可选
      st_flags   : {code: True/False}，来自 get_extras('is_st')，可选；优先级高于 names
    两个都没给时原样返回（无法判断就不乱删）。
    """
    names = names or {}
    st_flags = st_flags or {}
    out = []
    for c in codes:
        if EXCLUDE_ST:
            if c in st_flags:
                if bool(st_flags[c]):
                    continue
            elif is_st_name(names.get(c)):
                continue
        out.append(c)
    return out


def _get_universe(context):
    """标的池：沪深主板（默认）→ 剔除 ST/*ST → 剔除停牌。不做市值/价格过滤。"""
    d = context.previous_date
    codes = []
    names = {}
    try:
        # 全市场表：既用来取名称（判 ST），也在 UNIVERSE='all' 时当股票池
        sec = None
        try:
            sec = get_all_securities(types=['stock'], date=d)
            if sec is not None and len(sec) > 0 and 'display_name' in sec.columns:
                names = dict(sec['display_name'])
        except Exception as e:
            log.warn('取股票名称失败，ST 判定改用 is_st: %s' % e)

        if UNIVERSE in IDX_MAP:
            codes = list(get_index_stocks(IDX_MAP[UNIVERSE], date=d))
        else:
            if sec is None or len(sec) == 0:
                return []
            n_all = len(sec)
            sec = sec[[listed_long_enough(sec.at[c, 'start_date'], d) for c in sec.index]]
            if VERBOSE:
                log.info('剔除上市不满 %d 年：%d → %d 只' % (MIN_LIST_YEARS, n_all, len(sec)))
            if UNIVERSE == 'main_board':
                # 主板 = 沪 60x + 深 000/001/002/003，剔除创业板/科创板/北交所/B股
                codes = [c for c in sec.index if is_main_board(c)]
            else:
                codes = list(sec.index)
        if VERBOSE:
            log.info('标的池 %s：%d 只（%s）' % (UNIVERSE, len(codes), d))
    except Exception as e:
        log.error('取标的池失败: %s' % e)
        return []

    # ---------- 剔除 ST / *ST ----------
    if EXCLUDE_ST and codes:
        st_flags = {}
        try:
            ex = get_extras('is_st', codes, end_date=d, count=1)
            if ex is not None and len(ex) > 0:
                row = ex.iloc[-1]
                st_flags = {str(k): bool(row[k]) for k in row.index}
        except Exception as e:
            log.warn("get_extras('is_st') 取不到，改用股票名称判 ST: %s" % e)
        n0 = len(codes)
        codes = strip_st(codes, names, st_flags)
        if VERBOSE and n0 != len(codes):
            log.info('剔除 ST/*ST %d 只（%d → %d）' % (n0 - len(codes), n0, len(codes)))

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


def _prev_close(code):
    """持仓股的昨收价（用于"当天涨幅 > 5%"判定）。取不到返回 None。"""
    try:
        h = attribute_history(code, 1, '1d', ['close'], skip_paused=True, df=False)
        arr = np.asarray(h['close'], dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        if len(arr) == 0:
            return None
        return float(arr[-1])
    except Exception:
        return None


def _hist_close_ma(code, n=MA20_N, price_today=None):
    """
    持仓股的 n 日收盘均线——用于"跌破20日线"。
    MA20_INCLUDE_TODAY=True（默认）时把今天 14:55 的价格当今天收盘算进去；
    False 则只用截至昨天的 n 个收盘。取不到返回 None。
    """
    try:
        h = attribute_history(code, n, '1d', ['close'], skip_paused=True, df=False)
        arr = np.asarray(h['close'], dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        if len(arr) == 0:
            return None
        if MA20_INCLUDE_TODAY and price_today:
            arr = np.append(arr[-n + 1:], float(price_today))
        return float(arr.mean())
    except Exception:
        return None


def _today_range(codes, context):
    """
    当日（截至 14:55）的开盘价 / 最高价 / 最低价，用于判断"跳空"和"盘中是否到过目标价"。
      - 开盘价：get_current_data()[s].day_open（聚宽自带，不用额外请求）
      - 最高/最低：今天 1 分钟线里已走完的 235 根取 max/min
    任何一项拿不到就填 None，判定时自动退回"14:55 价"的老口径。
    """
    out = {}
    if not codes:
        return out
    cd = {}
    try:
        cd = get_current_data()
    except Exception:
        cd = {}
    for s in codes:
        o = None
        try:
            o = getattr(cd[s], 'day_open', None)
        except Exception:
            o = None
        out[s] = {'open': float(o) if o else None, 'high': None, 'low': None}

    for field in ('high', 'low'):
        try:
            df = history(240, '1m', field, codes, df=True, skip_paused=False)
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue
        try:
            idx = pd.to_datetime(df.index)
            todays = idx.normalize() == pd.Timestamp(context.current_dt.date())
            sub = df.loc[todays]
        except Exception:
            continue
        if len(sub) == 0:
            continue
        for s in codes:
            if s not in sub.columns:
                continue
            try:
                ser = sub[s].dropna()
                if len(ser) == 0:
                    continue
                out[s][field] = float(ser.max() if field == 'high' else ser.min())
            except Exception:
                pass
    return out


def _exec_sell(s, context, p, act, why, ma20, entry, ret):
    """
    按 sell_decision() 给的 action 真正下单（14:55 和盘中监控共用这一段）。
    act='all' → 清仓；act='part' → 卖 2/3 留 1/3。返回 True 表示动过手。
    """
    pos = context.portfolio.positions.get(s)
    if pos is None or pos.total_amount == 0:
        return False

    # ---------- 全部卖出 ----------
    if act == 'all':
        order_target(s, 0)
        g.stat['sell_win' if ret > 0 else 'sell_lose'] += 1
        log.info('清仓 %s @%.2f %s 收益%.2f%% (买%.2f 止损%.2f 目标%.2f MA%d=%.2f)'
                 % (s, p, why, ret, entry['buy'], entry['p_low'],
                    entry['target'], MA20_N, ma20 if ma20 else 0.0))
        g.entry.pop(s, None)
        g.buy_date.pop(s, None)
        return True

    # ---------- 到压力区：卖到只剩 1/3 最初仓位，留 1/3 尾巴 ----------
    if act == 'part':
        qty0 = entry.get('qty0') or int(pos.total_amount)
        sold = int(entry.get('sold') or 0)
        sh = tp_part_shares(qty0, sold, pos.total_amount)
        if sh <= 0:
            # 之前放量减仓已经卖够了 2/3 → 到目标价不再卖，只把尾巴转成跟 20 日线
            entry['tp2_done'] = True
            entry['tp2_price'] = float(p)
            g.stat['tp_part'] += 1
            log.info('到目标价 %s @%.2f %s 已卖够2/3，剩%d股继续跟MA%d(%.2f) 收益%.2f%%'
                     % (s, p, why, int(pos.total_amount), MA20_N, ma20, ret))
            return True
        order_target(s, int(pos.total_amount - sh))
        entry['sold'] = sold + sh
        entry['tp2_done'] = True
        entry['tp2_price'] = float(p)
        g.stat['tp_part'] += 1
        log.info('止盈减仓 %s @%.2f %s 卖%d股(累计卖%d/最初%d) 留%d股跟MA%d(%.2f) 收益%.2f%%'
                 % (s, p, why, sh, entry['sold'], qty0,
                    int(pos.total_amount - sh), MA20_N, ma20, ret))
        return True

    return False


def _do_sell(context, today, price=None, vol_today=None):
    """
    卖出，14:55 执行，优先级：
      1) 跌破前低 / 时间止损                → 全部清仓
      2) 到压力区 → 卖到只剩【最初仓位的 1/3】（与 20 日线无关），留 1/3 跟 20 日线
      3) 已经卖过 2/3 的 1/3 尾巴 → 跌破 20 日线清仓
      4) 当日成交量 > 2×MA10(量) → 减仓【最初仓位】的 1/3（剩余不足 2 手时卖一半，
         卖完剩下的不足 1 手就一起清掉）；再次触发要有台阶：≥1.05×上次减仓价 或 当天涨>5%
    1)~3) 成立时不会再执行 4)。

    "到压力区"的判定会带上当日开盘价和盘中最高/最低价（`_today_range()`）：
    开盘就跳空在目标价之上的，不在开盘卖，等盘中回落到目标价再卖。
    """
    price = price or {}
    vol_today = vol_today or {}
    held = [s for s in context.portfolio.positions.keys()
            if context.portfolio.positions[s].total_amount > 0
            and g.entry.get(s) is not None]
    day_range = _today_range(held, context) if held else {}
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

        ma20 = _hist_close_ma(s, MA20_N, p) if TP_FOLLOW_MA else None
        rng = day_range.get(s) or {}
        act, why = sell_decision(p, entry, today, buy_date, ma20,
                                 day_open=rng.get('open'),
                                 day_high=rng.get('high'),
                                 day_low=rng.get('low'))
        ret = (p / entry['buy'] - 1.0) * 100 if entry['buy'] else 0.0

        if act in ('all', 'part'):
            _exec_sell(s, context, p, act, why, ma20, entry, ret)
            continue

        # ---------- 放量减仓：当日量 > 2 × MA10(量) → 卖 1/3【最初仓位】 ----------
        if not sell_allowed(buy_date, today):
            continue
        vt = vol_today.get(s)
        v10 = _hist_vol_ma(s)
        if not vol_exceed(vt, v10):
            continue
        # 再次触发要有台阶：股价 ≥ 1.05×上次减仓价，或当天相对昨收涨幅 > 5%
        anchor = entry.get('vol_anchor')
        if anchor is not None:
            up_5 = p >= float(anchor) * REDUCE_REARM_GAIN
            pct = None
            pc = _prev_close(s)
            if pc:
                pct = float(p) / float(pc) - 1.0
            big_day = pct is not None and pct > REDUCE_REARM_DAY_PCT
            if not (up_5 or big_day):
                continue
        qty0 = entry.get('qty0') or int(pos.total_amount)
        sh = reduce_shares(pos.total_amount, qty0)
        if sh <= 0:
            continue
        left = int(pos.total_amount - sh)
        order_target(s, left)
        entry['sold'] = int(entry.get('sold') or 0) + sh
        entry['vol_anchor'] = float(p)
        g.stat['reduce'] += 1
        log.info('减仓 %s @%.2f 卖%d股(%d/%d)%s 当日量%.0f > %.1f×MA%d(%.0f) 剩余%d股'
                 % (s, p, sh, entry['sold'], qty0,
                    '(清掉碎股)' if left <= 0 else '',
                    vt, REDUCE_VOL_CAP, VOL_L, v10, left))
        if left <= 0:
            g.stat['sell_win' if p > entry['buy'] else 'sell_lose'] += 1
            g.entry.pop(s, None)
            g.buy_date.pop(s, None)


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

    for rr, code, p, st, target, vt, src in picks:
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
            'qty0': int(amt),        # 最初股数：减仓/止盈的份额都按它算
            'sold': 0,               # 累计已卖出股数
            'vol_anchor': None,      # 上次放量减仓的价格（再次减仓要 ≥ 它的 1.05 倍）
        }
        g.buy_date[code] = today
        g.done.add((code, int(st['L_idx'])))      # 这个结构买过了，窗口内不再重复买
        g.stat['buy'] += 1
        slots -= 1
        bought += 1
        log.info('买入 %s @%.2f | L=%.2f(第%d根) 前低=%.2f 目标=%.2f(%s) 盈亏比=%.2f | 窗口第%d/%d根'
                 % (code, cost, st['L'], st['L_idx'], st['p_low'], target, src, rr,
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
# K线实体重合不超过1%（25元→0.25）           is_valid_bear() 的 overlap_ok()：实体上沿-前实体下沿 ≤ 1%×close
# 跌停板可以除外                            is_valid_bear() 的 is_limit_down()
# 倒数第二根阴线 → L                        find_L() 最后一根有效大阴线，L = open
# 至少三根K线下跌比较猛                      is_sharp_decline()：连跌≥3根且累计≥3%
# 段内实体重合都不超过1%（贴住/跳空）        has_body_gaps()，REQUIRE_GAP 开关
# 第一根跌幅>1%或破前低                     first_bar_sharp()，REQUIRE_FIRST_DROP 开关
# 四根k线内完全站上                        detect_setup() 的窗口 wleft >= 0；窗口内任意一天达标都能买
# 上涨的k线也要 >1%（站上那根的涨幅）        stand_gain_ok()，REQUIRE_STAND_GAIN 开关
# 连续三根k线在1%以内算放缓                  slow_run_ok()：窗口放宽到 6 根
# 放缓的3根也不能重合超过1%（否则是反转）    slow_run_ok() 里再过 overlap_ok()，NARROW_OVERLAP 开关
# 同时不可以创新低                          no_new_low()：price >= p_low（磨底小新低允许，反转后冻结）
# 反转那根出现后前低冻结                    find_reversal_idx()：重合>1% 且不创新低，p_low 只取 L 到那根
# 作废①：反转前"重合>1% 又创新低"            detect_setup()：砸盘大阴线创新低 → 新结构（小实体磨底新低不算）
# 作废②：反转后收盘跌破冻结前低              detect_setup()：不看重合，跌破止损位就是新结构
# 价格到达压力区就卖出                       target_hit() 判到价；sell_decision() 决定卖多少
# 持仓期高开在目标价之上 → 不卖等回落          target_hit()：开盘>目标 且 当日最低>目标 → 不卖（GAP_UP_HOLD）
# 到目标价止盈改到盘中执行              handle_data()：每分钟判 到价 → 当场卖（GAP_WATCH_SELL）
# 止损/放量减仓只在 14:55                 handle_data() 遇到"现价≤前低"直接跳过，交给 _do_sell
# 到压力区 → 站上MA20卖到剩1/3初始            sell_decision()：价≥MA20×0.99 返回 'part'；tp_part_shares() 抵扣已减的份额
# 到压力区 → 已跌破MA20则当天全卖             sell_decision()：价<MA20×0.99 返回 'all'（尾巴跟不住均线，不留过夜）
# 剩下1/3跌破20日均线再卖                    sell_decision()：tp2_done + price < ma_band()（MA20×0.99）
# 算不够1手 / 拿不到20日线 → 全卖             tp_part_shares() 返回不足1手时兜底 'all'
# 不能买：两倍十日成交量的K线                volume_ok()：VOL 必须 < 2×MA10(VOL)
# 必须放量过5日均量（10%容差）              volume_ok()：VOL > MA5×(1-VOL_S_TOL)
# 20日均线跌破容差1%                        ma_band(ma20, MA20_TOL)，含当天 MA20_INCLUDE_TODAY=True
# 上一个强压力区很近，盈亏比不满足2:1         risk_reward() >= 2.0；已在区内 → pick_target() 返回 None
# 强压力区：同一股价三根放量K线               find_strong_zones() touch=3（价格区间重合≥3根）
# 影线也算，实体也算                        find_strong_zones() 用 [low, high]，不只看收盘价
# 最高价到昨天这一整段下跌阶段都算            find_strong_zones() 窗口 = [find_peak_idx(), 昨天]
# 只有下降波段才有压力，涨回去就释放          released_mask()：后面最高价≥本根最高价（整根覆盖）→ 释放
# 每个下跌起点的左边那几根                    find_all_swing_highs() + ZONE_KEEP_PREV_HIGH=3（无条件保留）
# 压力区很近 → 目标取最近的那个              pick_target()：上方最近压力区的下沿；已在区内则不买
# 上方没压力区 → 按 120 日高点空间兜底         fallback_target()：target = 买入+2×(买入-前低)，须 ≤ 120 日最高价
# 成交量 > 买入当天那根K线的成交量           find_strong_zones(v0=买入当天量)
# 同一个结构只买一次                        g.done 记 (code, L_idx)，ONE_TRADE_PER_SETUP 开关
# 买入后遇当日量 > 2×MA10 → 减仓1/3初始      _do_sell()：vol_exceed() + reduce_shares(最初仓位)；剩余不足2手卖一半，卖完剩不足1手清仓
# 再减要涨回1.05倍或当天涨5%                 _do_sell()：vol_anchor×REDUCE_REARM_GAIN / _prev_close()
#
# =============================================================================
