#!/usr/bin/env python3
"""
ledger_jobs_v1_1_2026-10-02.py — the Public Research Ledger's box jobs (page v1.1/v1.2 §2, §5, §7, §8):
  --forecast    at T + 5 s           (systemd timer 00/4:00:05 UTC)
  --score       at T + 10 min        (scores every FORECAST whose bar closed >= 10 min ago and has no SCORE)
  --watchdog    every 5 min          (NO_FORECAST at T + 10 min, NO_SCORE at close + 30 min, the chain re-read, the
                                      pre-flight at T - 10 min; Telegram alerts)
  --crosscheck  daily 06:20 UTC      (the archive re-read of §2: SOURCE_MISMATCH; late scores from the archive after a
                                      NO_SCORE; OpenTimestamps upgrades)
  --notice KIND --text "..."         (PAGE_FROZEN, DATED_LINE, GO_LIVE, CODE_CHANGE, REHEARSAL_SUMMARY)
v1.1 (Fable ruling 654b66b8, §2 Q4 and §3): every NO_FORECAST carries reason_code from a fixed list — SOURCE_GAP
(the exchange's inputs incomplete or unreachable), REMOTE_UNREACHABLE (the git remote), JOB_ERROR (any other failure of
the forecast job), WATCHDOG_ONLY (no forecast attempt recorded on the writing box); each forecast attempt records its
outcome in state/attempts/<slot>.json, which the watchdog reads. Each new TSA token is verified against the repository's
stored certificates at once (an alert on failure: a TSA certificate change is caught within seconds). A rehearsal-only
drill holds one slot's FORECAST push so a lost-push race can be provoked on purpose (refused unless "rehearsal": true).
One writer at a time per box (flock). One chain across boxes: every write re-syncs to the remote head, re-checks its own
uniqueness rule, appends, stamps and pushes a fast-forward; a lost push race discards the local entry and re-decides.

Config (JSON on the box, never in the repo):
  {"repo": "/opt/ledger/repo", "role": "primary"|"secondary", "binance": "https://fapi.binance.com",
   "archive": "https://data.binance.vision", "archive_cache": "/opt/ledger/archive_cache", "state_dir": "/opt/ledger/state",
   "tsa": ["http://timestamp.digicert.com", "http://timestamp.sectigo.com"], "tsa_reserve": "https://freetsa.org/tsr",
   "ots_cmd": ["ots", "stamp"], "ots_upgrade_cmd": ["ots", "upgrade"], "ots_info_cmd": ["ots", "info"],
   "har_constants": "<path>", "har_constants_sha256": "<sha>", "page_sha256": "<sha>",
   "telegram": {"config_py": "/opt/btcbot/config.py"}, "expected_host": "btc-bot-new", "git_remote": "origin",
   "git_branch": "main", "push": true, "go_live_utc": "2026-..T..:00:00Z", "input_retries": 6, "input_retry_s": 5}
The host check (the program's wrong-box rule): if expected_host is set and the hostname differs, the job alerts and
writes nothing.
"""
import argparse, concurrent.futures as cf, datetime as dt, fcntl, glob, http.client, importlib.util, json, os, re, shutil, socket
import subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ledger_core", os.path.join(HERE, "ledger_core_v1_2026-10-02.py"))
L = importlib.util.module_from_spec(_spec); sys.modules.setdefault("ledger_core", L); _spec.loader.exec_module(L)

NOTICE_KINDS = ("PAGE_FROZEN", "DATED_LINE", "GO_LIVE", "CODE_CHANGE", "REHEARSAL_SUMMARY")
UNIQUE_BY_REF = ("SCORE", "NO_SCORE", "LATE", "FAILOVER", "SOURCE_MISMATCH")
NO_FORECAST_REASONS = ("SOURCE_GAP", "REMOTE_UNREACHABLE", "JOB_ERROR", "WATCHDOG_ONLY")
DRILL_KEYS = ("drill_hold_push_slot", "drill_hold_push_s")


