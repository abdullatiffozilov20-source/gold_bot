"""
Gold Bot — educational XAU/USD backtest simulator.
SAFETY: This program uses CSV data only. It does not connect to MetaTrader,
a broker, or any account, and it cannot place orders.
"""
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "sample_gold.csv"

STARTING_BALANCE = 5000.0
MAX_RISK_PER_TRADE = 50.0
DAILY_LOSS_LIMIT = 150.0

FAST_MA = 20
SLOW_MA = 50
ATR_PERIOD = 14
STOP_ATR_MULTIPLE = 1.5
TARGET_R_MULTIPLE = 2.0

# Illustrative costs per simulated ounce, charged on entry and exit.
# Real broker contract sizes, spread, slippage, and fees vary.
SPREAD_PER_OUNCE = 0.30
SLIPPAGE_PER_OUNCE = 0.05

@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float

@dataclass
class Position:
    side: int              # +1 long, -1 short
    entry: float
    stop: float
    target: float
    units: float
    entry_time: datetime
    risk_dollars: float

def load_candles(path):
    candles = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"time", "open", "high", "low", "close"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV ustunlari time, open, high, low, close bo‘lishi kerak.")
        for row in reader:
            c = Candle(
                datetime.fromisoformat(row["time"]),
                float(row["open"]), float(row["high"]),
                float(row["low"]), float(row["close"])
            )
            if c.low > min(c.open, c.close) or c.high < max(c.open, c.close) or c.low > c.high:
                raise ValueError(f"Noto‘g‘ri OHLC ma’lumot: {row}")
            candles.append(c)
    candles.sort(key=lambda c: c.time)
    if len(candles) < SLOW_MA + ATR_PERIOD + 5:
        raise ValueError("Ma’lumot kam. Kamida 60 ta candle kerak.")
    return candles

def sma(values, period, end_index):
    if end_index + 1 < period:
        return None
    window = values[end_index - period + 1:end_index + 1]
    return sum(window) / period

def calculate_atr(candles, index, period=ATR_PERIOD):
    if index < period:
        return None
    trs = []
    for i in range(index - period + 1, index + 1):
        prev_close = candles[i - 1].close
        c = candles[i]
        trs.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    return sum(trs) / len(trs)

def crossover_signal(candles, i):
    closes = [c.close for c in candles]
    fast_now = sma(closes, FAST_MA, i)
    slow_now = sma(closes, SLOW_MA, i)
    fast_prev = sma(closes, FAST_MA, i - 1)
    slow_prev = sma(closes, SLOW_MA, i - 1)
    if None in (fast_now, slow_now, fast_prev, slow_prev):
        return 0
    if fast_prev <= slow_prev and fast_now > slow_now:
        return 1
    if fast_prev >= slow_prev and fast_now < slow_now:
        return -1
    return 0

def close_position(position, exit_price, exit_time, balance, reason):
    gross = (exit_price - position.entry) * position.units * position.side
    costs = (SPREAD_PER_OUNCE + SLIPPAGE_PER_OUNCE) * position.units * 2
    net = gross - costs
    return balance + net, {
        "entry_time": position.entry_time.isoformat(sep=" "),
        "exit_time": exit_time.isoformat(sep=" "),
        "side": "BUY" if position.side == 1 else "SELL",
        "entry": position.entry,
        "exit": exit_price,
        "units_oz_illustrative": position.units,
        "planned_risk_usd": position.risk_dollars,
        "net_pnl": net,
        "reason": reason,
    }

