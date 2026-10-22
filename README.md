# Gold Bot v2 — XAU/USD tahlil va signal

Faqat tahlil: brokerga ulanmaydi, buyurtma yubormaydi. Python 3.10+, qo'shimcha kutubxona shart emas
(faqat `fetch` buyrug'i uchun `pip install yfinance`).

## Tez boshlash
```bash
# 1) Real ma'lumot (tavsiya: MT5 dan eksport qilingan CSV, kamida 1-2 yillik soatlik)
python -m goldbot fetch --out data/gold_1h.csv          # yoki MT5 CSV ni data/ ga qo'ying

# 2) Strategiya haqiqatan ishlaydimi? (eng muhim qadam)
python -m goldbot walkforward data/gold_1h.csv

# 3) Hozirgi signal
python -m goldbot signal data/gold_1h.csv --balance 5000
```
Boshqa buyruqlar: `backtest` (butun davr, `--trades savdolar.csv`), `demo-data` (SUN'IY ma'lumot, faqat kodni sinash uchun).
Parametrlarni o'zgartirish: `--set adx_min=25 --set risk_pct=0.5` (hamma parametrlar `goldbot/strategy.py` → `Params`).
Telegramga yuborish: `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID` ni o'rnatib, `signal ... --telegram` (jonli sinalmagan).

## CSV formati
`time,open,high,low,close` (ISO vaqt) yoki MT5 eksporti (`<DATE> <TIME> <OPEN>...`, TAB). Vaqt UTC deb olinadi
(MT5 server vaqti UTC bo'lmasa sessiya filtri siljiydi — `--set use_session=0` bilan o'chiring).

## Strategiya (ball tizimi, max 8)
Majburiy: katta trend (narx va EMA50 EMA200 ning bir tomonida), kirish triggeri (EMA20/50 kesishuvi yoki
EMA20 ga pullback), yetarli volatillik, faol sessiya (UTC 7–20). Qo'shimcha ball: EMA tartibi, ADX,
RSI zonasi, candle tasdig'i. Signal uchun ≥6 ball. Stop 1.5×ATR, target 2R, +1R da breakeven, 48 candle
vaqt chegarasi, kunlik zarar limiti 3%, kuniga ≤3 savdo.

## v1 dagi kamchiliklar va tuzatishlar
| v1 | v2 |
|---|---|
| Faqat backtest, signal yo'q | `signal` buyrug'i: BUY/SELL/WAIT, entry, SL, TP, lot, sabablar |
| Sun'iy 360 candle, 5 savdo | Real ma'lumot yuklash, MT5 formati, statistik baho (bootstrap) |
| Risk limiti amalda ishlamasdi (hajm balansga cheklangan) | Risk % bo'yicha hajm + leverage chegarasi + lot qadami |
| Gap hisobga olinmagan | Gap bo'lsa chiqish ochilish narxida (yo'qotish kattaroq) |
| O(n²) sekin | Indikatorlar bir marta hisoblanadi (8000 candle < 1 s) |
| Faqat SMA crossover | Trend filtri, ADX, RSI, volatillik, sessiya, breakeven, vaqt chegarasi |
| Spread faqat qo'shib-ayirilgan | Kirish va chiqish narxi noqulay tomonga siljiydi + komissiya |
| In-sample natija | Walk-forward: parametr o'tmishda tanlanadi, ko'rilmagan davrda sinaladi |
| Test yo'q | `python -m unittest discover -s tests` (look-ahead yo'qligi, gap, risk, indikatorlar) |

## Muhim
- Hech bir strategiya foyda kafolatlamaydi. `walkforward` natijasi "USTUNLIK TOPILMADI" yoki
  "YETARLI EMAS" desa — strategiya bilan savdo qilmang.
- "UMIDLI" baho ham faqat o'tmish haqida; avval demo hisobda kamida bir necha hafta kuzating.
- Yangiliklar (NFP, FOMC, CPI) paytida signal bermaslik tavsiya etiladi — bot yangilikni bilmaydi.
- Signal ma'lumot fayli qanchalik yangi bo'lsa, shunchalik foydali (eskirgan bo'lsa ogohlantiradi).