class Ctx:
    def __init__(self, cfg, now_fn=None, sleep_fn=None):
        self.cfg = cfg
        self.repo = cfg["repo"]
        self.ledger = os.path.join(self.repo, "ledger.jsonl")
        self.proofs = os.path.join(self.repo, "proofs")
        self.state = cfg.get("state_dir") or os.path.join(self.repo, "..", "state")
        self.now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self.sleep = sleep_fn or time.sleep
        self.rest = L.RestSource(cfg["binance"])
        self.archive = L.ArchiveSource(cfg.get("archive", "https://data.binance.vision"),
                                       cfg.get("archive_cache") or os.path.join(self.repo, "..", "archive_cache"))
        os.makedirs(os.path.join(self.state, "attempts"), exist_ok=True)
        if any(k in cfg for k in DRILL_KEYS) and cfg.get("rehearsal") is not True:
            raise SystemExit("ABORT: drill settings are allowed only in a rehearsal config")

    # --------------------------------------------------------------------------------------------------- git
    def git(self, *a, check=True):
        return subprocess.run(["git", "-C", self.repo, *a], capture_output=True, text=True, check=check)

    def sync(self):
        if self.cfg.get("push", True):
            rem, br = self.cfg.get("git_remote", "origin"), self.cfg.get("git_branch", "main")
            self.git("fetch", "-q", rem)
            self.git("reset", "-q", "--hard", f"{rem}/{br}")
            self.git("clean", "-fdq")                    # proof files of a lost race never survive into a later commit

    def publish(self, msg):
        self.git("add", "-A")
        if not self.git("status", "--porcelain").stdout.strip():
            return True
        self.git("commit", "-q", "-m", msg)
        if not self.cfg.get("push", True):
            return True
        r = self.git("push", "-q", self.cfg.get("git_remote", "origin"), f"HEAD:{self.cfg.get('git_branch', 'main')}",
                     check=False)
        return r.returncode == 0

    # ------------------------------------------------------------------------------------------------ alerts
    def telegram(self):
        """(token, chat_id) from the box's /opt/btcbot/config.py (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), read as text —
        never imported — or from a token file + chat id."""
        t = self.cfg.get("telegram") or {}
        if t.get("config_py"):
            src = open(t["config_py"]).read()
            got = {k: re.search(rf"^{k}\s*=\s*[\"']?([^\"'\s#]+)", src, re.M) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
            return got["TELEGRAM_BOT_TOKEN"].group(1), got["TELEGRAM_CHAT_ID"].group(1)
        return open(t["token_file"]).read().strip(), t["chat_id"]

    def alert(self, text):
        line = f"[ledger {self.cfg.get('role')}] {text}"
        try:
            tok, chat = self.telegram()
            if tok in ("", "YOUR_BOT_TOKEN"):
                raise ValueError("Telegram not configured")
            data = json.dumps({"chat_id": chat, "text": line}).encode()
            urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data,
                                                          headers={"Content-Type": "application/json"}), timeout=10)
        except Exception:                                         # noqa: BLE001 — an alert failure never stops a job
            with open(os.path.join(self.state, "alerts_unsent.log"), "a") as fh:
                fh.write(f"{self.now().isoformat()} {line}\n")

    # ---------------------------------------------------------------------------------------- timestamping
    def stamp(self, seq, entry_bytes, entry_hash):
        """Two TSAs in parallel (L4), the reserve if fewer than two answered, then OpenTimestamps.
        Returns tau (the earliest granted token's genTime) or None."""
        p = os.path.join(self.proofs, f"{seq}.entry")
        open(p, "wb").write(entry_bytes)
        toks = {}
        with cf.ThreadPoolExecutor(2) as ex:
            futs = {ex.submit(L.tsa_request, entry_hash, u): i for i, u in enumerate(self.cfg["tsa"], 1)}
            for f in cf.as_completed(futs):
                try:
                    toks[futs[f]] = f.result()
                except Exception as e:                            # noqa: BLE001 — recorded; the reserve is tried
                    toks[futs[f]] = e
        times = []
        for i in sorted(toks):
            if isinstance(toks[i], bytes):
                times += self._keep(seq, i, toks[i])
            else:
                self.alert(f"TSA {i} failed for seq {seq}: {toks[i]}")
        if len(times) < 2 and self.cfg.get("tsa_reserve"):
            try:
                times += self._keep(seq, 3, L.tsa_request(entry_hash, self.cfg["tsa_reserve"]))
            except Exception as e:                                # noqa: BLE001
                self.alert(f"reserve TSA failed for seq {seq}: {e}")
        self._check_tokens(seq, entry_hash)
        try:
            subprocess.run(list(self.cfg.get("ots_cmd", ["ots", "stamp"])) + [p], check=True, capture_output=True, timeout=60)
        except Exception as e:                                    # noqa: BLE001 — the long-horizon proof; alert, go on
            self.alert(f"OTS stamp failed for seq {seq}: {e}")
        return min(times) if times else None

    def _check_tokens(self, seq, entry_hash):
        """Every token just written must verify against proofs/tsa_certs/ (what a stranger will use); alert if not."""
        cert_dir = os.path.join(self.proofs, "tsa_certs")
        try:
            bundle = L.tsa_bundle(cert_dir, os.path.join(self.state, "tsa_bundle.pem"))
            for tok in sorted(glob.glob(os.path.join(self.proofs, f"{seq}.tsa*.tsr"))):
                if not L.tsa_verify(tok, entry_hash, bundle):
                    self.alert(f"TOKEN {os.path.basename(tok)} does not verify against proofs/tsa_certs "
                               f"(a TSA certificate change? add its new chain as a new file)")
        except Exception as e:                                    # noqa: BLE001 — a check, never a stop
            self.alert(f"token check failed for seq {seq}: {e}")

    def _keep(self, seq, i, reply):
        fp = os.path.join(self.proofs, f"{seq}.tsa{i}.tsr")
        open(fp, "wb").write(reply)
        try:
            return [L.tsa_time(fp)]
        except Exception as e:                                    # noqa: BLE001 — a refused or unreadable reply is dropped
            os.remove(fp)
            self.alert(f"TSA {i} reply for seq {seq} unusable: {e}")
            return []

    # --------------------------------------------------------------------------------------------- writing
    def write(self, body, msg):
        """Append one entry with a fresh head; stamp; push. Returns (entry, hash, tau), or None if the entry's uniqueness
        rule is already met on the remote head (another writer got there first)."""
        for attempt in range(3):
            self.sync()
            if self.taken(body):
                return None
            e, b, h = L.make_entry(self.ledger, body)
            L.append_line(self.ledger, b)
            tau = self.stamp(e["seq"], b, h)
            if (attempt == 0 and self.cfg.get("rehearsal") is True and body["kind"] == "FORECAST"
                    and body.get("slot_utc") == self.cfg.get("drill_hold_push_slot")):
                hold = float(self.cfg.get("drill_hold_push_s", 90))
                self.alert(f"DRILL: holding the push of {body['slot_utc']} for {hold:.0f} s (provoked lost-push race)")
                self.sleep(hold)
            if self.publish(f"seq {e['seq']} {body['kind']} {body.get('slot_utc', '')}".strip()):
                return e, h, tau
            self.alert(f"push lost for seq {e['seq']} ({body['kind']}); re-reading the head")
        raise RuntimeError("could not publish after 3 attempts")

    def taken(self, body):
        k = body["kind"]
        for e, _ in self.entries():
            if k in ("FORECAST", "NO_FORECAST") and e["kind"] in ("FORECAST", "NO_FORECAST") and e.get("slot_utc") == body["slot_utc"]:
                return True
            if k in UNIQUE_BY_REF and e["kind"] == k and e.get("refers_to") == body["refers_to"]:
                return True
            if k in ("PAGE_FROZEN", "DATED_LINE", "GO_LIVE") and e["kind"] == k:
                return True
        return False

    def entries(self):
        return L.read_chain(self.ledger)

    def code(self):
        return {"job_sha256": L.sha256_file(os.path.abspath(__file__)),
                "core_sha256": L.sha256_file(os.path.join(HERE, "ledger_core_v1_2026-10-02.py")),
                "constants_sha256": self.cfg["har_constants_sha256"], "page_sha256": self.cfg.get("page_sha256", "")}

    def base(self, kind, **kw):
        return dict(kind=kind, writer=self.cfg["role"], created_utc=self.now().isoformat(), code=self.code(), **kw)

    def golive_ms(self):
        g = self.cfg.get("go_live_utc")
        return L.ms_of_iso(g) if g else None


