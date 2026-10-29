# -*- coding: utf-8 -*-
"""
离线冒烟测试：用假的聚宽环境跑完整 trade_1455 流程，验证"能真的成交 / 能真的卖出"。

运行：python local_test\test_strategy_flow.py

场景 A：构造一只股票走完 急跌→有效大阴线→窗口内放量站上 L→盈亏比2.3，断言买入 1 笔
场景 B：已持仓且价格跌破前低，断言 14:55 触发止损卖出
场景 C：当日量达 2 倍均量 → 买入被否决
场景 D：价格没站上 L → 不买
场景 E：已持仓 + 当日量 2.5 倍均量 → 减仓 1/3（1000股→卖300股，剩700股）
场景 F：已持仓 + 当日量 1.5 倍均量 → 不减仓
"""

import os
import sys
import types
import datetime
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import jq_strong_structure as S   # noqa: E402

CODE = '000001.XSHE'
FAILED = []
PASSED = [0]


def check(name, cond, detail=''):
    if cond:
        PASSED[0] += 1
        print('  PASS  %s' % name)
    else:
        FAILED.append(name)
        print('  FAIL  %s   %s' % (name, detail))


# ---------------------------------------------------------------------------
# 构造 60 根日线：53 根横盘(28.00) + 4 根急跌 + 3 根反抽，最后一根(idx56)是有效大阴线 L
# ---------------------------------------------------------------------------
def flat(k, price=28.0, vol=1000.0):
    return [(price, price, price + 0.05, price - 0.05, vol)] * k


def bar(o, c, vol=1000.0):
    return (o, c, max(o, c) + 0.05, min(o, c) - 0.05, vol)


def build_history():
    rows = flat(53)
    for i in (5, 6, 7):                 # 三根放量横盘 → 28.00 成为强压力区
        rows[i] = (28.0, 28.0, 28.05, 27.95, 2000.0)
    rows += [
        bar(28.00, 27.10),              # 53 跌
        bar(27.00, 26.10),              # 54 跌
        bar(26.20, 25.20),              # 55 跌
        bar(24.90, 24.00),              # 56 有效大阴线  L = 24.90
        bar(24.30, 24.30),              # 57 反抽
        bar(24.05, 24.05),              # 58
        bar(24.35, 24.35),              # 59
    ]
    o = np.array([r[0] for r in rows], float)
    c = np.array([r[1] for r in rows], float)
    h = np.array([r[2] for r in rows], float)
    l = np.array([r[3] for r in rows], float)
    v = np.array([r[4] for r in rows], float)
    return o, c, h, l, v


O, C, H, L, V = build_history()
N = len(C)


