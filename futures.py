"""国内商品期货研究原型，Python 3.10+，仅标准库。

运行：python futures.py --demo
测试：python futures.py --test
真实数据：python futures.py --csv bars.csv --config contract.json
CSV 必须含 timestamp,trading_day,open,high,low,close；单一实际合约，
timestamp 为不带时区的北京时间 ISO 格式，trading_day 由数据源提供。
配置键见 Config；数值均为演示假设，不能当作任何真实合约参数。
输出到 --out（默认 results）：summary.json, trades.csv, equity.csv。

已实现：收盘均线信号、下一根开盘成交、多空一手、开平/平今费率、
固定每手费用+成交金额费率、滑点、保证金准入、收盘止损/日亏损停开。
限制：风控收盘触发后下一开盘执行；不模拟盘中路径、涨跌停排队、
强平、结算价结算、换月及交易日历；无实时行情、实盘或 AI 训练。
末根收盘按滑点清仓属于回测终止约定。禁止据此直接实盘。
"""
import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class Config:
    capital: float = 100000
    multiplier: float = 10
    tick: float = 1
    slippage_ticks: int = 1
    margin_rate: float = .15
    max_margin_fraction: float = .30
    open_fixed: float = 3
    close_fixed: float = 3
    close_today_fixed: float = 3
    open_rate: float = 0
    close_rate: float = 0
    close_today_rate: float = 0
    fast: int = 5
    slow: int = 20
    stop_loss_fraction: float = .02
    daily_loss_fraction: float = .02

    def validate(self):
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in asdict(self).values()):
            raise ValueError('配置必须为有限数值')
        if not (isinstance(self.fast, int) and isinstance(self.slow, int) and 1 <= self.fast < self.slow):
            raise ValueError('均线窗口须为整数且 1 <= fast < slow')
        if min(self.capital, self.multiplier, self.tick) <= 0:
            raise ValueError('资金、乘数、最小变动价位必须大于零')
        if not isinstance(self.slippage_ticks, int) or self.slippage_ticks < 0:
            raise ValueError('滑点必须是非负整数')
        for key in ('margin_rate', 'max_margin_fraction', 'stop_loss_fraction', 'daily_loss_fraction'):
            if not 0 < getattr(self, key) <= 1:
                raise ValueError(key + ' 必须在 (0,1]')
        if any(getattr(self, k) < 0 for k in asdict(self) if k.endswith(('_fixed', '_rate'))):
            raise ValueError('费用不能为负数')


def validate_bars(bars):
    if not bars:
        raise ValueError('没有行情')
    previous = None
    previous_day = None
    for b in bars:
        t = datetime.fromisoformat(b['timestamp'])
        day = datetime.strptime(b['trading_day'], '%Y-%m-%d').date()
        if t.tzinfo is not None or (previous and t <= previous):
            raise ValueError('时间必须为北京时间、严格递增且不能重复')
        if previous_day and day < previous_day:
            raise ValueError('交易日不能倒退')
        previous, previous_day = t, day
        prices = [b[k] for k in ('open', 'high', 'low', 'close')]
        if not all(math.isfinite(v) and v > 0 for v in prices):
            raise ValueError('价格必须为正有限数')
        if not b['low'] <= min(b['open'], b['close']) <= max(b['open'], b['close']) <= b['high']:
            raise ValueError('OHLC 范围错误')