def record_attempt(ctx, slot, outcome, reason_code="", detail=""):
    p = os.path.join(ctx.state, "attempts", slot.replace(":", "") + ".json")
    json.dump({"slot_utc": slot, "outcome": outcome, "reason_code": reason_code, "detail": str(detail)[:300],
               "at_utc": ctx.now().isoformat(), "host": socket.gethostname()}, open(p, "w"), sort_keys=True)


def read_attempt(ctx, slot):
    p = os.path.join(ctx.state, "attempts", slot.replace(":", "") + ".json")
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


SOURCE_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, json.JSONDecodeError)   # not ValueError: a bug is a JOB_ERROR


def classify(phase, exc):
    """The fixed reason list (ruling 654b66b8 §2 Q4). A fence refusal is a program error, never a source gap."""
    if isinstance(exc, L.FenceError):
        return "JOB_ERROR"
    if phase == "remote" and isinstance(exc, (subprocess.CalledProcessError, RuntimeError)):
        return "REMOTE_UNREACHABLE"
    if phase == "source" and isinstance(exc, SOURCE_ERRORS):
        return "SOURCE_GAP"
    return "JOB_ERROR"


def har_constants(cfg):
    p = cfg["har_constants"]
    if L.sha256_file(p) != cfg["har_constants_sha256"]:
        raise SystemExit("ABORT: the HAR constants file is not the filed one")
    return json.load(open(p))


