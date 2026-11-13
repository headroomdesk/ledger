"""
ledger_core_v1_2026-10-02.py — the Public Research Ledger's core: canonical bytes, the hash chain, the two public data
sources (live REST, bulk archive) behind ONE input path, the benchmark rows' fixed formulas, the target and its flags, the
scores, and the third-party timestamps. Imported by the jobs AND by the stranger's verifier, so both compute a forecast
through the same function from the same rows.
Python 3 standard library + the `openssl` and `git` binaries (+ `ots` from opentimestamps-client on the box).

Governs against: PAFM_PublicResearchLedger_PreRegistration_v1_0_2026-10-02.md (405cbf2c...ccf4) and its v1.1
clarifications page; the ruling it applies (bef24279...ceaa §4). Section numbers below refer to the page.

DECLARED CONSTANTS (Rule 15 items of §11.3 are marked R15):
  EWMA half-life 24 h (R15); D-BASE prior weight 1 bar at 0.5 (R15); the 80% quantile 1.2816 = Phi^-1(0.9) to 4 dp (R15);
  L_max 120 s (R15); the TSAs (R15, in the box config); the forward window start 2026-08-01 00:00 UTC (the fence, §1).
  Downtime flag (§2, D1 v1.1 flat-line rule): a run of >= 5 consecutive target minutes with volume 0 and O = H = L = C.
  Numbers in entries are decimal strings: forecasts and scores with 10 significant digits (format '.9e'); prices and volumes
  exactly as the source prints them; counts as base-10 integers.
THE FENCE IS ENFORCED HERE: both sources refuse any request that starts before 2026-08-01 00:00 UTC (§1).
"""
import csv, datetime as dt, hashlib, io, json, math, os, subprocess, tempfile, time, urllib.error, urllib.request, zipfile

SCHEMA = "L1"
ROW_FAMILY = "BENCH-1"
FORWARD_START = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
HALF_LIFE_H = 24                         # R15
PRIOR_W = 1.0                            # R15: D-BASE's prior weight (bars) at 0.5
Q80 = 1.2816                             # R15: the 80% band quantile
L_MAX_S = 120                            # R15
DOWNTIME_RUN = 5
H1_MS, M1_MS, H4_MS = 3_600_000, 60_000, 14_400_000
HAR_LAGS_D, HAR_LAGS_W = 6, 42
ROWS = ("V-EWMA", "V-HAR", "B-RET80", "B-EXC80", "D-HALF", "D-BASE")
FENCE_MS = int(FORWARD_START.timestamp() * 1000)


