# gold_bot

Gold Bot — simulyatsiya prototipi

Bu o‘quv loyihasi XAU/USD uchun oddiy moving-average crossover strategiyasini
tarixiy OHLC CSV ma’lumotida simulyatsiya qiladi.

Xavfsizlik

• Brokerga ulanmaydi.
• MetaTrader 5 ga ulanmaydi.
• Buyurtma yuborish funksiyasi yo‘q.
• sample_gold.csv sun’iy (synthetic) ma’lumot; real bozor narxlari emas.
• Natijalar foyda kafolati emas va real savdo qarori uchun ishlatilmasligi kerak.

Fayllar

• main.py — strategiya va backtest simulyatori (Python standard library).
• data/sample_gold.csv — sinov uchun sun’iy OHLC ma’lumot.

Ishga tushirish

Python 3.10+ kerak. Qo‘shimcha kutubxona o‘rnatish shart emas.

Terminalda loyiha papkasiga kirib:

python main.py

O‘zingizdagi CSV faylni sinash:

python main.py data/my_gold_data.csv

CSV ustunlari:
time,open,high,low,close
Vaqt ISO formatida bo‘lsin, masalan 2026-01-01T09:00:00.

Strategiya qoidalari

• 20 SMA va 50 SMA crossover.
• Signal candle yopilganda aniqlanadi; kirish keyingi candle ochilishida simulyatsiya qilinadi.
• Stop: 1.5 × ATR(14); target: 2R.
• Har savdo uchun taxminiy risk limiti: $50.
• Kunlik zarar chegarasi: $150. Bu prototipda kunlik limit yopilgan savdolar bo‘yicha hisoblanadi.
• Agar bir candle ichida stop va target ikkalasi ham tegsa, konservativ ravishda stop birinchi deb olinadi.
• Spread/slippage xarajati namunaviy qiymat; brokerga xos emas.

Muhim cheklovlar

Bu juda sodda prototip. Pozitsiya hajmi uchun 1 unit = 1 ounce deb faraz qilinadi;
brokerning contract size, tick value, margin, spread va execution qoidalari farq qiladi.
Kunlik limit ham gap, sirpanish yoki uzluksiz narx o‘zgarishi sabab real bozorda kafolatlanmaydi.
Avval haqiqiy tarixiy ma’lumot, to‘g‘ri xarajatlar va mustaqil testlar bilan tekshirish kerak.