# ------------------------------------------------------------------------------------------------------- FORECAST
def forecast(ctx):
    now = ctx.now()
    T = L.slot_of(now)
    slot = L.iso(T)
    if L.ms_of(now) - T > 9 * 60_000:
        record_attempt(ctx, slot, "TOO_LATE")
        return "TOO_LATE_WATCHDOG_OWNS_SLOT"
    phase = ["job"]                                               # which step is running, for the reason code
    try:
        return _forecast_body(ctx, T, slot, phase)
    except Exception as e:                                        # noqa: BLE001 — recorded with its reason, then raised
        code = classify(phase[0], e)
        record_attempt(ctx, slot, "FAILED", code, f"{type(e).__name__}: {e}")
        ctx.alert(f"forecast {slot} failed ({code}): {type(e).__name__}: {e}")
        raise


def _forecast_body(ctx, T, slot, phase):
    if ctx.cfg["role"] == "secondary":
        wait = T + 60_000 - L.ms_of(ctx.now())
        if wait > 0:
            ctx.sleep(wait / 1000)
    phase[0] = "remote"
    ctx.sync()
    phase[0] = "job"
    if any(e["kind"] in ("FORECAST", "NO_FORECAST") and e.get("slot_utc") == slot for e, _ in ctx.entries()):
        record_attempt(ctx, slot, "EXISTS")
        return "EXISTS"
    const = har_constants(ctx.cfg)
    phase[0] = "source"
    for attempt in range(int(ctx.cfg.get("input_retries", 6))):
        ok, fc, inputs, reason = L.compute_forecast(ctx.rest, T, const)
        if ok:
            break
        ctx.sleep(float(ctx.cfg.get("input_retry_s", 5)))         # the last hour can lag a few seconds at T + 5 s
    phase[0] = "remote"
    if not ok:
        res = ctx.write(ctx.base("NO_FORECAST", slot_utc=slot, reason_code="SOURCE_GAP", reason=reason), f"NO_FORECAST {slot}")
        record_attempt(ctx, slot, "NO_FORECAST", "SOURCE_GAP", reason)
        ctx.alert(f"NO_FORECAST {slot} (SOURCE_GAP): {reason}")
        return "NO_FORECAST" if res else "LOST_RACE"
    body = ctx.base("FORECAST", row_family=L.ROW_FAMILY, slot_utc=slot, target_open_utc=slot, inputs=inputs, forecasts=fc)
    res = ctx.write(body, f"FORECAST {slot}")
    record_attempt(ctx, slot, "FORECAST" if res else "LOST_RACE")
    if res is None:
        if ctx.cfg["role"] == "primary":
            ctx.alert(f"{slot}: the secondary's entry reached the remote first")
        return "LOST_RACE"
    e, h, tau = res
    if tau is None or (L.ms_of(tau) - T) > L.L_MAX_S * 1000:
        ctx.write(ctx.base("LATE", slot_utc=slot, refers_to=h, tau_utc=(L.iso(L.ms_of(tau)) if tau else "")), f"LATE {slot}")
        ctx.alert(f"LATE {slot}: tau {tau}")
    if ctx.cfg["role"] == "secondary":
        ctx.write(ctx.base("FAILOVER", slot_utc=slot, refers_to=h), f"FAILOVER {slot}")
        ctx.alert(f"FAILOVER: the secondary wrote {slot}")
    return "FORECAST"