def backtest(bars, c):
    c.validate()
    validate_bars(bars)
    cash, pos, entry, entry_day = c.capital, 0, 0, ''
    target, day, blocked = 0, None, False
    day_start, peak, drawdown = cash, cash, 0
    closes, trades, curve = [], [], []

    def equity(price):
        return cash + pos * (price - entry) * c.multiplier

    def execute(new_pos, raw_price, b, reason):
        nonlocal cash, pos, entry, entry_day
        if new_pos == pos:
            return
        # Reversal closes first, then checks the new entry independently.
        if pos:
            px = raw_price - pos * c.tick * c.slippage_ticks
            kind = 'close_today' if b['trading_day'] == entry_day else 'close'
            fee = getattr(c, kind + '_fixed') + abs(px) * c.multiplier * getattr(c, kind + '_rate')
            pnl = pos * (px - entry) * c.multiplier
            cash += pnl - fee
            trades.append(dict(timestamp=b['timestamp'], action=kind, side=-pos, price=px, fee=fee, realized_pnl=pnl, reason=reason))
            pos = 0
        if new_pos:
            px = raw_price + new_pos * c.tick * c.slippage_ticks
            fee = c.open_fixed + abs(px) * c.multiplier * c.open_rate
            required = abs(px) * c.multiplier * c.margin_rate
            if px <= 0 or cash - fee <= 0 or required > (cash - fee) * c.max_margin_fraction:
                return
            cash -= fee
            pos, entry, entry_day = new_pos, px, b['trading_day']
            trades.append(dict(timestamp=b['timestamp'], action='open', side=pos, price=px, fee=fee, realized_pnl=0, reason=reason))

    for i, b in enumerate(bars):
        if b['trading_day'] != day:
            day = b['trading_day']
            day_start = curve[-1]['equity'] if curve else cash
            blocked = False
        execute(0 if blocked else target, b['open'], b, 'pending_signal_or_risk')
        value = equity(b['close'])
        if value <= day_start * (1 - c.daily_loss_fraction):
            blocked = True
        stop = bool(pos and pos * (b['close'] - entry) <= -entry * c.stop_loss_fraction)
        closes.append(b['close'])
        target = 0
        if len(closes) >= c.slow and not blocked and not stop:
            delta = sum(closes[-c.fast:]) / c.fast - sum(closes[-c.slow:]) / c.slow
            target = (delta > 0) - (delta < 0)
        if i == len(bars) - 1:
            execute(0, b['close'], b, 'end_of_data')
            value = cash
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
        curve.append(dict(timestamp=b['timestamp'], trading_day=day, equity=value, position=pos, daily_blocked=blocked))
    return dict(initial_capital=c.capital, final_equity=cash, net_pnl=cash-c.capital, return_fraction=cash/c.capital-1, max_drawdown_fraction=drawdown, fills=len(trades), fees=sum(t['fee'] for t in trades)), trades, curve


def demo():
    bars = []
    for i in range(160):
        t = datetime(2025, 1, 1) + timedelta(days=i)
        price = 3500 + round(100 * math.sin(i / 9))
        bars.append(dict(timestamp=t.isoformat(), trading_day=t.date().isoformat(), open=price, high=price+10, low=price-10, close=price+2))
    return bars  # 合成序列含周末，不代表交易日历或历史价格。


def self_test():
    import unittest
    class EngineTests(unittest.TestCase):
        def test_accounting(self):
            s, ts, _ = backtest(demo(), Config())
            self.assertAlmostEqual(s['net_pnl'], sum(t['realized_pnl']-t['fee'] for t in ts))
        def test_next_open(self):
            bars = demo()
            _, ts, _ = backtest(bars, Config())
            self.assertEqual(ts[0]['timestamp'], bars[20]['timestamp'])
            self.assertEqual(ts[0]['price'], bars[20]['open'] + ts[0]['side'])
        def test_margin_reject(self):
            self.assertEqual(backtest(demo(), Config(capital=1))[0]['fills'], 0)
        def test_bad_data(self):
            bars = demo(); bars[1]['timestamp'] = bars[0]['timestamp']
            with self.assertRaises(ValueError): backtest(bars, Config())
        def test_no_lookahead(self):
            bars = demo(); changed = [dict(b) for b in bars]
            for b in changed[90:]:
                for k in ('open','high','low','close'): b[k] += 200
            a = backtest(bars, Config())[2]
            b = backtest(changed, Config())[2]
            self.assertEqual(a[:90], b[:90])
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EngineTests))
    raise SystemExit(not result.wasSuccessful())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--demo', action='store_true'); g.add_argument('--csv'); g.add_argument('--test', action='store_true')
    p.add_argument('--config'); p.add_argument('--out', default='results')
    args = p.parse_args()
    if args.test: self_test()
    if args.csv and not args.config: p.error('真实数据必须提供 --config 合约参数 JSON')
    c = Config(**json.loads(Path(args.config).read_text(encoding='utf-8'))) if args.config else Config()
    if args.demo:
        bars = demo()
    else:
        with open(args.csv, encoding='utf-8-sig', newline='') as f:
            bars = [{**r, **{k: float(r[k]) for k in ('open','high','low','close')}} for r in csv.DictReader(f)]
    summary, trades, curve = backtest(bars, c)
    summary.update(synthetic_data=bool(args.demo), config=asdict(c))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, rows, fields in [('trades', trades, ['timestamp','action','side','price','fee','realized_pnl','reason']), ('equity', curve, list(curve[0]))]:
        with (out / (name+'.csv')).open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