def run_backtest(candles):
    balance = STARTING_BALANCE
    peak_balance = balance
    max_drawdown = 0.0
    position = None
    trades = []
    daily_pnl = {}
    paused_days = set()

    # Signal is evaluated at candle close; entry, if any, is at next candle open.
    for i in range(SLOW_MA + ATR_PERIOD, len(candles) - 1):
        c = candles[i]
        next_c = candles[i + 1]
        day = c.time.date().isoformat()

        # Conservative intrabar simulation: if stop and target both touch,
        # assume stop happened first. No look-ahead entries.
        if position:
            exit_price, reason = None, None
            if position.side == 1:
                stop_hit = c.low <= position.stop
                target_hit = c.high >= position.target
            else:
                stop_hit = c.high >= position.stop
                target_hit = c.low <= position.target
            if stop_hit:
                exit_price, reason = position.stop, "stop"
            elif target_hit:
                exit_price, reason = position.target, "target"
            if exit_price is not None:
                balance, trade = close_position(position, exit_price, c.time, balance, reason)
                trades.append(trade)
                daily_pnl[day] = daily_pnl.get(day, 0.0) + trade["net_pnl"]
                position = None
                peak_balance = max(peak_balance, balance)
                max_drawdown = max(max_drawdown, peak_balance - balance)
                if daily_pnl[day] <= -DAILY_LOSS_LIMIT:
                    paused_days.add(day)

        if position is None and day not in paused_days:
            signal = crossover_signal(candles, i)
            atr = calculate_atr(candles, i)
            if signal and atr and atr > 0:
                entry = next_c.open
                stop_distance = STOP_ATR_MULTIPLE * atr
                # Approximate one unit as one ounce; broker contract sizing varies.
                units = min(MAX_RISK_PER_TRADE / stop_distance,
                            max(0.0, balance) / max(entry, 1.0))
                if units > 0:
                    if signal == 1:
                        stop = entry - stop_distance
                        target = entry + TARGET_R_MULTIPLE * stop_distance
                    else:
                        stop = entry + stop_distance
                        target = entry - TARGET_R_MULTIPLE * stop_distance
                    position = Position(signal, entry, stop, target, units,
                                        next_c.time, min(MAX_RISK_PER_TRADE, units * stop_distance))

    # Close any remaining position at final close for an honest end-of-data mark.
    if position:
        last = candles[-1]
        balance, trade = close_position(position, last.close, last.time, balance, "end_of_data")
        trades.append(trade)
        day = last.time.date().isoformat()
        daily_pnl[day] = daily_pnl.get(day, 0.0) + trade["net_pnl"]

    wins = sum(1 for t in trades if t["net_pnl"] > 0)
    net = balance - STARTING_BALANCE
    return {
        "starting_balance": STARTING_BALANCE,
        "ending_balance": balance,
        "net_pnl": net,
        "return_pct": (net / STARTING_BALANCE) * 100,
        "trades": trades,
        "win_rate_pct": (wins / len(trades) * 100) if trades else 0.0,
        "max_drawdown_dollars": max_drawdown,
        "daily_pnl": daily_pnl,
        "paused_days": sorted(paused_days),
    }

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_FILE
    try:
        candles = load_candles(path)
        result = run_backtest(candles)
    except (OSError, ValueError) as exc:
        print(f"Xatolik: {exc}")
        raise SystemExit(1)

    print("\n=== GOLD BOT: SIMULATION ONLY ===")
    print("Brokerga ulanmaydi va buyurtma yubormaydi.")
    print(f"Data: {path.name} | Candle: {len(candles)}")
    print(f"Boshlang‘ich balans: ${result['starting_balance']:.2f}")
    print(f"Yakuniy simulyatsiya balansi: ${result['ending_balance']:.2f}")
    print(f"Net natija: ${result['net_pnl']:.2f} ({result['return_pct']:.2f}%)")
    print(f"Savdolar: {len(result['trades'])} | Yutuqli savdolar: {result['win_rate_pct']:.1f}%")
    print(f"Taxminiy maksimal drawdown: ${result['max_drawdown_dollars']:.2f}")
    print(f"Kunlik limit sabab to‘xtatilgan kunlar: {len(result['paused_days'])}")
    print("\nEslatma: sample_gold.csv sun’iy demo ma’lumotidir. Bu natijalar haqiqiy bozorni ifodalamaydi.")
    if result["trades"]:
        print("\nOxirgi 10 ta simulyatsiya:")
        for t in result["trades"][-10:]:
            print(f"{t['side']:4} {t['entry_time']} -> {t['exit_time']} | "
                  f"entry {t['entry']:.2f} exit {t['exit']:.2f} | "
                  f"net ${t['net_pnl']:.2f} | {t['reason']}")
    else:
        print("Bu ma’lumotda strategiya signal chiqarmadi.")

if __name__ == "__main__":
    main()
