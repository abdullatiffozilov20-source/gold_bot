"""Strategiya: trend bo'yicha ball tizimi (trend + EMA trigger + ADX + RSI + sessiya + volatillik).
Signal faqat YOPILGAN candle ma'lumotiga tayanadi (look-ahead yo'q)."""
from dataclasses import dataclass, field, fields
from statistics import median

from . import indicators as ta

MAX_SCORE = 8


@dataclass
class Params:
    # indikatorlar
    fast: int = 20
    slow: int = 50
    trend: int = 200
    atr_p: int = 14
    adx_p: int = 14
    rsi_p: int = 14
    # filtrlar
    adx_min: float = 20.0
    min_atr_pct: float = 0.0003      # ATR/narx shundan past bo'lsa — bozor "o'lik", kirmaydi
    cross_lookback: int = 3          # EMA kesishuvi oxirgi nechta candle ichida hisoblanadi
    use_session: bool = True         # faqat London+NY (kichik taymfreymlarda)
    session_start: int = 7           # UTC soat (kiritilgan)
    session_end: int = 20            # UTC soat (kiritilmagan)
    min_score: int = 6               # signal uchun minimal ball (max 8)
    # chiqish
    # Real XAU/USD 1H (2024-07..2026-10) walk-forward bo'yicha tanlangan: keng stop (3×ATR)
    # shovqinga yeb qo'yilmaydi; uzoq target (4R) trendni ushlaydi.
    stop_atr: float = 3.0
    target_r: float = 4.0
    breakeven_r: float = 1.0         # +1R da stopni kirish narxiga ko'chirish (0 = o'chiq)
    max_bars: int = 48               # vaqt bo'yicha chiqish (candle soni)
    # risk va hajm
    start_balance: float = 5000.0
    risk_pct: float = 1.0            # har savdoda balansning %
    max_leverage: float = 10.0       # pozitsiya qiymati / balans chegarasi
    contract_size: float = 100.0     # 1 lot = 100 oz (XAUUSD ko'p brokerlarda)
    lot_step: float = 0.01
    # xarajatlar (narx birligida, $/oz)
    spread: float = 0.30
    slippage: float = 0.05
    commission_per_lot: float = 0.0  # har tomon uchun, $/lot
    # kunlik himoya
    daily_loss_pct: float = 3.0
    max_daily_trades: int = 3

    @classmethod
    def from_overrides(cls, pairs):
        """['adx_min=25', 'stop_atr=2'] ko'rinishidagi ro'yxatdan Params yasaydi."""
        p = cls()
        types = {f.name: f.type for f in fields(cls)}
        for item in pairs or []:
            k, _, v = item.partition("=")
            k = k.strip()
            if k not in types:
                raise ValueError(f"Noma'lum parametr: {k}")
            t = types[k]
            if t in (bool, "bool"):
                setattr(p, k, v.strip().lower() in ("1", "true", "yes", "ha"))
            elif t in (int, "int"):
                setattr(p, k, int(float(v)))
            else:
                setattr(p, k, float(v))
        return p


class Indicators:
    """Butun qator uchun indikatorlarni bir marta hisoblaydi."""

    def __init__(self, candles, p):
        self.t = [c.time for c in candles]
        self.o = [c.open for c in candles]
        self.h = [c.high for c in candles]
        self.l = [c.low for c in candles]
        self.c = [c.close for c in candles]
        self.n = len(candles)
        deltas = [(self.t[i + 1] - self.t[i]).total_seconds() for i in range(self.n - 1)]
        self.bar_seconds = median(deltas) if deltas else 3600
        self.session_on = p.use_session and self.bar_seconds < 4 * 3600
        self.ema_f = ta.ema(self.c, p.fast)
        self.ema_s = ta.ema(self.c, p.slow)
        self.ema_t = ta.ema(self.c, p.trend)
        self.atr = ta.atr(self.h, self.l, self.c, p.atr_p)
        self.adx, self.pdi, self.mdi = ta.adx(self.h, self.l, self.c, p.adx_p)
        self.rsi = ta.rsi(self.c, p.rsi_p)
        self.warmup = max(p.trend, p.slow, 2 * p.adx_p + 2, p.atr_p + 1, p.rsi_p + 1) + 1


@dataclass
class Signal:
    action: str = "WAIT"             # BUY | SELL | WAIT
    score: int = 0
    max_score: int = MAX_SCORE
    time: object = None
    price: float = 0.0
    atr: float = 0.0
    bias: str = ""
    reasons: list = field(default_factory=list)
    blockers: list = field(default_factory=list)

    @property
    def side(self):
        return {"BUY": 1, "SELL": -1}.get(self.action, 0)