# ---------------------------------------------------------------------------------------------------------- SCORE
def score_body(ctx, e, h, tg, late):
    return ctx.base("SCORE", slot_utc=e["slot_utc"], refers_to=h, row_family=e["row_family"],
                    late_score=str(int(late)), scores=L.scores(e["forecasts"], tg["_tgt"]),
                    **{k: v for k, v in tg.items() if k != "_tgt"})


def may_score(ctx, e):
    """§8: the secondary never writes a SCORE for a forecast the primary wrote."""
    return ctx.cfg["role"] == "primary" or e.get("writer") == "secondary"


def score(ctx):
    """Score, from REST, every FORECAST whose bar closed >= 10 min ago, with no SCORE and no NO_SCORE (a NO_SCORE bar is
    scored later from the archive by --crosscheck, marked late)."""
    now = L.ms_of(ctx.now())
    ctx.sync()
    ch = ctx.entries()
    closed = {e.get("refers_to") for e, _ in ch if e["kind"] in ("SCORE", "NO_SCORE")}
    n = 0
    for e, h in ch:
        if e["kind"] != "FORECAST" or h in closed or not may_score(ctx, e):
            continue
        T = L.ms_of_iso(e["slot_utc"])
        if now < T + L.H4_MS + 600_000:
            continue
        tg = L.compute_target(ctx.rest, T)
        if tg is None:
            continue
        if ctx.write(score_body(ctx, e, h, tg, False), f"SCORE {e['slot_utc']}") is not None:
            n += 1
    return f"SCORED {n}"


# ------------------------------------------------------------------------------------------------------- WATCHDOG
def watchdog(ctx):
    """The heartbeat on flow and on correctness of flow."""
    now_dt = ctx.now()
    now = L.ms_of(now_dt)
    ctx.sync()
    try:
        ch = ctx.entries()
    except ValueError as e:
        ctx.alert(f"CHAIN BREAK: {e}")
        return "CHAIN_BREAK"
    acts = []
    T_next = L.slot_of(now_dt) + L.H4_MS
    if T_next - 10 * 60_000 <= now < T_next - 5 * 60_000:
        acts.append(preflight(ctx))
    g = ctx.golive_ms()
    if g is not None:
        have = {e.get("slot_utc") for e, _ in ch if e["kind"] in ("FORECAST", "NO_FORECAST")}
        T = g + (-g) % L.H4_MS
        while T + 10 * 60_000 <= now:                     # every slot since go-live, not only the current one
            slot = L.iso(T)
            if slot not in have:
                att = read_attempt(ctx, slot) or {}
                code = att.get("reason_code") if att.get("reason_code") in NO_FORECAST_REASONS else "WATCHDOG_ONLY"
                why = f"no forecast by T + 10 min (watchdog); this box's attempt: {att.get('outcome', 'none recorded')}"
                if att.get("detail"):
                    why += f" — {att['detail']}"
                if ctx.write(ctx.base("NO_FORECAST", slot_utc=slot, reason_code=code, reason=why), f"NO_FORECAST {slot}"):
                    ctx.alert(f"NO_FORECAST {slot} ({code}, watchdog)"); acts.append("NO_FORECAST")
                have.add(slot)
            T += L.H4_MS
    closed = {e.get("refers_to") for e, _ in ch if e["kind"] in ("SCORE", "NO_SCORE")}
    for e, h in ch:
        if e["kind"] == "FORECAST" and h not in closed and now >= L.ms_of_iso(e["slot_utc"]) + L.H4_MS + 30 * 60_000:
            if ctx.write(ctx.base("NO_SCORE", slot_utc=e["slot_utc"], refers_to=h, reason="the score missed its slot"),
                         f"NO_SCORE {e['slot_utc']}"):
                ctx.alert(f"NO_SCORE {e['slot_utc']}"); acts.append("NO_SCORE")
    return ",".join(acts) or "OK"