class FenceError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------- canonical bytes
def num(x):
    """A forecast or score number as a decimal string, 10 significant digits."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    return format(float(x), ".9e")


def _check(obj, path="$"):
    if isinstance(obj, (float, int)) and not isinstance(obj, bool):
        raise TypeError(f"number at {path}: every number in an entry is a decimal string")
    if isinstance(obj, bool):
        raise TypeError(f"boolean at {path}: flags are the strings '0' and '1'")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"non-string key at {path}")
            _check(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")


def canonical(obj):
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_of(d):
    return int(round(d.timestamp() * 1000))


def ms_of_iso(s):
    return ms_of(dt.datetime.fromisoformat(s.replace("Z", "+00:00")))


def slot_of(now):
    """The 4H bar open T at or before `now` (UTC)."""
    ms = ms_of(now)
    return ms - ms % H4_MS


# ------------------------------------------------------------------------------------------------------- the chain
GENESIS = "0" * 64


def read_chain(ledger_file):
    """All entries in order as (entry, entry_hash); raises ValueError at the first break (the verifier's first check)."""
    out, prev, seq = [], GENESIS, 0
    if not os.path.exists(ledger_file):
        return out
    with open(ledger_file, "rb") as fh:
        data = fh.read()
    if data and not data.endswith(b"\n"):
        raise ValueError("the file does not end in a newline (a torn append)")
    for n, line in enumerate(data.split(b"\n")[:-1] if data else [], 1):
        try:
            e = json.loads(line)
        except ValueError:
            raise ValueError(f"line {n}: not JSON")
        if not isinstance(e, dict) or canonical(e) != line:
            raise ValueError(f"line {n}: bytes are not canonical")
        if e.get("seq") != str(seq + 1) or e.get("prev_hash") != prev:
            raise ValueError(f"line {n}: chain break (seq {e.get('seq')}, prev_hash {str(e.get('prev_hash'))[:12]})")
        if e.get("schema_version") != SCHEMA:
            raise ValueError(f"line {n}: schema_version {e.get('schema_version')}")
        prev, seq = sha256_hex(line), seq + 1
        out.append((e, prev))
    return out


def head(ledger_file):
    ch = read_chain(ledger_file)
    return (ch[-1][1], len(ch)) if ch else (GENESIS, 0)


def make_entry(ledger_file, body):
    prev, seq = head(ledger_file)
    e = dict(body, schema_version=SCHEMA, seq=str(seq + 1), prev_hash=prev)
    b = canonical(e)
    return e, b, sha256_hex(b)


def append_line(ledger_file, b):
    with open(ledger_file, "ab") as fh:
        fh.write(b + b"\n")
        fh.flush(); os.fsync(fh.fileno())


# --------------------------------------------------------------------------------------------- the two data sources
def http_bytes(url, timeout=15, tries=3, data=None, headers=None):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:                                   # noqa: BLE001 — retried, then raised
            last = e
        time.sleep(0.5 + i)
    raise last


def _fence(start_ms):
    if start_ms < FENCE_MS:
        raise FenceError(f"request starts {iso(start_ms)}, before the forward window (2026-08-01): refused (§1)")


class RestSource:
    """Binance USDT-M public REST (§2 'Source, live'). Rows: [open_ms, open, high, low, close, volume] as printed."""
    name = "REST"

    def __init__(self, base):
        self.base = base.rstrip("/")

    def klines(self, interval, start_ms, end_ms, symbol="BTCUSDT"):
        _fence(start_ms)
        step = {"1h": H1_MS, "1m": M1_MS}[interval]
        out, s = [], start_ms
        while s < end_ms:
            url = (f"{self.base}/fapi/v1/klines?symbol={symbol}&interval={interval}&startTime={s}"
                   f"&endTime={end_ms - 1}&limit=1500")
            rows = json.loads(http_bytes(url).decode())
            if not rows:
                break
            for r in rows:
                if int(r[0]) < end_ms and int(r[0]) >= start_ms:
                    out.append([int(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5])])
            s = int(rows[-1][0]) + step
        return out

    def server_time_ms(self):
        return int(json.loads(http_bytes(f"{self.base}/fapi/v1/time").decode())["serverTime"])


