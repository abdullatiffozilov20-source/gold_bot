"""Buyruqlar:
  python -m goldbot demo-data  --out data/demo.csv
  python -m goldbot fetch      --out data/gold_1h.csv
  python -m goldbot backtest   data/gold_1h.csv
  python -m goldbot walkforward data/gold_1h.csv
  python -m goldbot signal     data/gold_1h.csv --balance 5000
"""
import argparse
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import __version__
from .backtest import run_backtest, summarize, walk_forward
from .data import drop_forming, fetch_yfinance, load_candles, make_demo, save_candles
from .strategy import Indicators, Params, evaluate, levels
from .backtest import position_size

DISCLAIMER = ("Eslatma: bu tahlil vositasi, moliyaviy maslahat emas. Hech bir strategiya foyda "
              "kafolatlamaydi. Avval demo hisobda sinang, faqat yo'qotishga tayyor mablag' bilan savdo qiling.")


def _load(path):
    candles, warns = load_candles(path)
    for w in warns:
        print("Ogohlantirish:", w)
    return candles


def _params(args):
    try:
        return Params.from_overrides(args.set)
    except ValueError as e:
        raise SystemExit(f"Xatolik: {e}")


def _tf(sec):
    sec = int(sec)
    if sec % 86400 == 0:
        return f"{sec // 86400}D"
    if sec % 3600 == 0:
        return f"{sec // 3600}H"
    return f"{sec // 60}M"


def _fmt_pf(x):
    return "∞" if x == float("inf") else f"{x:.2f}"


def print_summary(sm, title):
    print(f"\n=== {title} ===")
    print(f"Savdolar: {sm['n']} | Yutuq darajasi: {sm['win_rate']:.1f}% | Profit factor: {_fmt_pf(sm['pf'])}")
    print(f"Sof natija: ${sm['net']:.2f} ({sm['return_pct']:.2f}%) | Maks. drawdown: ${sm['max_dd']:.2f} ({sm['max_dd_pct']:.1f}%)")
    print(f"O'rtacha R: {sm['avg_r']:+.3f} | Jami R: {sm['total_r']:+.1f} | O'rtacha yutuq ${sm['avg_win']:.2f} / zarar ${sm['avg_loss']:.2f}")
    print(f"Eng uzun yutqazish seriyasi: {sm['max_losing_streak']} | O'rtacha ushlab turish: {sm['avg_bars']:.1f} candle")
    print(f"Solishtirish (buy&hold shu davrda): {sm['bh_pct']:+.2f}%")
    if sm["prob_profit"] is not None:
        print(f"Bootstrap: foyda ehtimoli {100 * sm['prob_profit']:.0f}% | 5-persentil jami R: {sm['p5_total_r']:+.1f}")
    print(f"BAHO: {sm['verdict']}")


def cmd_demo(a):
    c = make_demo(a.bars, a.seed, trend_strength=a.trend)
    save_candles(a.out, c)
    print(f"SUN'IY demo ma'lumot yozildi: {a.out} ({len(c)} candle). Real bozor emas!")


def cmd_fetch(a):
    c = fetch_yfinance(a.symbol, a.interval, a.days)
    save_candles(a.out, c)
    print(f"Yuklandi: {a.out} ({len(c)} candle, {c[0].time} → {c[-1].time})")


