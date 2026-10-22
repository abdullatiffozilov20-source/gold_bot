"""Backtest: gap-ga chidamli, xarajatli, to'g'ri risk hajmli simulyator + walk-forward."""
import itertools
import math
import random
from dataclasses import replace

from .strategy import Indicators, evaluate, levels


def position_size(balance, stop_dist, entry, p):
    """Risk bo'yicha hajm (lot, oz). Leverage chegarasi va lot qadami hisobga olinadi."""
    if stop_dist <= 0 or balance <= 0:
        return 0.0, 0.0
    oz = min(balance * p.risk_pct / 100.0 / stop_dist, balance * p.max_leverage / entry)
    lot_oz = p.lot_step * p.contract_size
    lots = round(math.floor(oz / lot_oz + 1e-9) * p.lot_step, 6)
    return lots, lots * p.contract_size


def _close(pos, raw_exit, time, reason, p):
    half = p.spread / 2 + p.slippage
    fill = raw_exit - pos["side"] * half          # chiqishda ham narx noqulay tomonga siljiydi
    gross = (fill - pos["entry"]) * pos["side"] * pos["oz"]
    net = gross - 2 * pos["lots"] * p.commission_per_lot
    risk = pos["oz"] * pos["sd"]
    return {
        "entry_time": pos["time"], "exit_time": time,
        "side": "BUY" if pos["side"] == 1 else "SELL",
        "entry": pos["entry"], "exit": fill, "lots": pos["lots"],
        "risk_usd": risk, "net_pnl": net, "r": net / risk if risk else 0.0,
        "bars": pos["bars"], "reason": reason,
    }


def run_backtest(candles, p, ind=None, start=None, end=None):
    """candles[start:end] oralig'ida savdo qiladi (indikatorlar butun qatordan olinadi,
    shuning uchun segment boshida 'isitish' yo'qolmaydi)."""
    ind = ind or Indicators(candles, p)
    n = ind.n
    lo = max(start or 0, ind.warmup)
    hi = min(end or n, n)
    balance = p.start_balance
    peak, max_dd = balance, 0.0
    pos, pending = None, None
    trades, daily, dcount = [], {}, {}

    def book(trade):
        nonlocal balance, peak, max_dd
        balance += trade["net_pnl"]
        peak = max(peak, balance)
        max_dd = max(max_dd, peak - balance)
        trades.append(trade)
        day = trade["exit_time"].date()
        daily[day] = daily.get(day, 0.0) + trade["net_pnl"]

    for j in range(lo, hi):
        t = ind.t[j]
        o, h, l, c = ind.o[j], ind.h[j], ind.l[j], ind.c[j]
        half = p.spread / 2 + p.slippage

        # 1) Kutilayotgan signal bo'yicha shu candle ochilishida kirish
        if pending and pos is None:
            side, atr_v = pending
            pending = None
            entry = o + side * half
            stop, target, sd = levels(side, entry, atr_v, p)
            lots, oz = position_size(balance, sd, entry, p)
            if lots > 0:
                pos = {"side": side, "entry": entry, "stop": stop, "target": target,
                       "sd": sd, "lots": lots, "oz": oz, "time": t, "bars": 0, "be": False}
                dcount[t.date()] = dcount.get(t.date(), 0) + 1
        pending = None

        # 2) Ochiq pozitsiyani boshqarish (kirish candle'ining o'zida ham)
        if pos:
            d = pos["side"]
            pos["bars"] += 1
            stop_hit = l <= pos["stop"] if d == 1 else h >= pos["stop"]
            tgt_hit = h >= pos["target"] if d == 1 else l <= pos["target"]
            if stop_hit:                                  # ikkalasi tegsa — stop birinchi
                raw = min(o, pos["stop"]) if d == 1 else max(o, pos["stop"])   # gap
                reason = "breakeven" if pos["be"] and abs(pos["stop"] - pos["entry"]) < 1e-9 else "stop"
                book(_close(pos, raw, t, reason, p))
                pos = None
            elif tgt_hit:
                raw = max(o, pos["target"]) if d == 1 else min(o, pos["target"])
                book(_close(pos, raw, t, "target", p))
                pos = None
            elif p.max_bars and pos["bars"] >= p.max_bars:
                book(_close(pos, c, t, "time", p))
                pos = None
            elif p.breakeven_r > 0 and not pos["be"]:
                fav = (h - pos["entry"]) if d == 1 else (pos["entry"] - l)
                if fav >= p.breakeven_r * pos["sd"]:      # kuchga kirishi KEYINGI candle'dan
                    pos["stop"], pos["be"] = pos["entry"], True

        # 3) Yangi signal (candle yopilganda) -> keyingi candle ochilishida kirish
        if pos is None and j + 1 < hi:
            day = t.date()
            if (daily.get(day, 0.0) > -balance * p.daily_loss_pct / 100.0
                    and dcount.get(day, 0) < p.max_daily_trades):
                sig = evaluate(ind, j, p)
                if sig.side and sig.atr > 0:
                    pending = (sig.side, sig.atr)

    if pos:                                               # oxirida halol yopish
        book(_close(pos, ind.c[hi - 1], ind.t[hi - 1], "end_of_data", p))

    return {"trades": trades, "balance": balance, "max_dd": max_dd,
            "start": lo, "end": hi, "bh_pct": 100.0 * (ind.c[hi - 1] / ind.c[lo] - 1.0)}


