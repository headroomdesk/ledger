#!/usr/bin/env python3
"""
ledger_verify_v1_1_2026-10-02.py — THE STRANGER'S SCRIPT (ledger page v1.2 §6, §7). Anyone can run it on a clone of the
public repository: Python 3 standard library + the `openssl` binary. No key, no account, no trust in our clock.

Run from the repository root:   python3 code/ledger_verify_v1_1_2026-10-02.py --repo .
  --source archive   (default) recompute from Binance's public bulk archive (data.binance.vision), each file checked
                     against its .CHECKSUM; days the archive has not yet published are skipped and counted
  --source rest      recompute from Binance's live REST API (the same source the jobs read)
  --source none      the chain, the proofs, the rules and the scorecard only
  --append-only REF  (CI) also require that, since git REF, ledger.jsonl only grew by appended lines and no existing
                     proof, constants, page or code file was changed or removed

The checks, for every entry (the six steps of §6, plus the rules of §3, §5, §8):
  1. the chain: canonical bytes, gapless seq, prev_hash = SHA-256 of the line before (the first break is reported);
  2. proofs/<seq>.entry is byte-identical to the line;
  3. every RFC 3161 token proofs/<seq>.tsa<i>.tsr verifies (messageImprint = the entry's SHA-256; the signature chains to
     the TSA certificates stored in proofs/tsa_certs/); tau = the earliest token's genTime;
  4. a FORECAST is ON TIME iff tau <= slot + 120 s; otherwise (or with no token) it is LATE: excluded from every primary
     score and scored beside;
  5. every FORECAST is recomputed from the public data and must equal the published decimal strings (exactly, or within
     one unit of the 10th significant digit — such cases are counted);
  6. every SCORE is recomputed from the 240 target minutes; with the same source its target_digest must match too.
  Rules: entry 1 is PAGE_FROZEN naming a page file in page/; slots on the 4H grid; one FORECAST-or-NO_FORECAST per slot;
  every NO_FORECAST carries a reason_code from the fixed list (v1.1; ruling 654b66b8 §2 Q4) and the scorecard's uptime
  counts them by reason; each SCORE refers to an earlier FORECAST, at most one per forecast; the secondary never scored a primary's forecast; the
  code and constants each entry names are in the repository. A recomputation difference already disclosed by a
  SOURCE_MISMATCH entry is reported as explained, not as a failure.
  OpenTimestamps: the presence of proofs/<seq>.entry.ots is counted; check its Bitcoin attestation with `ots verify`.
Output (in --out): verify_report.json and scorecard.json. Exit code 0 only if every check that ran passed.
"""
import argparse, datetime as dt, glob, importlib.util, json, math, os, subprocess, sys, tempfile, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("ledger_core", os.path.join(HERE, "ledger_core_v1_2026-10-02.py"))
L = importlib.util.module_from_spec(_spec); sys.modules.setdefault("ledger_core", L); _spec.loader.exec_module(L)

ARCHIVE_AGE_MS = 30 * 3_600_000
NO_FORECAST_REASONS = ("SOURCE_GAP", "REMOTE_UNREACHABLE", "JOB_ERROR", "WATCHDOG_ONLY")


def tolerant_chain(path):
    """Like read_chain, but returns the entries before the first break and the break itself."""
    try:
        return L.read_chain(path), None
    except ValueError as e:
        good = []
        prev, seq = L.GENESIS, 0
        for line in open(path, "rb").read().split(b"\n"):
            try:
                x = json.loads(line)
                if L.canonical(x) != line or x.get("seq") != str(seq + 1) or x.get("prev_hash") != prev:
                    break
            except Exception:                                     # noqa: BLE001
                break
            prev, seq = L.sha256_hex(line), seq + 1
            good.append((x, prev))
        return good, str(e)


