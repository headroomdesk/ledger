#!/usr/bin/env python3
"""
ledger_har_estimate_v1_2026-10-02.py — the Public Research Ledger's V-HAR constants (ledger page v1.0 §4, R2 §4 L3):
the log-HAR coefficients estimated ONCE on the development window's 1-minute data and frozen by hash. Standard library
only. Runs on the box (the 1-minute development partitions live there).

Governs against: PAFM_PublicResearchLedger_PreRegistration_v1_0_2026-10-02.md (405cbf2c...ccf4) §4 (V-HAR; L3: "estimated
once on the development window and frozen by hash; the script and window filed; never the sealed year") and §4's notation
(RV = sum of the 240 squared 1-minute log returns of a 4H bar, the first return taken from the first minute's open).

READS ONLY <layer0-dir>/1m/dev/YYYY-MM.csv.gz, each verified against layer0_summary.json's recorded hash; refuses any path
with a component named 'sealed'. The window is the development window 2019-12-31 00:00 -> 2025-07-31 20:00 (12,240 4H bars).
THE MODEL (declared before the fit): for 4H bar t,
    y_t  = ln RV_t
    x1_t = ln RV_{t-1}                              (the last 4H)
    x2_t = ln( mean of RV_{t-1} .. RV_{t-6} )       (the last day, 6 bars)
    x3_t = ln( mean of RV_{t-1} .. RV_{t-42} )      (the last week, 42 bars)
    y_t = b0 + b1 x1 + b2 x2 + b3 x3 + e_t,   OLS over every t with all 42 lags inside the window and RV > 0 throughout.
THE FORECAST MAP (declared, used by the ledger's forecast job): sigma2_f = exp(b0 + b1 x1 + b2 x2 + b3 x3 + s2 / 2), s2 the
OLS residual variance (the lognormal mean correction). A bar with RV = 0 (a whole frozen bar) never occurs in the
development window; the live job records such a bar's x as missing and writes NO_FORECAST for V-HAR only.
OUTPUT (write-once): the constants JSON — the four coefficients and s2 as decimal strings (17 significant digits), their
standard errors, R^2, n, the window, every partition hash read, the script hash, the host.
Usage:  python3 ledger_har_estimate_v1_2026-10-02.py --layer0-dir DIR --out ledger_har_constants_v1.json --expected-host btc-bot-new
        python3 ledger_har_estimate_v1_2026-10-02.py --selftest
"""
import argparse, csv, datetime as dt, gzip, hashlib, json, math, os, random, socket, sys, tempfile