def summarize(result, p, boot=2000, seed=1):
    tr = result["trades"]
    n = len(tr)
    pnl = [t["net_pnl"] for t in tr]
    rs = [t["r"] for t in tr]
    wins = [x for x in pnl if x > 0]
    loss = [x for x in pnl if x <= 0]
    gp, gl = sum(wins), -sum(loss)
    streak = cur = 0
    for x in pnl:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    net = result["balance"] - p.start_balance
    sm = {
        "n": n, "net": net, "return_pct": 100 * net / p.start_balance,
        "win_rate": 100 * len(wins) / n if n else 0.0,
        "pf": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0),
        "avg_r": sum(rs) / n if n else 0.0, "total_r": sum(rs),
        "avg_win": gp / len(wins) if wins else 0.0,
        "avg_loss": -gl / len(loss) if loss else 0.0,
        "max_dd": result["max_dd"], "max_dd_pct": 100 * result["max_dd"] / p.start_balance,
        "max_losing_streak": streak, "bh_pct": result["bh_pct"],
        "avg_bars": sum(t["bars"] for t in tr) / n if n else 0.0,
        "prob_profit": None, "p5_total_r": None,
    }
    if n >= 20 and boot > 0:                              # bootstrap: natija omadmi?
        rnd = random.Random(seed)
        tot = sorted(sum(rnd.choice(rs) for _ in range(n)) for _ in range(boot))
        sm["prob_profit"] = sum(1 for x in tot if x > 0) / boot
        sm["p5_total_r"] = tot[int(0.05 * boot)]
    sm["verdict"] = verdict(sm)
    return sm


def verdict(sm):
    n = sm["n"]
    if n < 30:
        return "YETARLI EMAS — savdolar soni 30 dan kam, xulosa chiqarib bo'lmaydi"
    if sm["avg_r"] <= 0 or sm["pf"] < 1.1:
        return "USTUNLIK TOPILMADI — bu ma'lumotda strategiya pul ishlamadi"
    if n < 100 or (sm["prob_profit"] or 0) < 0.90:
        return "EHTIYOT — natija shovqin (tasodif) bo'lishi mumkin, ko'proq ma'lumot kerak"
    return "UMIDLI — lekin real pul emas, avval demo hisobda tekshiring"


GRID = {
    "adx_min": [15.0, 20.0, 25.0],
    "stop_atr": [1.0, 1.5, 2.0],
    "target_r": [1.5, 2.0, 3.0],
    "min_score": [5, 6, 7],
}


def walk_forward(candles, base, grid=None, folds=4, min_train_trades=15, progress=None):
    """Anchored walk-forward: har bosqichda parametrlar FAQAT o'tmishda tanlanadi,
    keyin ko'rilmagan keyingi bo'lakda sinaladi. Faqat out-of-sample natija hisobga olinadi."""
    grid = grid or GRID
    ind = Indicators(candles, base)
    usable = ind.n - ind.warmup
    if usable < (folds + 1) * 300:
        raise ValueError("Walk-forward uchun ma'lumot kam (kamida ~%d candle kerak)."
                         % ((folds + 1) * 300 + ind.warmup))
    chunk = usable // (folds + 1)
    keys = list(grid)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(grid[k] for k in keys))]
    rows, all_trades = [], []
    for k in range(1, folds + 1):
        tr_start, tr_end = ind.warmup, ind.warmup + k * chunk
        te_end = ind.n if k == folds else tr_end + chunk
        best, best_score = None, -1e9
        for cfg in combos:
            pp = replace(base, **cfg)
            r = run_backtest(candles, pp, ind, tr_start, tr_end)
            nt = len(r["trades"])
            if nt < min_train_trades:
                continue
            avg_r = sum(t["r"] for t in r["trades"]) / nt
            score = avg_r * math.sqrt(nt)                 # t-statistikaga o'xshash mezon
            if score > best_score:
                best, best_score = cfg, score
        if best is None:
            best = {}                                     # yetarli savdo yo'q -> default
        pp = replace(base, **best)
        te = run_backtest(candles, pp, ind, tr_end, te_end)
        sm = summarize(te, pp, boot=0)
        rows.append({"fold": k, "cfg": best, "train_score": best_score, "test": sm,
                     "from": ind.t[tr_end], "to": ind.t[te_end - 1]})
        all_trades.extend(te["trades"])
        if progress:
            progress(k, folds)
    gp = sum(t["net_pnl"] for t in all_trades if t["net_pnl"] > 0)
    gl = -sum(t["net_pnl"] for t in all_trades if t["net_pnl"] <= 0)
    n = len(all_trades)
    rs = [t["r"] for t in all_trades]
    agg = {"n": n, "pf": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0),
           "avg_r": sum(rs) / n if n else 0.0, "total_r": sum(rs),
           "win_rate": 100 * sum(1 for t in all_trades if t["net_pnl"] > 0) / n if n else 0.0,
           "net": sum(t["net_pnl"] for t in all_trades),
           "prob_profit": None, "prob": None}
    if n >= 20:
        rnd = random.Random(1)
        tot = [sum(rnd.choice(rs) for _ in range(n)) for _ in range(2000)]
        agg["prob_profit"] = sum(1 for x in tot if x > 0) / len(tot)
    agg["verdict"] = verdict({**agg, "avg_r": agg["avg_r"]})
    return rows, agg