def cmd_backtest(a):
    p = _params(a)
    candles = _load(a.file)
    ind = Indicators(candles, p)
    res = run_backtest(candles, p, ind)
    sm = summarize(res, p)
    print(f"Data: {a.file} | {len(candles)} candle | TF {_tf(ind.bar_seconds)} | "
          f"{ind.t[res['start']]} → {ind.t[res['end'] - 1]}")
    print_summary(sm, "BACKTEST (butun davr, parametrlar o'zgartirilmagan)")
    if a.trades:
        import csv
        with open(a.trades, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            cols = ["entry_time", "exit_time", "side", "entry", "exit", "lots", "risk_usd", "net_pnl", "r", "bars", "reason"]
            w.writerow(cols)
            for t in res["trades"]:
                w.writerow([round(t[k], 4) if isinstance(t[k], float) else t[k] for k in cols])
        print(f"Savdolar ro'yxati: {a.trades}")
    print("\nOxirgi 8 savdo:")
    for t in res["trades"][-8:]:
        print(f"{t['side']:4} {t['entry_time']} → {t['exit_time']} | {t['entry']:.2f}→{t['exit']:.2f} | "
              f"{t['lots']:.2f} lot | ${t['net_pnl']:+.2f} ({t['r']:+.2f}R) | {t['reason']}")
    print("\n" + DISCLAIMER)


def cmd_wf(a):
    p = _params(a)
    candles = _load(a.file)
    print("Walk-forward ishlayapti (bir necha soniya)...")
    try:
        rows, agg = walk_forward(candles, p, folds=a.folds)
    except ValueError as e:
        raise SystemExit(f"Xatolik: {e}")
    print("\nBosqichlar (parametrlar o'tmishda tanlangan, natija KO'RILMAGAN davrda):")
    for r in rows:
        t = r["test"]
        print(f"  #{r['fold']} {r['from']:%Y-%m-%d} → {r['to']:%Y-%m-%d} | tanlangan: {r['cfg']} | "
              f"savdo {t['n']}, PF {_fmt_pf(t['pf'])}, avg R {t['avg_r']:+.2f}, ${t['net']:+.0f}")
    print(f"\n=== OUT-OF-SAMPLE JAMI ===")
    print(f"Savdolar: {agg['n']} | Yutuq: {agg['win_rate']:.1f}% | PF: {_fmt_pf(agg['pf'])} | "
          f"O'rtacha R: {agg['avg_r']:+.3f} | Jami R: {agg['total_r']:+.1f} | Net ${agg['net']:.2f}")
    if agg["prob_profit"] is not None:
        print(f"Bootstrap foyda ehtimoli: {100 * agg['prob_profit']:.0f}%")
    print(f"BAHO: {agg['verdict']}")
    print("\nBu raqam backtest'dan past bo'lishi NORMAL — u haqiqatga yaqinroq.\n" + DISCLAIMER)


def _stat_line(trades):
    n = len(trades)
    if not n:
        return "savdo yo'q"
    gp = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gl = -sum(t["net_pnl"] for t in trades if t["net_pnl"] <= 0)
    pf = gp / gl if gl else float("inf")
    return f"{n} savdo, PF {_fmt_pf(pf)}, o'rtacha {sum(t['r'] for t in trades) / n:+.2f}R"


def build_signal_text(candles, p, balance, quick_stats=True):
    ind = Indicators(candles, p)
    i = ind.n - 1
    sig = evaluate(ind, i, p)
    last = ind.t[i]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    age_h = (now - last).total_seconds() / 3600
    out = [f"=== XAU/USD SIGNAL (Gold Bot v{__version__}) ===",
           f"Oxirgi yopilgan candle: {last} UTC | TF {_tf(ind.bar_seconds)} | Narx: {sig.price:.2f}"]
    if age_h > 72:
        out.append(f"⚠ Ma'lumot eskirgan ({age_h / 24:.1f} kun oldingi). Bu signal HOZIRGI bozorga mos emas — yangi ma'lumot kiriting.")
    elif age_h > 2 * ind.bar_seconds / 3600 + 1 and now.weekday() < 5:
        out.append(f"⚠ Oxirgi candle {age_h:.1f} soat oldingi — ma'lumot yangilanganini tekshiring.")
    out.append("")
    if sig.action in ("BUY", "SELL"):
        entry = sig.price                                  # keyingi candle ochilishi ≈ oxirgi close
        stop, target, sd = levels(sig.side, entry, sig.atr, p)
        lots, oz = position_size(balance, sd, entry, p)
        out.append(f"SIGNAL: {sig.action}   (ball {sig.score}/{sig.max_score})")
        out.append(f"Kirish: ≈{entry:.2f} (keyingi candle ochilishida)")
        out.append(f"Stop-loss: {stop:.2f}  (masofa {sd:.2f} = {p.stop_atr}×ATR)")
        out.append(f"Take-profit: {target:.2f}  ({p.target_r}R)")
        if p.breakeven_r > 0:
            be = entry + sig.side * p.breakeven_r * sd
            out.append(f"Breakeven: narx {be:.2f} ga yetsa stopni kirish narxiga ko'chiring")
        out.append(f"Vaqt chegarasi: {p.max_bars} candle ichida natija bo'lmasa — yoping")
        if lots > 0:
            out.append(f"Hajm: {lots:.2f} lot (risk ≈ ${oz * sd:.2f} = {p.risk_pct}% balans ${balance:.0f})")
        else:
            out.append(f"Hajm: balans ${balance:.0f} bilan {p.risk_pct}% risk uchun minimal lot sig'maydi — KIRMANG yoki riskni oshirmasdan balansni tekshiring.")
        out.append("\nSabablar:")
        out += [f"  • {r}" for r in sig.reasons]
    else:
        out.append("SIGNAL: WAIT (kutish)")
        out.append(f"Trend: {sig.bias or '—'}")
        out.append("Nima uchun kirilmaydi:")
        out += [f"  • {b}" for b in sig.blockers]
        if sig.reasons:
            out.append("Hozirgi holat:")
            out += [f"  • {r}" for r in sig.reasons]
    if quick_stats and len(candles) > ind.warmup + 500:
        res = run_backtest(candles, p, ind)
        sm = summarize(res, p, boot=0)
        out.append(f"\nTarix (parametrlar shu davrda tanlangan, shuning uchun biroz optimistik; "
                   f"halol baho uchun `walkforward`): {sm['n']} savdo, yutuq {sm['win_rate']:.0f}%, "
                   f"PF {_fmt_pf(sm['pf'])}, o'rtacha {sm['avg_r']:+.2f}R")
        if sig.action in ("BUY", "SELL"):
            side = [t for t in res["trades"] if t["side"] == sig.action]
            if side:
                out.append(f"  {sig.action} tomon tarixi: {_stat_line(side)}")
        # So'nggi 90 kun: strategiya hozirgi bozorda ishlayaptimi?
        cutoff = last - timedelta(days=90)
        recent = [t for t in res["trades"] if t["entry_time"] >= cutoff]
        out.append(f"  So'nggi 90 kun: {_stat_line(recent)}")
        if len(recent) < 8:
            out.append("  ⚠ So'nggi davrda savdo kam — joriy holat haqida xulosa chiqarish qiyin.")
        elif sum(t["r"] for t in recent) <= 0:
            out.append("  ⚠ So'nggi 90 kunda strategiya zarar qildi — bozor rejimi o'zgargan bo'lishi mumkin. "
                       "Signalga ehtiyotkor munosabatda bo'ling (kichik risk yoki demo).")
        out.append(f"Ishonch (butun tarix): {sm['verdict']}")
    out.append("\n" + DISCLAIMER)
    return "\n".join(out)


def send_telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise SystemExit("TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID muhit o'zgaruvchilarini o'rnating.")
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20) as r:
        if r.status != 200:
            raise SystemExit(f"Telegram xatosi: {r.status}")
    print("Telegramga yuborildi.")