def verify(repo, src, out_dir, now=None, log=print):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ms = L.ms_of(now)
    proofs = os.path.join(repo, "proofs")
    rep = dict(script=os.path.basename(__file__), script_sha256=L.sha256_file(os.path.abspath(__file__)),
               core_sha256=L.sha256_file(os.path.join(HERE, "ledger_core_v1_2026-10-02.py")), run_utc=now.isoformat(),
               source=(src.name if src else "none"), failures=[], warnings=[], entries=0, kinds={},
               late=[], no_token=[], single_token=[], ots_missing=[], explained=[],
               recompute={"forecasts": 0, "scores": 0, "exact": 0, "last_digit": 0, "not_yet_published": 0})
    F = rep["failures"].append
    ch, brk = tolerant_chain(os.path.join(repo, "ledger.jsonl"))
    if brk:
        F(f"CHAIN: {brk} — nothing after the break can be trusted")
    rep["entries"] = len(ch)
    cert_dir = os.path.join(proofs, "tsa_certs")
    tmpd = tempfile.mkdtemp()
    bundle = L.tsa_bundle(cert_dir, os.path.join(tmpd, "bundle.pem")) if os.path.isdir(cert_dir) else None
    code_files = {L.sha256_file(p) for p in glob.glob(os.path.join(repo, "code", "*.py"))}
    page_files = {L.sha256_file(p) for p in glob.glob(os.path.join(repo, "page", "*.md"))}
    const_files = {L.sha256_file(p): p for p in glob.glob(os.path.join(repo, "constants", "*.json"))}
    consts = {}
    mismatch_refs = {e.get("refers_to") for e, _ in ch if e["kind"] == "SOURCE_MISMATCH"}
    tau_of, fc = {}, {}
    slots, scored, late_notices = set(), set(), set()
    for i, (e, h) in enumerate(ch):
        seq, kind = e["seq"], e["kind"]
        rep["kinds"][kind] = rep["kinds"].get(kind, 0) + 1
        line = L.canonical(e)
        pe = os.path.join(proofs, f"{seq}.entry")
        if not os.path.exists(pe) or open(pe, "rb").read() != line:
            F(f"seq {seq}: proofs/{seq}.entry missing or not byte-identical to the line")
        taus = []
        for tok in sorted(glob.glob(os.path.join(proofs, f"{seq}.tsa*.tsr"))):
            if bundle and L.tsa_verify(tok, h, bundle):
                taus.append(L.tsa_time(tok))
            else:
                F(f"seq {seq}: {os.path.basename(tok)} does not verify (imprint or certificate chain)")
        if not taus:
            rep["no_token"].append(seq)
        elif len(taus) == 1:
            rep["single_token"].append(seq)
        if not os.path.exists(pe + ".ots"):
            rep["ots_missing"].append(seq)
        tau_of[h] = min(taus) if taus else None
        code = e.get("code", {})
        for k in ("job_sha256", "core_sha256"):
            if code.get(k) and code[k] not in code_files:
                F(f"seq {seq}: the code it names ({k} {code[k][:12]}) is not in code/")
        if i == 0 and (kind != "PAGE_FROZEN" or e.get("page_sha256") not in page_files):
            F("entry 1 is not a PAGE_FROZEN naming a page file in page/")
        if kind in ("FORECAST", "NO_FORECAST"):
            T = L.ms_of_iso(e["slot_utc"])
            if T % L.H4_MS:
                F(f"seq {seq}: slot {e['slot_utc']} is not on the 4H grid")
            if e["slot_utc"] in slots:
                F(f"seq {seq}: a second entry for slot {e['slot_utc']}")
            slots.add(e["slot_utc"])
        if kind == "NO_FORECAST" and e.get("reason_code") not in NO_FORECAST_REASONS:
            F(f"seq {seq}: NO_FORECAST without a reason_code from the fixed list ({e.get('reason_code')})")
        if kind == "LATE":
            late_notices.add(e["refers_to"])
        if kind == "FORECAST":
            fc[h] = e
            tau = tau_of[h]
            if tau is None or L.ms_of(tau) - T > L.L_MAX_S * 1000:
                rep["late"].append(e["slot_utc"])
            cs = code.get("constants_sha256")
            if cs not in consts:
                if cs not in const_files:
                    F(f"seq {seq}: constants {str(cs)[:12]} not in constants/")
                    continue
                consts[cs] = json.load(open(const_files[cs]))
            if src is not None and recompute_due(src, T, now_ms):
                try:
                    ok, rec, inputs, why = L.compute_forecast(src, T, consts[cs])
                except urllib.error.HTTPError as x:
                    if x.code != 404:
                        raise
                    rep["recompute"]["not_yet_published"] += 1
                    continue
                rep["recompute"]["forecasts"] += 1
                ex, ld, bad = L.compare_tree(e["forecasts"], rec) if ok else (0, 0, [f"inputs incomplete: {why}"])
                if ok and src.name == e["inputs"].get("source") and inputs["inputs_digest_1h"] != e["inputs"]["inputs_digest_1h"]:
                    bad.append("inputs_digest_1h differs on the same source")
                tally(rep, F, seq, e, h, ex, ld, bad, mismatch_refs)
        elif kind == "SCORE":
            f = fc.get(e["refers_to"])
            if f is None:
                F(f"seq {seq}: SCORE refers to no earlier FORECAST")
                continue
            if e["refers_to"] in scored:
                F(f"seq {seq}: a second SCORE for one forecast")
            scored.add(e["refers_to"])
            if e.get("writer") == "secondary" and f.get("writer") == "primary":
                F(f"seq {seq}: the secondary scored a primary's forecast (§8)")
            if e["slot_utc"] != f["slot_utc"]:
                F(f"seq {seq}: SCORE slot differs from its forecast's")
            # the published scores must follow from the published target and forecast (no source needed)
            pub_t = {k: float(v) for k, v in e["target"].items()}
            ex, ld, bad = L.compare_tree(e["scores"], L.scores(f["forecasts"], pub_t))
            for b in bad:
                F(f"seq {seq}: published scores do not follow from the published target: {b}")
            T = L.ms_of_iso(e["slot_utc"])
            if src is not None and recompute_due(src, T + L.H4_MS, now_ms):
                try:
                    tg = L.compute_target(src, T)
                except urllib.error.HTTPError as x:
                    if x.code != 404:
                        raise
                    rep["recompute"]["not_yet_published"] += 1
                    continue
                rep["recompute"]["scores"] += 1
                rec = {"target": tg["target"], "scores": L.scores(f["forecasts"], tg["_tgt"]),
                       "minute_count": tg["minute_count"], "complete": tg["complete"], "downtime": tg["downtime"]}
                ex, ld, bad = L.compare_tree({k: e[k] for k in rec}, rec)
                if src.name == e["target_source"] and tg["target_digest"] != e["target_digest"]:
                    bad.append("target_digest differs on the same source")
                tally(rep, F, seq, e, h, ex, ld, bad, mismatch_refs)
    for h, e in fc.items():
        if e["slot_utc"] in rep["late"] and h not in late_notices:
            rep["warnings"].append(f"{e['slot_utc']}: LATE by the tokens but no LATE notice was written")
    rep["ots_present"] = rep["entries"] - len(rep["ots_missing"])
    card = scorecard(ch, fc, set(rep["late"]), rep["single_token"])
    rep["passed"] = not rep["failures"]
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "verify_report.json"), "w").write(json.dumps(rep, indent=1, sort_keys=True, default=str))
    open(os.path.join(out_dir, "scorecard.json"), "wb").write(L.canonical(card))
    r = rep["recompute"]
    log(f"verify: {rep['entries']} entries {rep['kinds']}; late {len(rep['late'])}; no token {len(rep['no_token'])}; "
        f"single token {len(rep['single_token'])}; recomputed {r['forecasts']} forecasts + {r['scores']} scores "
        f"(exact {r['exact']}, last digit {r['last_digit']}, not yet published {r['not_yet_published']}); "
        f"explained by SOURCE_MISMATCH {len(rep['explained'])}; OTS present {rep['ots_present']}/{rep['entries']} "
        f"-> {'PASS' if rep['passed'] else 'FAIL'}")
    for f in rep["failures"][:25]:
        log(f"  FAIL {f}")
    return rep, card