# ---------------------------------------------------------------------------
# 假聚宽环境
# ---------------------------------------------------------------------------
class Log(object):
    def set_level(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warn(self, *a, **k):
        pass

    def error(self, msg, *a, **k):
        raise RuntimeError('日志错误: %s' % msg)


class Obj(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Portfolio(object):
    def __init__(self, cash=1000000.0):
        self.available_cash = cash
        self.total_value = cash
        self.positions = {}

    def refresh(self):
        val = self.available_cash + sum(
            p.total_amount * p.last for p in self.positions.values())
        self.total_value = val


ORDERS = []


def make_env(now_price, now_vol, today, yesterday):
    """返回挂到 S 模块上的全局函数集合。"""

    def get_price(security, end_date=None, count=None, fields=None,
                  skip_paused=True, fq='pre', panel=False):
        codes = [security] if isinstance(security, str) else list(security)
        frames = []
        k = min(count or N, N)
        for s in codes:
            df = pd.DataFrame({
                'code': [s] * k,
                'time': pd.date_range(end=pd.Timestamp(end_date), periods=k, freq='B'),
                'open': O[-k:], 'close': C[-k:], 'high': H[-k:],
                'low': L[-k:], 'volume': V[-k:],
            })
            frames.append(df)
        out = pd.concat(frames, ignore_index=True)
        return out.sort_values(['code', 'time']).reset_index(drop=True)

    def get_current_data():
        return {CODE: Obj(paused=False, is_st=False, last_price=now_price,
                          high_limit=30.0, low_limit=20.0)}

    def history(count, unit='1d', field='avg', security_list=None, df=True,
                skip_paused=False, fq='pre'):
        codes = [security_list] if isinstance(security_list, str) else list(security_list)
        idx = pd.date_range(end=pd.Timestamp(today) + pd.Timedelta(hours=14, minutes=55),
                            periods=int(count), freq='min')
        per = float(now_vol) / float(count)
        data = {s: [per] * int(count) for s in codes}
        return pd.DataFrame(data, index=idx)

    def attribute_history(security, count, unit='1d', fields=None,
                          skip_paused=True, df=False, fq='pre'):
        k = min(int(count), N)
        return {f: np.array(V[-k:], dtype=float) for f in (fields or ['volume'])}

    def get_all_securities(types=None, date=None):
        return pd.DataFrame({'display_name': ['测试股'],
                             'start_date': [datetime.date(2015, 1, 5)],
                             'end_date': [datetime.date(2030, 1, 1)]}, index=[CODE])

    def order_target_value(security, value):
        ORDERS.append(('buy', security, value))
        price = now_price
        amt = int(value / price / 100) * 100
        pf = CURRENT['portfolio']
        cost = amt * price
        if cost > pf.available_cash:
            amt = int(pf.available_cash / price / 100) * 100
            cost = amt * price
        pf.available_cash -= cost
        pf.positions[security] = Obj(total_amount=amt, avg_cost=price, last=price)
        return Obj()

    def order_target(security, amount):
        ORDERS.append(('sell', security, amount))
        pf = CURRENT['portfolio']
        pos = pf.positions.get(security)
        if pos is None:
            return Obj()
        target = int(amount)
        sold = int(pos.total_amount) - target
        if sold <= 0:
            return Obj()
        pf.available_cash += sold * now_price
        if target <= 0:
            pf.positions.pop(security, None)
        else:
            pos.total_amount = target
        return Obj()

    def run_daily(func, time='14:55'):
        CURRENT['daily'] = (func, time)

    def noop(*a, **k):
        return None

    S.g = types.SimpleNamespace()
    S.log = Log()
    S.get_price = get_price
    S.get_current_data = get_current_data
    S.history = history
    S.attribute_history = attribute_history
    S.get_all_securities = get_all_securities
    S.get_index_stocks = lambda *a, **k: []
    S.order_target_value = order_target_value
    S.order_target = order_target
    S.run_daily = run_daily
    S.set_benchmark = noop
    S.set_option = noop
    S.set_order_cost = noop
    S.set_slippage = noop
    S.log = Log()
    # 类名占位
    S.OrderCost = lambda **k: None
    S.PriceRelatedSlippage = lambda x: None


CURRENT = {}


def run_scenario(name, now_price, now_vol, cash=1000000.0):
    del ORDERS[:]
    today = datetime.date(2024, 6, 3)
    yesterday = datetime.date(2024, 5, 31)
    make_env(now_price, now_vol, today, yesterday)
    pf = Portfolio(cash)
    CURRENT['portfolio'] = pf
    ctx = Obj(current_dt=datetime.datetime(2024, 6, 3, 14, 55),
              previous_date=yesterday, portfolio=pf)
    S.initialize(ctx)
    S.trade_1455(ctx)
    return ctx, pf


def run_hold(now_price, now_vol, shares=1000):
    """已持仓场景：先跑一遍初始流程（把 g 初始化好），再注入昨天的持仓，重跑一次。"""
    ctx, pf = run_scenario('hold', now_price, now_vol)
    pf.positions.clear()
    pf.positions[CODE] = Obj(total_amount=shares, avg_cost=25.0, last=now_price)
    S.g.entry[CODE] = {'L': 24.90, 'p_low': 22.50, 'target': 30.0, 'buy': 25.0,
                       'rr': 2.0, 'L_idx': 56,
                       'buy_date': datetime.date(2024, 5, 30)}
    S.g.buy_date[CODE] = datetime.date(2024, 5, 30)
    S.g.stat['reduce'] = 0
    del ORDERS[:]
    S.trade_1455(ctx)
    return ctx, pf


def main():
    print('\n[场景 A] 急跌 → 14:55 放量站上 L → 应买入 1 笔')
    ctx, pf = run_scenario('A', now_price=25.20, now_vol=1500.0)
    buys = [x for x in ORDERS if x[0] == 'buy']
    check('A1 触发了定时任务', CURRENT.get('daily', (None,))[1] == '14:55',
          str(CURRENT.get('daily')))
    check('A2 买入 1 笔', len(buys) == 1, str(ORDERS))
    check('A3 有持仓', len(pf.positions) == 1, str(pf.positions))
    e = S.g.entry.get(CODE)
    check('A4 记录了 L/前低/目标', e is not None and abs(e['L'] - 24.90) < 0.01
          and abs(e['p_low'] - 24.00) < 0.01 and abs(e['target'] - 27.95) < 0.01,
          str(e))
    check('A5 盈亏比≥2', e is not None and e['rr'] >= 2.0, str(e and e['rr']))

    print('\n[场景 B] 已持仓 + 价格跌破前低 → 应止损卖出')
    ctx, pf = run_scenario('B', now_price=22.40, now_vol=1500.0)
    # 手工塞入一个昨天的持仓（模拟持有中）
    pf.positions[CODE] = Obj(total_amount=1000, avg_cost=25.0, last=22.40)
    S.g.entry[CODE] = {'L': 24.90, 'p_low': 22.50, 'target': 30.0,
                       'buy': 25.0, 'rr': 2.0, 'L_idx': 56, 'buy_date': datetime.date(2024, 5, 30)}
    S.g.buy_date[CODE] = datetime.date(2024, 5, 30)
    del ORDERS[:]
    S.trade_1455(ctx)
    sells = [x for x in ORDERS if x[0] == 'sell']
    check('B1 触发止损卖出', len(sells) == 1, str(ORDERS))
    check('B2 清空持仓记录', CODE not in S.g.entry)
    check('B3 卖出后未追高买回', all(x[0] == 'sell' for x in ORDERS)
          or [x for x in ORDERS if x[0] == 'buy'] == [], str(ORDERS))

    print('\n[场景 C] 当日成交量达到 2 倍 10 日均量 → 应否决，不买')
    ctx, pf = run_scenario('C', now_price=25.20, now_vol=2500.0)
    check('C1 2倍量不买', len([x for x in ORDERS if x[0] == 'buy']) == 0, str(ORDERS))

    print('\n[场景 D] 价格没站上 L → 不买')
    ctx, pf = run_scenario('D', now_price=24.50, now_vol=1500.0)
    check('D1 未站上L不买', len([x for x in ORDERS if x[0] == 'buy']) == 0, str(ORDERS))

    print('\n[场景 E] 持仓 + 当日量 2.5 倍均量 → 卖出 1/3 持仓（1000股 → 卖300股）')
    ctx, pf = run_hold(now_price=25.20, now_vol=2500.0, shares=1000)
    sells = [x for x in ORDERS if x[0] == 'sell']
    check('E1 触发减仓 1 笔', len(sells) == 1, str(ORDERS))
    check('E2 减仓后剩 700 股',
          pf.positions.get(CODE) is not None
          and pf.positions[CODE].total_amount == 700, str(pf.positions))
    check('E3 减仓不清空记录（还持有着）', CODE in S.g.entry, str(list(S.g.entry)))
    check('E4 计数 reduce=1', S.g.stat.get('reduce') == 1, str(S.g.stat))

    print('\n[场景 F] 持仓 + 当日量 1.5 倍均量 → 未到 2 倍，不减仓')
    ctx, pf = run_hold(now_price=25.20, now_vol=1500.0, shares=1000)
    check('F1 不减仓', len([x for x in ORDERS if x[0] == 'sell']) == 0, str(ORDERS))
    check('F2 持仓不变 1000 股',
          pf.positions.get(CODE) is not None
          and pf.positions[CODE].total_amount == 1000, str(pf.positions))

    print('\n' + '=' * 60)
    total = PASSED[0] + len(FAILED)
    if FAILED:
        print('结果：%d/%d 通过，失败：%s' % (PASSED[0], total, ', '.join(FAILED)))
        return 1
    print('结果：%d/%d 全部通过 ✅' % (PASSED[0], total))
    return 0


if __name__ == '__main__':
    sys.exit(main())