def preflight(ctx):
    """T - 10 min (§5): clock vs the exchange, the source, disk, both TSAs. Alerts only; writes nothing."""
    bad = []
    try:
        t0 = time.time(); st = ctx.rest.server_time_ms(); t1 = time.time()
        off = abs(st - (t0 + t1) / 2 * 1000)
        if off > 1000:
            bad.append(f"clock offset {off:.0f} ms vs the exchange")
    except Exception as e:                                        # noqa: BLE001
        bad.append(f"exchange unreachable: {e}")
    free = shutil.disk_usage(ctx.repo).free
    if free < 1 << 30:
        bad.append(f"disk free {free >> 20} MiB")
    for i, u in enumerate(ctx.cfg["tsa"], 1):
        try:
            p = os.path.join(ctx.state, f"preflight_tsa{i}.tsr")
            open(p, "wb").write(L.tsa_request(L.sha256_hex(b"preflight " + ctx.now().isoformat().encode()), u))
            L.tsa_time(p)
        except Exception as e:                                    # noqa: BLE001
            bad.append(f"TSA {i} pre-flight failed: {e}")
    if bad:
        ctx.alert("PRE-FLIGHT: " + "; ".join(bad))
        return "PREFLIGHT_FAIL"
    return "PREFLIGHT_OK"


# ----------------------------------------------------------------------------------------------------- CROSSCHECK
def crosscheck(ctx, lookback_days=8):
    """§2 two-source check: every FORECAST and REST SCORE whose days the archive has published (>= 30 h old, within
    the lookback) is recomputed from the archive; a difference is a SOURCE_MISMATCH notice. A NO_SCORE bar is scored
    from the archive (late_score 1). Then the OpenTimestamps upgrades."""
    now = L.ms_of(ctx.now())
    ctx.sync()
    ch = ctx.entries()
    const = har_constants(ctx.cfg)
    lo, hi = now - lookback_days * 86_400_000, now - 30 * 3_600_000
    flagged = {e.get("refers_to") for e, _ in ch if e["kind"] == "SOURCE_MISMATCH"}
    scored = {e.get("refers_to") for e, _ in ch if e["kind"] == "SCORE"}
    no_score = {e.get("refers_to") for e, _ in ch if e["kind"] == "NO_SCORE"}
    fc = {h: e for e, h in ch if e["kind"] == "FORECAST"}
    out = {"checked": 0, "mismatch": 0, "late_scored": 0, "unpublished": 0}
    for e, h in ch:
        if e["kind"] not in ("FORECAST", "SCORE"):
            continue
        T = L.ms_of_iso(e["slot_utc"])
        ripe = T + L.H4_MS <= hi                                  # the archive has published every day involved
        try:
            # (1) the two-source check of a FORECAST
            if e["kind"] == "FORECAST" and ripe and lo <= T and h not in flagged:
                ok, rec, _, _ = L.compute_forecast(ctx.archive, T, const)
                out["checked"] += 1
                bad = L.compare_tree(e["forecasts"], rec)[2] if ok else ["archive inputs incomplete"]
                if bad:
                    mismatch(ctx, e, h, bad); out["mismatch"] += 1
            # (2) the two-source check of a REST SCORE
            if e["kind"] == "SCORE" and e.get("target_source") == "REST" and ripe and lo <= T and h not in flagged:
                tg = L.compute_target(ctx.archive, T)
                out["checked"] += 1
                f = fc[e["refers_to"]]
                rec = {"target": tg["target"], "scores": L.scores(f["forecasts"], tg["_tgt"]),
                       "minute_count": tg["minute_count"], "complete": tg["complete"], "downtime": tg["downtime"]}
                bad = L.compare_tree({k: e[k] for k in rec}, rec)[2]
                if bad:
                    mismatch(ctx, e, h, bad); out["mismatch"] += 1
            # (3) a NO_SCORE bar is scored from the archive, marked late (no lower age bound: never left unscored)
            if e["kind"] == "FORECAST" and ripe and h in no_score and h not in scored and may_score(ctx, e):
                tg = L.compute_target(ctx.archive, T)
                if tg is not None and ctx.write(score_body(ctx, e, h, tg, True), f"SCORE {e['slot_utc']} (archive, late)"):
                    out["late_scored"] += 1
        except urllib.error.HTTPError as x:
            if x.code != 404:
                raise
            out["unpublished"] += 1
            if T is not None and now - T > 4 * 86_400_000:
                ctx.alert(f"archive still missing a day for {e.get('slot_utc')}")
    out["ots"] = ots_upgrade(ctx)
    return json.dumps(out, sort_keys=True)


