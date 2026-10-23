# Gold Bot v2.1 — XAU/USD tahlil va signal

Faqat tahlil: brokerga ulanmaydi, buyurtma yubormaydi. Python 3.10+, qo'shimcha kutubxona shart emas
(faqat ma'lumot yuklash uchun `pip install yfinance`).

## Har kuni ishlatish (2 buyruq)
```bash
pip install yfinance                                   # bir marta
python -m goldbot signal data/gold_1h.csv --refresh    # yangi ma'lumot yuklab, signal beradi
```
`--refresh` Yahoo'dan so'nggi ~700 kunni yuklaydi, **yopilmagan oxirgi soatni tashlab yuboradi** va
oxirgi YOPILGAN candle bo'yicha BUY / SELL / WAIT beradi (entry, SL, TP, lot, sabablar).
Signalni soat boshida (masalan 5–10 daqiqadan keyin) so'rang — candle yopilgach.

Boshqa buyruqlar:
| Buyruq | Vazifa |
|---|---|
| `walkforward data/gold_1h.csv` | Halol out-of-sample test (parametr o'tmishda tanlanadi, ko'rilmagan davrda sinaladi) |
| `backtest data/gold_1h.csv --trades t.csv` | Butun davr backtest, savdolar CSV ga |
| `fetch --out data/gold_1h.csv` | Faqat ma'lumot yuklash |
| `demo-data` | SUN'IY ma'lumot (faqat kodni sinash uchun) |

Parametrlar: `--set risk_pct=0.5 --set stop_atr=2.5` (hammasi `goldbot/strategy.py` → `Params`).
Telegramga: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` o'rnatib, `signal ... --telegram` (jonli sinalmagan).
MT5 CSV (TAB, `<DATE> <TIME>`) ham o'qiladi; vaqt UTC deb olinadi.

## Strategiya (ball tizimi, max 8)
Majburiy: katta trend (narx va EMA50 EMA200 ning bir tomonida), kirish triggeri (EMA20/50 kesishuvi yoki
EMA20 ga pullback), yetarli volatillik, faol sessiya (UTC 7–20). Qo'shimcha ball: EMA tartibi, ADX≥20,
RSI zonasi, candle tasdig'i. Signal uchun ≥6 ball.
Chiqish: stop 3×ATR, target 4R, +1R da breakeven, 48 candle vaqt chegarasi.
Risk: har savdoda 1% balans, kunlik zarar limiti 3%, kuniga ≤3 savdo.

## Real XAU/USD 1H natijalari (2024-07 … 2026-10, Yahoo GC=F)
| | Natija |
|---|---|
| v1 standart (stop 1.5×ATR, target 2R) | PF 0.89, o'rtacha −0.07R → ustunlik yo'q |
| v2.1 walk-forward (out-of-sample, 4 bosqich) | 98 savdo, PF 1.69, o'rtacha +0.34R, yutuq 37% |
| Butun davr, tanlangan parametrlar (optimistik) | 172 savdo, PF 1.60; BUY PF 1.62, SELL PF 1.56 |
| Xarajat 4× oshirilsa (spread 1.2, slippage 0.3) | PF 1.42, o'rtacha +0.24R — foyda saqlanadi |

**Ogohlantirishlar (muhim):**
- Oxirgi walk-forward bosqichida (2026-05 … 2026-10) natija **salbiy** (PF 0.59, 19 savdo): so'nggi
  paytlarda ustunlik susaygan. `signal` so'nggi 90 kunlik natijani ko'rsatadi va zarar bo'lsa ogohlantiradi.
- Natija bitta bozor davri (kuchli oltin trendi) ga tayanadi. Boshqa rejimda ishlamasligi mumkin.
- Savdolarning ~63% yutqazadi (yutuq darajasi 37%): 4R target — kam yutuq, lekin katta foyda. Tarixda ketma-ket
  6 tagacha yutqazish seriyasi bo'lgan; maksimal drawdown ~6–8%.
- Variantlar bir xil ma'lumotda solishtirilgan, shuning uchun raqamlar biroz optimistik. Haqiqiy tekshiruv —
  **demo hisobda kamida 1–2 oy** kuzatish (u haqiqiy "ko'rilmagan" ma'lumot).
- Yangiliklar (NFP, FOMC, CPI) paytida bot signal bermasligi kerak — u yangilikni bilmaydi.
- Bu moliyaviy maslahat emas. Faqat yo'qotishga tayyor mablag' bilan savdo qiling.

## v1 → v2 tuzatishlar
Signal rejimi qo'shildi; risk % bo'yicha hajm + leverage chegarasi; gap-ga chidamli chiqish; spread/slippage
kirish va chiqishda; O(n) indikatorlar; trend/ADX/RSI/sessiya filtrlari; walk-forward; testlar
(`python -m unittest discover -s tests`); yopilmagan candle bo'yicha signal bermaslik.