def recompute_due(src, end_ms, now_ms):
    return now_ms - end_ms > (ARCHIVE_AGE_MS if src.name == "ARCHIVE" else 600_000)


def tally(rep, F, seq, e, h, ex, ld, bad, mismatch_refs):
    rep["recompute"]["exact"] += ex
    rep["recompute"]["last_digit"] += ld
    if bad:
        if h in mismatch_refs:
            rep["explained"].append(f"seq {seq} {e['kind']} {e['slot_utc']}: {len(bad)} differences, disclosed")
        else:
            for b in bad[:6]:
                F(f"seq {seq} {e['kind']} {e['slot_utc']}: does not recompute: {b}")


# ----------------------------------------------------------------------------------------------------- the scorecard
def scorecard(ch, fc, late, single=()):
    """Every number with its denominator and window (§4, §10). Primary: on-time forecasts, complete and downtime-free
    targets. LATE forecasts are scored beside. Nothing is a stored running total: this is rebuilt from the full log."""
    sched = [e for e, _ in ch if e["kind"] in ("FORECAST", "NO_FORECAST")]
    sc = [e for e, _ in ch if e["kind"] == "SCORE" and e["refers_to"] in fc]
    prim = [s for s in sc if s["slot_utc"] not in late and s["complete"] == "1" and s.get("downtime") == "0"]
    beside = [s for s in sc if s["slot_utc"] in late]
    flags = sum(1 for s in sc if s["slot_utc"] not in late and (s["complete"] != "1" or s.get("downtime") != "0"))
    return {"schema": "SCORECARD-1", "row_family": L.ROW_FAMILY,
            "uptime": {"scheduled": str(len(sched)), "published": str(sum(1 for e in sched if e["kind"] == "FORECAST")),
                       "on_time": str(sum(1 for e in sched if e["kind"] == "FORECAST" and e["slot_utc"] not in late)),
                       "no_forecast": str(sum(1 for e in sched if e["kind"] == "NO_FORECAST")), "late": str(len(late)),
                       "no_forecast_by_reason": {r: str(sum(1 for e in sched if e["kind"] == "NO_FORECAST"
                                                             and e.get("reason_code") == r)) for r in NO_FORECAST_REASONS},
                       "single_token": str(len(single))},
            "primary": block(prim, fc, len(sched), flags), "beside_late": block(beside, fc, len(sched), 0)}


