import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from goldbot import indicators as ta
from goldbot.backtest import position_size, run_backtest
from goldbot.data import Candle, make_demo, drop_forming
from goldbot.strategy import Indicators, Params, evaluate


def flat_then(candles_spec, n_warm=260, price=2000.0):
    """Tekis (trendsiz) qator + berilgan (o,h,l,c) candle'lar."""
    t = datetime(2025, 1, 6)
    out = []
    for _ in range(n_warm):
        out.append(Candle(t, price, price + 0.5, price - 0.5, price)); t += timedelta(hours=1)
    for o, h, l, c in candles_spec:
        out.append(Candle(t, o, h, l, c)); t += timedelta(hours=1)
    return out


class TestIndicators(unittest.TestCase):
    def test_sma_ema(self):
        v = [1, 2, 3, 4, 5, 6]
        self.assertEqual(ta.sma(v, 3)[2:], [2, 3, 4, 5])
        e = ta.ema(v, 3)
        self.assertAlmostEqual(e[2], 2.0)
        self.assertAlmostEqual(e[3], 4 * 0.5 + 2.0 * 0.5)

    def test_rsi_bounds_and_trend(self):
        up = [float(i) for i in range(60)]
        self.assertEqual(ta.rsi(up, 14)[-1], 100.0)
        dn = [float(-i) for i in range(60)]
        self.assertAlmostEqual(ta.rsi(dn, 14)[-1], 0.0)

    def test_atr_constant_range(self):
        h = [10.0] * 40; l = [9.0] * 40; c = [9.5] * 40
        self.assertAlmostEqual(ta.atr(h, l, c, 14)[-1], 1.0)

    def test_adx_strong_trend(self):
        c = [100 + i * 1.0 for i in range(120)]
        h = [x + 0.3 for x in c]; l = [x - 0.3 for x in c]
        a, pdi, mdi = ta.adx(h, l, c, 14)
        self.assertGreater(a[-1], 60)
        self.assertGreater(pdi[-1], mdi[-1])


class TestNoLookahead(unittest.TestCase):
    def test_signal_unchanged_when_future_removed(self):
        candles = make_demo(1500, seed=3)
        p = Params()
        full = Indicators(candles, p)
        for i in (400, 800, 1200, 1499):
            part = Indicators(candles[:i + 1], p)
            a, b = evaluate(full, i, p), evaluate(part, i, p)
            self.assertEqual((a.action, a.score), (b.action, b.score))


class TestSizing(unittest.TestCase):
    def test_risk_respected(self):
        p = Params()
        lots, oz = position_size(5000, 5.0, 2350, p)       # risk $50 / 5 = 10 oz = 0.10 lot
        self.assertAlmostEqual(lots, 0.10)
        self.assertLessEqual(oz * 5.0, 50.0 + 1e-9)

    def test_leverage_cap_and_min_lot(self):
        p = Params(max_leverage=1.0)
        lots, oz = position_size(5000, 0.5, 2500, p)       # cheklov: 2 oz -> 0.02 lot
        self.assertAlmostEqual(lots, 0.02)
        lots, _ = position_size(100, 5.0, 2500, p)         # 0.04 oz -> minimal lotga yetmaydi
        self.assertEqual(lots, 0.0)


class TestFills(unittest.TestCase):
    def _force_trade(self, side, bar, bar2=None):
        """Majburiy kirish: bitta pending signalni qo'lda bermaymiz — evaluate ni almashtiramiz."""
        import goldbot.backtest as bt
        from goldbot.strategy import Signal
        candles = flat_then([(2000, 2000.5, 1999.5, 2000), bar] + ([bar2] if bar2 else []))
        p = Params(use_session=False, stop_atr=1.5, target_r=2.0, spread=0.0, slippage=0.0, breakeven_r=0, max_bars=0,
                   daily_loss_pct=100, risk_pct=1.0)
        ind = Indicators(candles, p)
        n_before = len(candles) - (3 if bar2 else 2)
        orig = bt.evaluate
        def fake(ind_, j, p_):
            s = Signal(time=ind_.t[j], price=ind_.c[j], atr=2.0)
            if j == n_before:
                s.action = "BUY" if side == 1 else "SELL"
            return s
        bt.evaluate = fake
        try:
            res = run_backtest(candles, p, ind)
        finally:
            bt.evaluate = orig
        return res["trades"]

    def test_gap_down_through_stop_fills_at_open(self):
        # BUY kirish 2000, ATR 2 -> stop 1997. Keyingi candle 1990 da ochiladi (gap) -> 1990 da chiqish.
        trades = self._force_trade(1, (2000, 2000.2, 1999.9, 2000.0), (1990, 1991, 1989, 1990))
        self.assertEqual(trades[0]["reason"], "stop")
        self.assertAlmostEqual(trades[0]["exit"], 1990.0, places=6)
        self.assertLess(trades[0]["r"], -3.0)      # -1R emas: gap zarari kattaroq

    def test_stop_first_when_both_hit(self):
        trades = self._force_trade(1, (2000, 2010, 1990, 2000))   # ikkalasi ham tegadi
        self.assertEqual(trades[0]["reason"], "stop")
        self.assertLess(trades[0]["net_pnl"], 0)

    def test_target_hit(self):
        trades = self._force_trade(1, (2000, 2007, 1999, 2006))   # target = 2000+2*3 = 2006
        self.assertEqual(trades[0]["reason"], "target")
        self.assertAlmostEqual(trades[0]["r"], 2.0, places=3)


class TestForming(unittest.TestCase):
    def test_drops_unclosed_last_candle(self):
        c = flat_then([], n_warm=60)
        last = c[-1].time
        kept, dropped = drop_forming(c, now=last + timedelta(minutes=30))   # oxirgi soat hali yopilmagan
        self.assertTrue(dropped); self.assertEqual(len(kept), len(c) - 1)
        kept, dropped = drop_forming(c, now=last + timedelta(hours=1, minutes=1))
        self.assertFalse(dropped); self.assertEqual(len(kept), len(c))


class TestBacktestSmoke(unittest.TestCase):
    def test_runs_and_balances(self):
        candles = make_demo(3000, seed=5)
        p = Params()
        res = run_backtest(candles, p)
        total = sum(t["net_pnl"] for t in res["trades"])
        self.assertAlmostEqual(res["balance"], p.start_balance + total, places=6)
        for t in res["trades"]:
            self.assertLessEqual(t["risk_usd"], p.start_balance * 3 * p.risk_pct / 100)  # risk limiti


if __name__ == "__main__":
    unittest.main()
