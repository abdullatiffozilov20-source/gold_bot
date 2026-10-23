"""Ma'lumot: CSV yuklash (MT5/Yahoo/oddiy formatlar), yfinance yuklab olish, demo generator."""
import csv
import math
import random
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

Candle = namedtuple("Candle", "time open high low close")

_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M",
    "%Y-%m-%d", "%Y.%m.%d", "%m/%d/%Y %H:%M", "%d.%m.%Y %H:%M",
)


def parse_time(s):
    """Vaqtni UTC deb hisoblangan naive datetime ga aylantiradi."""
    s = s.strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = None
        for f in _FORMATS:
            try:
                dt = datetime.strptime(s, f)
                break
            except ValueError:
                continue
        if dt is None:
            raise ValueError(f"Vaqt formati tanilmadi: {s!r}")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def load_candles(path):
    """CSV dan candle'larni o'qiydi. (candles, ogohlantirishlar) qaytaradi.

    Qo'llab-quvvatlanadi: ajratgich , ; yoki TAB; sarlavhalar <DATE>/<TIME> (MT5),
    time/datetime/timestamp, open/high/low/close (katta-kichik harf farqsiz).
    """
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("Fayl bo'sh yoki faqat sarlavha bor.")
    delim = max((",", "\t", ";"), key=lines[0].count)
    reader = csv.reader(lines, delimiter=delim)
    header = [h.strip().strip("<>").lower() for h in next(reader)]

    def col(*names):
        for nm in names:
            if nm in header:
                return header.index(nm)
        return None

    i_o, i_h, i_l, i_c = col("open"), col("high"), col("low"), col("close")
    if None in (i_o, i_h, i_l, i_c):
        raise ValueError("CSV da open, high, low, close ustunlari bo'lishi kerak. "
                         f"Topilgan sarlavha: {header}")
    i_date, i_time = col("date"), col("time")
    i_dt = col("datetime", "timestamp", "gmt time", "time", "date")
    combine = i_date is not None and i_time is not None
    if not combine and i_dt is None:
        raise ValueError("Vaqt ustuni (time/datetime/date) topilmadi.")

    candles, bad = [], 0
    for row in reader:
        try:
            ts = (row[i_date] + " " + row[i_time]) if combine else row[i_dt]
            c = Candle(parse_time(ts), float(row[i_o]), float(row[i_h]),
                       float(row[i_l]), float(row[i_c]))
            if (c.low > c.high or c.low > min(c.open, c.close) + 1e-9
                    or c.high < max(c.open, c.close) - 1e-9 or min(c[1:]) <= 0):
                raise ValueError("OHLC mantiqsiz")
            candles.append(c)
        except (ValueError, IndexError):
            bad += 1
    warns = []
    if bad:
        warns.append(f"{bad} ta noto'g'ri qator tashlab yuborildi.")
        if bad > 0.05 * (len(candles) + bad):
            raise ValueError("Qatorlarning 5% dan ko'pi noto'g'ri — fayl formatini tekshiring.")
    candles.sort(key=lambda c: c.time)
    uniq = []
    for c in candles:
        if uniq and uniq[-1].time == c.time:
            continue
        uniq.append(c)
    if len(uniq) != len(candles):
        warns.append(f"{len(candles) - len(uniq)} ta takroriy vaqt olib tashlandi.")
    return uniq, warns


def save_candles(path, candles):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close"])
        for c in candles:
            w.writerow([c.time.isoformat(), f"{c.open:.2f}", f"{c.high:.2f}",
                        f"{c.low:.2f}", f"{c.close:.2f}"])


def drop_forming(candles, now=None):
    """Hali yopilmagan (shakllanayotgan) oxirgi candle'ni olib tashlaydi.
    Signal faqat YOPILGAN candle'ga tayanishi kerak (backtest ham shunday)."""
    if len(candles) < 3:
        return candles, False
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    deltas = sorted((b.time - a.time).total_seconds() for a, b in zip(candles[-50:], candles[-49:]))
    bar = timedelta(seconds=deltas[len(deltas) // 2])
    if candles[-1].time + bar > now:
        return candles[:-1], True
    return candles, False


def fetch_yfinance(symbol="GC=F", interval="1h", days=700):
    """Yahoo Finance dan yuklaydi (pip install yfinance kerak, internet kerak).
    1h uchun Yahoo ~730 kun bilan cheklaydi. GC=F — oltin fyucherslari (spot XAUUSD dan
    biroz farq qiladi); aniqroq natija uchun MT5 dan eksport qiling."""
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("yfinance o'rnatilmagan:  pip install yfinance")
    df = yf.Ticker(symbol).history(period=f"{days}d", interval=interval, auto_adjust=False)
    if df is None or df.empty:
        raise SystemExit("Yahoo ma'lumot qaytarmadi (internet yoki simvolni tekshiring).")
    out = []
    for ts, r in df.iterrows():
        t = ts.to_pydatetime()
        if t.tzinfo is not None:
            t = t.astimezone(timezone.utc).replace(tzinfo=None)
        if any(math.isnan(x) for x in (r["Open"], r["High"], r["Low"], r["Close"])):
            continue
        out.append(Candle(t, float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])))
    out, _ = drop_forming(out)          # shakllanayotgan oxirgi soatni saqlamaymiz
    return out


def make_demo(bars=8000, seed=7, start=datetime(2024, 1, 1), price=2350.0, trend_strength=1.0):
    """SUN'IY soatlik XAU/USD o'xshash ma'lumot: trend/range rejimlari, volatillik
    klasterlari, sessiya effekti, dam olish kunlarisiz. Faqat kodni sinash uchun —
    bunda strategiyaning real foydasi haqida xulosa chiqarib bo'lmaydi."""
    rnd = random.Random(seed)
    base = 1.6                      # soatlik standart og'ish ($)
    var = base * base
    prev_ret = 0.0
    t = start
    out = []
    regime, left, drift, anchor = "range", 0, 0.0, price
    while len(out) < bars:
        if t.weekday() >= 5:
            t += timedelta(hours=1)
            continue
        if left <= 0:
            regime = rnd.choice(("up", "down", "range", "range"))
            left = rnd.randint(80, 400)
            drift = {"up": 0.12, "down": -0.12, "range": 0.0}[regime] * base * trend_strength
            anchor = price
        left -= 1
        var = 0.1 * base * base + 0.15 * prev_ret ** 2 + 0.75 * var
        sess = 1.4 if 13 <= t.hour <= 16 else (0.6 if (t.hour >= 22 or t.hour <= 5) else 1.0)
        sigma = math.sqrt(var) * sess
        o = price
        pull = -0.04 * (price - anchor) if regime == "range" else 0.0
        steps, p_ = [], o
        for _ in range(4):
            p_ += (drift + pull) / 4 + rnd.gauss(0, sigma / 2)
            steps.append(p_)
        cl = steps[-1]
        hi = max(o, *steps) + abs(rnd.gauss(0, sigma * 0.15))
        lo = min(o, *steps) - abs(rnd.gauss(0, sigma * 0.15))
        out.append(Candle(t, round(o, 2), round(hi, 2), round(lo, 2), round(cl, 2)))
        prev_ret = cl - o
        price = cl
        t += timedelta(hours=1)
    return out