def levels(side, entry, atr_value, p):
    """Stop va target narxlari."""
    dist = p.stop_atr * atr_value
    return entry - side * dist, entry + side * p.target_r * dist, dist


def evaluate(ind, i, p):
    """i-chi (yopilgan) candle bo'yicha signal."""
    price = ind.c[i]
    s = Signal(time=ind.t[i], price=price)
    vals = (ind.ema_f[i], ind.ema_s[i], ind.ema_t[i], ind.atr[i],
            ind.adx[i], ind.rsi[i], ind.pdi[i], ind.mdi[i])
    if i < 1 or any(v is None for v in vals):
        s.blockers.append("Indikatorlar uchun ma'lumot yetarli emas")
        return s
    f, sl, tr, a, adx_v, rsi_v, pdi, mdi = vals
    s.atr = a

    # 1) Katta trend yo'nalishi (majburiy)
    if price > tr and sl > tr:
        d, s.bias = 1, "BUY tomon (narx va EMA%d EMA%d dan yuqorida)" % (p.slow, p.trend)
    elif price < tr and sl < tr:
        d, s.bias = -1, "SELL tomon (narx va EMA%d EMA%d dan pastda)" % (p.slow, p.trend)
    else:
        s.bias = "Aniq trend yo'q"
        s.blockers.append("Katta trend aniq emas (narx/EMA%d/EMA%d mos emas) — savdo qilinmaydi"
                          % (p.slow, p.trend))
        return s

    # 2) Majburiy filtrlar
    if a / price < p.min_atr_pct:
        s.blockers.append("Volatillik juda past (ATR/narx %.4f%% < %.4f%%)"
                          % (100 * a / price, 100 * p.min_atr_pct))
    if ind.session_on and not (p.session_start <= ind.t[i].hour < p.session_end):
        s.blockers.append("Faol sessiyadan tashqarida (UTC %02d:00-%02d:00)"
                          % (p.session_start, p.session_end))

    # 3) Trigger: yaqinda EMA kesishuvi YOKI EMA(fast) ga pullback-bounce (majburiy)
    cross = False
    for k in range(p.cross_lookback):
        j = i - k
        if j < 1:
            break
        a0, a1, b0, b1 = ind.ema_f[j - 1], ind.ema_f[j], ind.ema_s[j - 1], ind.ema_s[j]
        if None in (a0, a1, b0, b1):
            break
        if (d == 1 and a0 <= b0 and a1 > b1) or (d == -1 and a0 >= b0 and a1 < b1):
            cross = True
            break
    if d == 1:
        pull = f > sl and ind.l[i] <= f < price and price > ind.o[i]
    else:
        pull = f < sl and ind.h[i] >= f > price and price < ind.o[i]
    if not (cross or pull):
        s.blockers.append("Kirish triggeri yo'q: EMA%d/%d kesishuvi yoki EMA%d ga pullback kutilmoqda"
                          % (p.fast, p.slow, p.fast))
    if s.blockers:
        return s

    # 4) Ball
    score = 2
    s.reasons.append("Katta trend mos: %s (+2)" % s.bias)
    if (f - sl) * d > 0:
        score += 1
        s.reasons.append("EMA%d, EMA%d ning trend tomonida (+1)" % (p.fast, p.slow))
    if cross:
        score += 2
        s.reasons.append("EMA%d/%d kesishuvi oxirgi %d candle ichida (+2)" % (p.fast, p.slow, p.cross_lookback))
    else:
        score += 2
        s.reasons.append("Narx EMA%d ga qaytib, trend tomonga bounce berdi (+2)" % p.fast)
    if adx_v >= p.adx_min and ((pdi > mdi) if d == 1 else (mdi > pdi)):
        score += 1
        s.reasons.append("ADX %.1f ≥ %.0f va DI yo'nalishi mos — trend kuchli (+1)" % (adx_v, p.adx_min))
    else:
        s.reasons.append("ADX %.1f — trend kuchi yetarli emas (0)" % adx_v)
    if (d == 1 and 45 <= rsi_v <= 68) or (d == -1 and 32 <= rsi_v <= 55):
        score += 1
        s.reasons.append("RSI %.1f — sog'lom zona, haddan oshmagan (+1)" % rsi_v)
    else:
        s.reasons.append("RSI %.1f — haddan oshgan yoki zaif zona (0)" % rsi_v)
    if (price > ind.o[i]) == (d == 1):
        score += 1
        s.reasons.append("Oxirgi candle yo'nalishni tasdiqlaydi (+1)")
    s.score = score
    if score >= p.min_score:
        s.action = "BUY" if d == 1 else "SELL"
    else:
        s.blockers.append("Ball past: %d/%d (kerak ≥ %d)" % (score, MAX_SCORE, p.min_score))
    return s