class ArchiveSource:
    """Binance's public bulk archive (§2 'Source, verifier'): daily zip files, each checked against its .CHECKSUM file,
    cached locally. A day not yet published raises urllib.error.HTTPError 404."""
    name = "ARCHIVE"

    def __init__(self, base, cache_dir):
        self.base, self.cache = base.rstrip("/"), cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _day(self, interval, d):
        name = f"BTCUSDT-{interval}-{d.strftime('%Y-%m-%d')}"
        p = os.path.join(self.cache, name + ".csv")
        if not os.path.exists(p):
            url = f"{self.base}/data/futures/um/daily/klines/BTCUSDT/{interval}/{name}.zip"
            z = http_bytes(url)
            want = http_bytes(url + ".CHECKSUM").decode().split()[0].strip().lower()
            if sha256_hex(z) != want:
                raise ValueError(f"{name}.zip does not match its .CHECKSUM")
            zf = zipfile.ZipFile(io.BytesIO(z))
            tmp = p + ".part"
            open(tmp, "wb").write(zf.read(zf.namelist()[0]))
            os.replace(tmp, p)
        rows = []
        for r in csv.reader(open(p, newline="")):
            if not r or not r[0].strip().isdigit():
                continue                                          # the header line, when present
            ms = int(r[0]); ms = ms // 1000 if ms > 10 ** 14 else ms
            rows.append([ms, r[1], r[2], r[3], r[4], r[5]])
        return rows

    def klines(self, interval, start_ms, end_ms):
        _fence(start_ms)
        out = []
        d = dt.datetime.fromtimestamp(start_ms / 1000, dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        while ms_of(d) < end_ms:
            out += [r for r in self._day(interval, d) if start_ms <= r[0] < end_ms]
            d += dt.timedelta(days=1)
        return out


def census(rows, start_ms, end_ms, step):
    """Gapless, ordered, on-grid, complete. Returns (complete, missing_count)."""
    grid = list(range(start_ms, end_ms, step))
    times = [r[0] for r in rows]
    return times == grid, len(grid) - len(set(times) & set(grid))


def rows_digest(rows):
    """SHA-256 of the rows exactly as the source printed them (comparable only between reads of the same source)."""
    return sha256_hex(json.dumps([[str(c) for c in r] for r in rows], separators=(",", ":")).encode())


# ------------------------------------------------------------------------------------------- the benchmark formulas
def hourly_returns(h_rows):
    """r_k = ln(C_k / C_{k-1}); the first from the first bar's open."""
    out, prev = [], None
    for r in h_rows:
        o, c = float(r[1]), float(r[4])
        out.append(math.log(c / (o if prev is None else prev)))
        prev = c
    return out


def ewma_var(r, half_life=HALF_LIFE_H):
    lam = 0.5 ** (1.0 / half_life)
    acc = r[0] * r[0]
    for x in r[1:]:
        acc = lam * acc + (1 - lam) * x * x
    return acc


def bars_4h_from_1h(h_rows):
    """Complete 4H bars (open_ms, O of the first hour, H, L, C of the last) from aligned hourly rows."""
    out = []
    for i in range(0, len(h_rows) - len(h_rows) % 4, 4):
        g = h_rows[i:i + 4]
        if g[0][0] % H4_MS:
            raise ValueError("hourly rows not aligned to the 4H grid")
        out.append((g[0][0], float(g[0][1]), max(float(x[2]) for x in g), min(float(x[3]) for x in g), float(g[-1][4])))
    return out


def rv_of_minutes(m_rows):
    """Sum of squared 1-minute log returns, the first from the first minute's open (L2)."""
    s, prev = 0.0, None
    for r in m_rows:
        o, c = float(r[1]), float(r[4])
        s += math.log(c / (o if prev is None else prev)) ** 2
        prev = c
    return s


def har_x(rv_bars):
    """x1, x2, x3 from the last 42 4H RVs (oldest first)."""
    lag = rv_bars[-HAR_LAGS_W:]
    if len(lag) < HAR_LAGS_W or min(lag) <= 0:
        return None
    return math.log(lag[-1]), math.log(sum(lag[-HAR_LAGS_D:]) / HAR_LAGS_D), math.log(sum(lag) / HAR_LAGS_W)


def har_var(x, const):
    """sigma^2_f = exp(b0 + b1 x1 + b2 x2 + b3 x3 + s2/2): the lognormal mean of the fitted log-RV (v1.1 clarification)."""
    c = const["coefficients"]
    b0, b1, b2, b3 = (float(c[k]) for k in ("b0", "b1", "b2", "b3"))
    return math.exp(b0 + b1 * x[0] + b2 * x[1] + b3 * x[2] + float(const["s2"]) / 2)


def forecasts(h_rows, rv_bars, const):
    """The six rows (§4) from the hourly rows since FORWARD_START up to T and the last 42 4H RVs. Pure function."""
    r = hourly_returns(h_rows)
    v_e = 4.0 * ewma_var(r)
    s_e = math.sqrt(v_e)
    x = har_x(rv_bars) if rv_bars is not None else None
    v_h = har_var(x, const) if x else None
    b4 = bars_4h_from_1h(h_rows)
    ups = sum(1 for b in b4 if b[4] > b[1]); downs = sum(1 for b in b4 if b[4] < b[1])
    p_base = (ups + PRIOR_W * 0.5) / (ups + downs + PRIOR_W)
    return {"V-EWMA": {"var": num(v_e)},
            "V-HAR": ({"var": num(v_h)} if v_h is not None else {"status": "NO_FORECAST", "reason": "HAR inputs incomplete"}),
            "B-RET80": {"lo": num(-Q80 * s_e), "hi": num(Q80 * s_e)},
            "B-EXC80": {"up": num(Q80 * s_e), "dn": num(Q80 * s_e)},
            "D-HALF": {"p_up": num(0.5)},
            "D-BASE": {"p_up": num(p_base), "n_up": str(ups), "n_down": str(downs)}}


def compute_forecast(src, T, const):
    """THE input path for slot T, shared by the forecast job and the verifier.
    Returns (complete, forecasts | None, inputs, reason)."""
    h_rows = src.klines("1h", FENCE_MS, T)
    ok_h, miss_h = census(h_rows, FENCE_MS, T, H1_MS)
    if not ok_h:
        return False, None, {"n_1h": str(len(h_rows))}, f"hourly inputs incomplete (missing {miss_h})"
    m_start = T - HAR_LAGS_W * H4_MS
    m_rows = src.klines("1m", m_start, T) if m_start >= FENCE_MS else []
    ok_m = bool(m_rows) and census(m_rows, m_start, T, M1_MS)[0]
    rv_bars = [rv_of_minutes(m_rows[i:i + 240]) for i in range(0, len(m_rows), 240)] if ok_m else None
    inputs = {"last_1h_close_utc": iso(T), "n_1h": str(len(h_rows)), "inputs_digest_1h": rows_digest(h_rows),
              "n_1m_har": str(len(m_rows)), "inputs_digest_1m_har": rows_digest(m_rows) if m_rows else "",
              "har_inputs_complete": str(int(ok_m)), "source": src.name}
    return True, forecasts(h_rows, rv_bars, const), inputs, ""


# --------------------------------------------------------------------------------------------- the target, the flags
def downtime_flag(m_rows):
    """D1 v1.1 flat-line rule: a run of >= 5 consecutive minutes with volume 0 and O = H = L = C."""
    run = best = 0
    for r in m_rows:
        flat = float(r[5]) == 0.0 and float(r[1]) == float(r[2]) == float(r[3]) == float(r[4])
        run = run + 1 if flat else 0
        best = max(best, run)
    return best >= DOWNTIME_RUN


def target_of(m_rows):
    o = float(m_rows[0][1]); c = float(m_rows[-1][4])
    return dict(R=math.log(c / o), RV=rv_of_minutes(m_rows), up=math.log(max(float(x[2]) for x in m_rows) / o),
                dn=math.log(o / min(float(x[3]) for x in m_rows)))


def compute_target(src, T):
    """THE target path for the bar opening at T. Returns None if no minute is available, else a dict of the fields a
    SCORE carries (strings) plus the float target under '_tgt'."""
    m = src.klines("1m", T, T + H4_MS)
    if not m:
        return None
    ok, miss = census(m, T, T + H4_MS, M1_MS)
    tgt = target_of(m)
    pub = {k: num(tgt[k]) for k in ("R", "RV", "up", "dn")}
    # Scores are computed from the PUBLISHED (10-digit) target, so anyone can recompute them from the entry alone.
    return {"target_source": src.name, "target_digest": rows_digest(m), "minute_count": str(len(m)),
            "complete": str(int(ok)), "downtime": str(int(downtime_flag(m))),
            "target": pub, "_tgt": {k: float(v) for k, v in pub.items()}}


# --------------------------------------------------------------------------------------------------------- scoring
def scores(fc, tgt):
    """Per row (§4): log-score of R, QLIKE, MSE-of-log; coverage and width; log-loss, Brier, hit."""
    R, RV = tgt["R"], tgt["RV"]
    out = {}
    for k in ("V-EWMA", "V-HAR"):
        if "var" not in fc[k]:
            out[k] = {"status": "NOT_SCORED", "reason": fc[k].get("status", "")}
            continue
        v = float(fc[k]["var"])
        out[k] = {"log_score": num(-0.5 * math.log(2 * math.pi * v) - R * R / (2 * v)),
                  "qlike": num(RV / v - math.log(RV / v) - 1) if RV > 0 else None,
                  "mse_log": num((math.log(RV) - math.log(v)) ** 2) if RV > 0 else None}
    lo, hi = float(fc["B-RET80"]["lo"]), float(fc["B-RET80"]["hi"])
    out["B-RET80"] = {"covered": str(int(lo <= R <= hi)), "width": num(hi - lo)}
    up, dn = float(fc["B-EXC80"]["up"]), float(fc["B-EXC80"]["dn"])
    out["B-EXC80"] = {"covered_up": str(int(tgt["up"] <= up)), "covered_dn": str(int(tgt["dn"] <= dn)), "width": num(up + dn)}
    y = 1 if R > 0 else (0 if R < 0 else None)                    # R = 0 is a TIE: not scored for direction (v1.1)
    for k in ("D-HALF", "D-BASE"):
        p = float(fc[k]["p_up"])
        if y is None:
            out[k] = {"status": "TIE"}
        else:
            out[k] = {"log_loss": num(-math.log(p if y else 1 - p)), "brier": num((p - y) ** 2),
                      "hit": (str(int((p > 0.5) == (y == 1))) if p != 0.5 else "")}
    return out


def close_enough(a, b):
    """'exact' for equal decimal strings; 'last_digit' within 1 unit of the 10th significant digit (two platforms' libm,
    v1.1 clarification); None otherwise."""
    if a == b:
        return "exact"
    if a is None or b is None:
        return None
    try:
        x, y = float(a), float(b)
    except ValueError:
        return None
    if x == y:
        return "exact"
    return "last_digit" if abs(x - y) <= 1.0000001 * abs(x) * 1e-9 else None


def compare_tree(pub, rec, path=""):
    """Compare two nested dicts of decimal strings. Returns (n_exact, n_last_digit, [mismatch paths])."""
    ex = ld = 0
    bad = []
    keys = set(pub) | set(rec) if isinstance(pub, dict) and isinstance(rec, dict) else None
    if keys is None:
        c = close_enough(pub, rec)
        if c == "exact":
            return 1, 0, []
        if c == "last_digit":
            return 0, 1, []
        return 0, 0, [f"{path}: published {pub} recomputed {rec}"]
    for k in sorted(keys):
        if k not in pub or k not in rec:
            bad.append(f"{path}.{k}: present in only one")
            continue
        a, b, c = compare_tree(pub[k], rec[k], f"{path}.{k}")
        ex += a; ld += b; bad += c
    return ex, ld, bad


# --------------------------------------------------------------------------------------- third-party timestamps
def tsa_request(digest_hex, url, timeout=15):
    """RFC 3161: build the query with openssl (certificate requested), POST it, return the DER reply bytes."""
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "q.tsq")
        subprocess.run(["openssl", "ts", "-query", "-digest", digest_hex, "-sha256", "-cert", "-out", q], check=True,
                       capture_output=True)
        return http_bytes(url, timeout=timeout, tries=1, data=open(q, "rb").read(),
                          headers={"Content-Type": "application/timestamp-query"})