def block(use, fc, n_sched, flags):
    out = {"n_scored": str(len(use)), "n_scheduled": str(n_sched), "flags_excluded": str(flags), "rows": {}}
    if use:
        out["window"] = {"first": min(s["slot_utc"] for s in use), "last": max(s["slot_utc"] for s in use)}

    def agg(row, key, kind="mean"):
        vals = [s["scores"][row][key] for s in use if s["scores"].get(row, {}).get(key) not in (None, "")]
        if not vals:
            return None
        v = [float(x) for x in vals]
        a = {"value": L.num(sum(v) / len(v)), "n": str(len(v))}
        if kind == "rate":
            p, n = sum(v) / len(v), len(v)
            se = math.sqrt(p * (1 - p) / n)
            a["ci95"] = [L.num(max(0.0, p - 1.96 * se)), L.num(min(1.0, p + 1.96 * se))]
        return a

    for row in ("V-EWMA", "V-HAR"):
        out["rows"][row] = {"mean_log_score": agg(row, "log_score"), "mean_qlike": agg(row, "qlike"),
                            "mean_mse_log": agg(row, "mse_log"), "mz_slope_log": mz(use, fc, row)}
    out["rows"]["B-RET80"] = {"coverage": agg("B-RET80", "covered", "rate"), "mean_width": agg("B-RET80", "width")}
    out["rows"]["B-EXC80"] = {"coverage_up": agg("B-EXC80", "covered_up", "rate"),
                              "coverage_dn": agg("B-EXC80", "covered_dn", "rate"), "mean_width": agg("B-EXC80", "width")}
    for row in ("D-HALF", "D-BASE"):
        out["rows"][row] = {"mean_log_loss": agg(row, "log_loss"), "mean_brier": agg(row, "brier"),
                            "hit_rate": agg(row, "hit", "rate")}
    return out


def mz(use, fc, row):
    """Mincer–Zarnowitz slope of ln RV on ln sigma^2_f (beside, §4)."""
    pts = [(math.log(float(fc[s["refers_to"]]["forecasts"][row]["var"])), math.log(float(s["target"]["RV"])))
           for s in use if "var" in fc[s["refers_to"]]["forecasts"][row] and float(s["target"]["RV"]) > 0]
    if len(pts) < 3:
        return None
    mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0:
        return None
    return {"value": L.num(sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx), "n": str(len(pts))}


# ------------------------------------------------------------------------------------------------- the CI append rule
def append_only(repo, ref):
    """Since `ref`: ledger.jsonl only grew by whole appended lines; no existing proof (.entry, .tsr), constants, page or
    code file was modified or removed. (.ots files may change: an upgrade adds the Bitcoin attestation.)"""
    bad = []

    def git(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, check=False)
    old = git("show", f"{ref}:ledger.jsonl")
    new = open(os.path.join(repo, "ledger.jsonl"), "rb").read()
    if old.returncode == 0 and not new.startswith(old.stdout):
        bad.append("ledger.jsonl: an existing line was modified or removed")
    for d in git("diff", "--name-status", ref, "--").stdout.decode().splitlines():
        st, *paths = d.split("\t")
        p = paths[0]
        if st[0] in "DMR" and (p.startswith(("constants/", "page/", "code/"))
                               or (p.startswith("proofs/") and not p.endswith(".ots"))):
            bad.append(f"{p}: {'removed' if st[0] == 'D' else 'modified'} (write-once)")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--source", choices=["archive", "rest", "none"], default="archive")
    ap.add_argument("--archive", default="https://data.binance.vision")
    ap.add_argument("--rest", default="https://fapi.binance.com")
    ap.add_argument("--cache", default=None)
    ap.add_argument("--out", default="verify_out")
    ap.add_argument("--append-only", default=None, metavar="REF")
    a = ap.parse_args()
    src = None
    if a.source == "archive":
        src = L.ArchiveSource(a.archive, a.cache or os.path.join(a.out, "archive_cache"))
    elif a.source == "rest":
        src = L.RestSource(a.rest)
    rep, _ = verify(a.repo, src, a.out)
    ok = rep["passed"]
    if a.append_only:
        bad = append_only(a.repo, a.append_only)
        for b in bad:
            print(f"  FAIL append-only: {b}")
        ok = ok and not bad
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