FIRST_MS = int(dt.datetime(2019, 12, 31, tzinfo=dt.timezone.utc).timestamp() * 1000)
END_MS = int(dt.datetime(2025, 8, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
MIN_MS, BAR_MS = 60_000, 14_400_000
LAGS_D, LAGS_W = 6, 42


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


class Abort(Exception):
    pass


def no_sealed(p):
    if "sealed" in os.path.abspath(p).split(os.sep):
        raise Abort(f"refused: {p} has a path component named 'sealed'")


def rv_series(layer0_dir, first_ms=FIRST_MS, end_ms=END_MS):
    no_sealed(layer0_dir)
    rec = json.load(open(os.path.join(layer0_dir, "layer0_summary.json"))).get("sha256", {})
    parts = sorted(k for k in rec if k.replace("\\", "/").startswith("1m/dev/") and k.endswith(".csv.gz"))
    if not parts:
        raise Abort("no 1m/dev partitions recorded")
    hashes = {}
    n_bars = (end_ms - first_ms) // BAR_MS
    rv = [0.0] * n_bars
    cnt = [0] * n_bars
    prev_c, prev_bar = None, None
    for k in parts:
        p = os.path.join(layer0_dir, *k.replace("\\", "/").split("/"))
        h = sha256_file(p)
        if h != rec[k]:
            raise Abort(f"{k} does not hash to the recorded value")
        hashes[k] = h
        with gzip.open(p, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                ms = int(row["open_time_ms"])
                if not (first_ms <= ms < end_ms):
                    raise Abort(f"{k}: minute outside the development window")
                b = (ms - first_ms) // BAR_MS
                o, c = float(row["open"]), float(row["close"])
                start = o if b != prev_bar else prev_c          # the first return of a bar from its first minute's open
                rv[b] += math.log(c / start) ** 2
                cnt[b] += 1
                prev_c, prev_bar = c, b
    return rv, cnt, hashes


def design(rv):
    rows = []
    for t in range(LAGS_W, len(rv)):
        lag = rv[t - LAGS_W:t]
        if rv[t] <= 0 or min(lag) <= 0:
            continue
        x1 = math.log(rv[t - 1])
        x2 = math.log(sum(rv[t - LAGS_D:t]) / LAGS_D)
        x3 = math.log(sum(lag) / LAGS_W)
        rows.append((math.log(rv[t]), 1.0, x1, x2, x3))
    return rows


def ols(rows):
    """Normal equations with Gauss-Jordan (4 x 4), standard library only."""
    k = 4
    XtX = [[0.0] * k for _ in range(k)]
    Xty = [0.0] * k
    for y, *x in rows:
        for i in range(k):
            Xty[i] += x[i] * y
            for j in range(k):
                XtX[i][j] += x[i] * x[j]
    A = [XtX[i][:] + [1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(A[r][c]))
        A[c], A[piv] = A[piv], A[c]
        pv = A[c][c]
        A[c] = [v / pv for v in A[c]]
        for r in range(k):
            if r != c:
                f = A[r][c]
                A[r] = [a - f * b for a, b in zip(A[r], A[c])]
    inv = [row[k:] for row in A]
    beta = [sum(inv[i][j] * Xty[j] for j in range(k)) for i in range(k)]
    n = len(rows)
    res = [y - sum(b * xi for b, xi in zip(beta, x)) for y, *x in rows]
    s2 = sum(e * e for e in res) / (n - k)
    ybar = sum(r[0] for r in rows) / n
    sst = sum((r[0] - ybar) ** 2 for r in rows)
    se = [math.sqrt(s2 * inv[i][i]) for i in range(k)]
    return beta, se, s2, 1 - sum(e * e for e in res) / sst, n


def fmt(x):
    return format(x, ".17g")


def estimate(layer0_dir, out, first_ms=FIRST_MS, end_ms=END_MS, log=print):
    no_sealed(out)
    if os.path.exists(out):
        raise Abort(f"{out} exists (write-once)")
    rv, cnt, hashes = rv_series(layer0_dir, first_ms, end_ms)
    short = sum(1 for c in cnt if c != 240)
    rows = design(rv)
    beta, se, s2, r2, n = ols(rows)
    res = dict(model="log-HAR: ln RV_t = b0 + b1 ln RV_{t-1} + b2 ln mean(RV_{t-1..t-6}) + b3 ln mean(RV_{t-1..t-42})",
               forecast_map="sigma2_f = exp(b0 + b1 x1 + b2 x2 + b3 x3 + s2/2)",
               rv_definition="sum of the 240 squared 1-minute log returns of the 4H bar, the first from the first minute's open",
               coefficients=dict(b0=fmt(beta[0]), b1=fmt(beta[1]), b2=fmt(beta[2]), b3=fmt(beta[3])), s2=fmt(s2),
               std_errors=dict(b0=fmt(se[0]), b1=fmt(se[1]), b2=fmt(se[2]), b3=fmt(se[3])), r_squared=fmt(r2), n=n,
               bars=len(rv), bars_not_240_minutes=short,
               window=dict(first_open_utc=dt.datetime.fromtimestamp(first_ms / 1000, dt.timezone.utc).isoformat(),
                           end_exclusive_utc=dt.datetime.fromtimestamp(end_ms / 1000, dt.timezone.utc).isoformat()),
               partitions_sha256=hashes, script=os.path.basename(__file__),
               script_sha256=sha256_file(os.path.abspath(__file__)), host=socket.gethostname(),
               finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    with open(out, "x") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    log(f"[har] n {n}; b = {[round(b, 5) for b in beta]}; se = {[round(x, 5) for x in se]}; s2 {s2:.5f}; R2 {r2:.4f}; "
        f"bars not 240 min: {short}")
    log(f"[har] {out} {sha256_file(out)}")
    return res


def selftest():
    """Constructed 1-minute data from a known log-HAR volatility process; the fit must recover the coefficients."""
    rnd = random.Random(990501)
    d = tempfile.mkdtemp(prefix="har_st_"); l0 = os.path.join(d, "layer0"); os.makedirs(os.path.join(l0, "1m", "dev"))
    nb = 1500
    first = int(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    true = (-1.0, 0.35, 0.30, 0.25)
    lrv = [-10.0] * LAGS_W
    rows, price = [], 10000.0
    for t in range(nb):
        if t < LAGS_W:
            l = -10.0 + rnd.gauss(0, 0.3)
        else:
            rvh = [math.exp(v) for v in lrv[-LAGS_W:]]
            x1, x2, x3 = lrv[-1], math.log(sum(rvh[-6:]) / 6), math.log(sum(rvh) / 42)
            l = true[0] + true[1] * x1 + true[2] * x2 + true[3] * x3 + rnd.gauss(0, 0.25)
        target_rv = math.exp(l)
        sd = math.sqrt(target_rv / 240)
        incs = [rnd.gauss(0, 1) for _ in range(240)]
        scale = math.sqrt(target_rv / sum(z * z for z in incs))   # the bar's RV equals exp(l) exactly
        o = price
        for i, z in enumerate(incs):
            c = o * math.exp(z * scale)
            rows.append((first + (t * 240 + i) * MIN_MS, o, max(o, c), min(o, c), c))
            o = c
        price = o
        lrv.append(l)
    p = os.path.join(l0, "1m", "dev", "2020-01.csv.gz")
    with gzip.open(p, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["open_time_ms", "open", "high", "low", "close", "volume"])
        for ms, o, h, l_, c in rows:
            w.writerow([ms, repr(o), repr(h), repr(l_), repr(c), "1.0"])
    json.dump(dict(sha256={"1m/dev/2020-01.csv.gz": sha256_file(p)}), open(os.path.join(l0, "layer0_summary.json"), "w"))
    end = first + nb * BAR_MS
    res = estimate(l0, os.path.join(d, "c.json"), first, end, log=lambda s: None)
    b = [float(res["coefficients"][k]) for k in ("b0", "b1", "b2", "b3")]
    se = [float(res["std_errors"][k]) for k in ("b0", "b1", "b2", "b3")]
    t1 = all(abs(bi - ti) < 3.5 * si for bi, ti, si in zip(b, true, se)) and abs(float(res["s2"]) - 0.0625) < 0.01
    print(f"T1 recovers the constructed log-HAR (true {true}, fitted {[round(x, 3) for x in b]}, within 3.5 se; s2 "
          f"{float(res['s2']):.4f} vs 0.0625): {t1}")
    rv, cnt, _ = rv_series(l0, first, end)
    t2 = abs(math.log(rv[100]) - lrv[LAGS_W + 100]) < 1e-9 and all(c == 240 for c in cnt)   # lrv carries 42 seed values first
    print(f"T2 RV per bar equals the constructed RV (first return from the first minute's open): {t2}")
    try:
        estimate(l0, os.path.join(d, "c.json"), first, end, log=lambda s: None); t3a = False
    except Abort:
        t3a = True
    open(p, "ab").write(b"x")
    try:
        estimate(l0, os.path.join(d, "c2.json"), first, end, log=lambda s: None); t3b = False
    except Abort:
        t3b = True
    try:
        estimate(os.path.join(d, "sealed"), os.path.join(d, "c3.json"), log=lambda s: None); t3c = False
    except Abort:
        t3c = True
    print(f"T3 refusals: write-once {t3a}; a partition that is not the recorded one {t3b}; a 'sealed' path {t3c}")
    ok = t1 and t2 and t3a and t3b and t3c
    print("SELFTEST", "PASS" if ok else "FAIL")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer0-dir"); ap.add_argument("--out"); ap.add_argument("--expected-host")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    print(f"# {os.path.basename(__file__)} sha256 {sha256_file(os.path.abspath(__file__))}")
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not (a.layer0_dir and a.out and a.expected_host):
        sys.exit("--layer0-dir, --out and --expected-host are required")
    if socket.gethostname() != a.expected_host:
        sys.exit(f"ABORT: host {socket.gethostname()} is not {a.expected_host}")
    try:
        estimate(a.layer0_dir, a.out)
    except Abort as e:
        sys.exit(f"ABORT: {e}")


if __name__ == "__main__":
    main()