def tsa_time(reply_path):
    """The token's genTime (UTC) from `openssl ts -reply -text`."""
    out = subprocess.run(["openssl", "ts", "-reply", "-in", reply_path, "-text"], check=True, capture_output=True,
                         text=True).stdout
    if "Status: Granted" not in out:
        raise ValueError("the TSA did not grant the request")
    for line in out.splitlines():
        if line.strip().startswith("Time stamp:"):
            t = " ".join(line.split("Time stamp:", 1)[1].split())
            for fmt in ("%b %d %H:%M:%S.%f %Y GMT", "%b %d %H:%M:%S %Y GMT"):
                try:
                    return dt.datetime.strptime(t, fmt).replace(tzinfo=dt.timezone.utc)
                except ValueError:
                    pass
    raise ValueError("no genTime in the token")


def tsa_verify(reply_path, digest_hex, bundle):
    """messageImprint == digest and the signature chains to a certificate in the repo's TSA bundle (L4)."""
    r = subprocess.run(["openssl", "ts", "-verify", "-digest", digest_hex, "-in", reply_path, "-CAfile", bundle,
                        "-untrusted", bundle], capture_output=True, text=True)
    return r.returncode == 0 and "Verification: OK" in (r.stdout + r.stderr)


def tsa_bundle(cert_dir, out_path):
    """Concatenate every PEM in proofs/tsa_certs/ (roots and intermediates) into one bundle file."""
    with open(out_path, "wb") as fo:
        for p in sorted(os.listdir(cert_dir)):
            if p.endswith(".pem"):
                fo.write(open(os.path.join(cert_dir, p), "rb").read().rstrip(b"\n") + b"\n")
    return out_path
