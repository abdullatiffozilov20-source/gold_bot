"""Indikatorlar. Hammasi O(n): butun qator bir marta hisoblanadi.
Har funksiya kirish bilan bir xil uzunlikdagi ro'yxat qaytaradi; yetarli ma'lumot
bo'lmagan joyda None turadi."""


def sma(values, p):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= p:
            s -= values[i - p]
        if i >= p - 1:
            out[i] = s / p
    return out


def ema(values, p):
    out = [None] * len(values)
    if len(values) < p:
        return out
    k = 2.0 / (p + 1)
    prev = sum(values[:p]) / p
    out[p - 1] = prev
    for i in range(p, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def true_range(h, l, c):
    tr = [h[0] - l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def atr(h, l, c, p):
    """Wilder ATR."""
    n = len(c)
    out = [None] * n
    if n <= p:
        return out
    tr = true_range(h, l, c)
    prev = sum(tr[1:p + 1]) / p
    out[p] = prev
    for i in range(p + 1, n):
        prev = (prev * (p - 1) + tr[i]) / p
        out[i] = prev
    return out


def rsi(c, p):
    """Wilder RSI."""
    n = len(c)
    out = [None] * n
    if n <= p:
        return out
    gains = losses = 0.0
    for i in range(1, p + 1):
        d = c[i] - c[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / p, losses / p
    out[p] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    for i in range(p + 1, n):
        d = c[i] - c[i - 1]
        ag = (ag * (p - 1) + max(d, 0.0)) / p
        al = (al * (p - 1) + max(-d, 0.0)) / p
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    return out


def adx(h, l, c, p):
    """Wilder ADX, +DI, -DI. (adx, plus_di, minus_di) qaytaradi."""
    n = len(c)
    adx_v = [None] * n
    pdi = [None] * n
    mdi = [None] * n
    if n <= 2 * p:
        return adx_v, pdi, mdi
    tr = true_range(h, l, c)
    pdm = [0.0] * n
    mdm = [0.0] * n
    for i in range(1, n):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    s_tr = sum(tr[1:p + 1])
    s_p = sum(pdm[1:p + 1])
    s_m = sum(mdm[1:p + 1])
    dxs = []
    a = 0.0
    for i in range(p, n):
        if i > p:
            s_tr = s_tr - s_tr / p + tr[i]
            s_p = s_p - s_p / p + pdm[i]
            s_m = s_m - s_m / p + mdm[i]
        pd = 100.0 * s_p / s_tr if s_tr else 0.0
        md = 100.0 * s_m / s_tr if s_tr else 0.0
        pdi[i], mdi[i] = pd, md
        tot = pd + md
        dxs.append(100.0 * abs(pd - md) / tot if tot else 0.0)
        if len(dxs) == p:
            a = sum(dxs) / p
            adx_v[i] = a
        elif len(dxs) > p:
            a = (a * (p - 1) + dxs[-1]) / p
            adx_v[i] = a
    return adx_v, pdi, mdi