def cmd_signal(a):
    p = _params(a)
    if a.refresh:
        fresh = fetch_yfinance("GC=F", "1h", 700)
        save_candles(a.file, fresh)
        print(f"Ma'lumot yangilandi: {a.file} ({len(fresh)} candle, oxirgi {fresh[-1].time} UTC)")
    candles = _load(a.file)
    candles, dropped = drop_forming(candles)
    if dropped:
        print("Eslatma: oxirgi candle hali yopilmagan edi — signal oxirgi YOPILGAN candle bo'yicha.")
    ind = Indicators(candles, p)
    if len(candles) < ind.warmup + 5:
        raise SystemExit(f"Xatolik: kamida {ind.warmup + 5} ta candle kerak (EMA{p.trend} uchun).")
    text = build_signal_text(candles, p, a.balance, quick_stats=not a.fast)
    print(text)
    if a.telegram:
        send_telegram(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="goldbot", description="XAU/USD tahlil va signal (buyurtma yubormaydi)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--set", action="append", metavar="KEY=VAL",
                        help="parametrni o'zgartirish, masalan --set adx_min=25 --set risk_pct=0.5")

    s = sub.add_parser("demo-data", help="SUN'IY demo ma'lumot yaratish (faqat kodni sinash uchun)")
    s.add_argument("--out", default="data/demo.csv"); s.add_argument("--bars", type=int, default=8000)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--trend", type=float, default=1.0, help="trend kuchi (1=zaif, 4=kuchli)"); s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("fetch", help="Yahoo Finance dan real ma'lumot (yfinance kerak)")
    s.add_argument("--symbol", default="GC=F"); s.add_argument("--interval", default="1h")
    s.add_argument("--days", type=int, default=700); s.add_argument("--out", default="data/gold_1h.csv")
    s.set_defaults(fn=cmd_fetch)

    s = sub.add_parser("backtest", help="Strategiyani tarixiy ma'lumotda sinash")
    s.add_argument("file"); s.add_argument("--trades", help="savdolarni CSV ga yozish"); common(s)
    s.set_defaults(fn=cmd_backtest)

    s = sub.add_parser("walkforward", help="Halol out-of-sample test (tavsiya etiladi)")
    s.add_argument("file"); s.add_argument("--folds", type=int, default=4); common(s)
    s.set_defaults(fn=cmd_wf)

    s = sub.add_parser("signal", help="Oxirgi candle bo'yicha BUY/SELL/WAIT")
    s.add_argument("file"); s.add_argument("--balance", type=float, default=5000.0)
    s.add_argument("--telegram", action="store_true"); s.add_argument("--fast", action="store_true", help="tarixiy statistikasiz")
    s.add_argument("--refresh", action="store_true", help="avval Yahoo'dan yangi ma'lumot yuklab, keyin signal")
    common(s); s.set_defaults(fn=cmd_signal)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (OSError, ValueError) as e:
        print(f"Xatolik: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