def mismatch(ctx, e, h, bad):
    ctx.write(ctx.base("SOURCE_MISMATCH", slot_utc=e["slot_utc"], refers_to=h, refers_kind=e["kind"],
                       detail=bad[:12], n_differences=str(len(bad))), f"SOURCE_MISMATCH {e['slot_utc']}")
    ctx.alert(f"SOURCE_MISMATCH {e['kind']} {e['slot_utc']}: {len(bad)} differences")


def ots_upgrade(ctx):
    """Complete pending OpenTimestamps proofs (Bitcoin attestation arrives hours after the calendar receipt). The .ots
    files are proofs beside the chain, not chain entries: upgrading one changes no entry and no hash."""
    ctx.sync()
    done_p = os.path.join(ctx.state, "ots_complete.json")
    done = set(json.load(open(done_p))) if os.path.exists(done_p) else set()
    n = 0
    for p in sorted(glob.glob(os.path.join(ctx.proofs, "*.entry.ots"))):
        b = os.path.basename(p)
        if b in done:
            continue
        try:
            subprocess.run(list(ctx.cfg.get("ots_upgrade_cmd", ["ots", "upgrade"])) + [p], capture_output=True, timeout=60)
            info = subprocess.run(list(ctx.cfg.get("ots_info_cmd", ["ots", "info"])) + [p], capture_output=True,
                                  text=True, timeout=60).stdout
            if "BitcoinBlockHeaderAttestation" in info:
                done.add(b); n += 1
        except Exception:                                         # noqa: BLE001 — retried tomorrow
            pass
    for bak in glob.glob(os.path.join(ctx.proofs, "*.bak")):
        os.remove(bak)                                            # `ots upgrade` keeps a .bak of the pending proof
    if ctx.publish("ots upgrade"):
        json.dump(sorted(done), open(done_p, "w"))
    return str(n)


# --------------------------------------------------------------------------------------------------------- NOTICE
def notice(ctx, kind, text):
    if kind not in NOTICE_KINDS:
        raise SystemExit(f"unknown notice {kind}")
    kw = {"text": text}
    if kind == "PAGE_FROZEN":
        kw["page_sha256"] = ctx.cfg["page_sha256"]
    res = ctx.write(ctx.base(kind, **kw), kind)
    return "WRITTEN" if res else "EXISTS"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    for f in ("forecast", "score", "watchdog", "crosscheck"):
        g.add_argument(f"--{f}", action="store_true")
    g.add_argument("--notice")
    ap.add_argument("--text", default="")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    ctx = Ctx(cfg)
    if cfg.get("expected_host") and socket.gethostname() != cfg["expected_host"]:
        ctx.alert(f"HOSTNAME MISMATCH: expected {cfg['expected_host']}, running on {socket.gethostname()}; nothing written")
        sys.exit(3)
    lock = open(os.path.join(ctx.state, "ledger.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if a.forecast:
            print(forecast(ctx))
        elif a.score:
            print(score(ctx))
        elif a.watchdog:
            print(watchdog(ctx))
        elif a.crosscheck:
            print(crosscheck(ctx))
        else:
            print(notice(ctx, a.notice, a.text))
    except Exception as e:                                        # noqa: BLE001 — every failure reaches the operator
        ctx.alert(f"job error: {type(e).__name__}: {e}")
        raise
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
