#!/usr/bin/env python3
"""
ledger_claims_check_v1_2026-10-02.py — the claims rule as a script (ledger page v1.0 §10; ruling R §7d). Run on every
draft X post (and any public sentence that carries a number) BEFORE it is posted. Standard library only.

A draft PASSES only if all of these hold:
  1. Every number in it is either
       (a) a value in the current scorecard.json (written by ledger_verify), at the precision the draft shows it (only
           a rate — coverage, hit rate — may be written as a percentage) AND the same sentence carries that value's denominator (its n) and
           the post carries the window (the first and last slot dates of the scorecard block it comes from); or
       (b) a declared constant of the page (the DECLARED list below: 24 h, 80%, 1.2816, 120 s, 240 minutes, 42 bars),
           or a date or a time of day. Other small counts are written in words.
  2. Before any real-data verdict (the default phase "pre_verdict"), none of the words "edge", "beats", "predicts",
     "signal" — in any inflection — appear (§10), and in every phase none of the call words below appear (§10 "never a
     forecast and never a call"; "profitable" is never said).
  3. A sentence that mentions a synthetic result carries the word "synthetic" (checked when the draft says "simulat*",
     "backtest*", "test set" or "synthetic").
Output: PASS or FAIL with every reason, one per line; exit code 0 only on PASS.
Usage:  ledger_claims_check_v1_2026-10-02.py --draft post.txt --scorecard verify_out/scorecard.json [--phase pre_verdict]
"""
import argparse, json, re, sys

DECLARED = {"24", "80%", "0.8", "0.80", "0.5", "1.2816", "120", "240", "42", "2026"}   # the page's own parameters;
# small counts are written in words ("six rows"), so a bare "3%" can never pass as a constant
PRE_VERDICT_BANNED = r"\b(edges?|beat|beats|beating|beaten|predicts?|predicted|predicting|prediction|predictions|" \
                     r"signals?)\b"
ALWAYS_BANNED = r"\b(profitable|profit|profits|guaranteed?|buy|buying|sell|selling|go long|go short|take[- ]profit|" \
                r"stop[- ]loss|entry price|target price|price target|moon|100x|alpha)\b"
SYNTH_HINT = r"\b(simulat\w*|backtest\w*|test set|synthetic)\b"
DATE = r"\b20\d\d-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d)?Z?)?\b"
TIME = r"\b\d{1,2}:\d\d(?::\d\d)?\s?(?:UTC|Z)?\b"
URL = r"https?://\S+|@\w+|#\w+"
NUM = r"(?<![\w.])[-+−]?\d+(?:[.,]\d+)?%?(?![\w])"


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def scorecard_values(card):
    """[(value float, n str, window (first, last), label)] for every number in the scorecard."""
    out = []

    def walk(x, path, win):
        if isinstance(x, dict):
            w = x.get("window", win)
            w = (w["first"][:10], w["last"][:10]) if isinstance(w, dict) else win
            if "value" in x and "n" in x:
                out.append((float(x["value"]), x["n"], w, path))
                for i, c in enumerate(x.get("ci95", [])):
                    out.append((float(c), x["n"], w, f"{path}.ci95[{i}]"))
            for k, v in x.items():
                if k not in ("value", "ci95", "window"):
                    walk(v, f"{path}.{k}", w)
        elif isinstance(x, str) and re.fullmatch(r"\d+", x):
            out.append((float(x), x, win, path))                 # a count is its own denominator
    walk(card, "$", None)
    return out


RATES = ("coverage", "hit_rate")


def matches(token, value, label=""):
    """The draft's token equals the value at the precision shown. Only a rate (a coverage or a hit rate, or its CI) may
    be written as a percentage; every other number must be written as the scorecard has it."""
    t = token.replace("−", "-").replace(",", ".")
    pct = t.endswith("%")
    t = t.rstrip("%")
    dec = len(t.split(".")[1]) if "." in t else 0
    try:
        x = float(t)
    except ValueError:
        return False
    if pct and not any(r in label for r in RATES):
        return False
    cands = [value * 100] if pct else [value]
    return any(abs(round(c, dec) - x) < 10 ** (-dec) / 2 + 1e-12 for c in cands)


def check(text, card, phase="pre_verdict"):
    reasons = []
    vals = scorecard_values(card)
    body = re.sub(URL, " ", text)
    for s in sentences(body):
        low = s.lower()
        if phase == "pre_verdict":
            for m in re.finditer(PRE_VERDICT_BANNED, low):
                reasons.append(f"banned before a verdict: '{m.group(0)}' in: {s}")
        for m in re.finditer(ALWAYS_BANNED, low):
            reasons.append(f"never said (a call or a promise): '{m.group(0)}' in: {s}")
        if re.search(SYNTH_HINT, low) and "synthetic" not in low:
            reasons.append(f"a synthetic or simulated result without the word 'synthetic': {s}")
        clean = re.sub(DATE, " ", s)
        clean = re.sub(TIME, " ", clean)
        nums = re.findall(NUM, clean)
        for tok in nums:
            if tok.lstrip("+") in DECLARED:
                continue
            hits = [v for v in vals if matches(tok, v[0], v[3])]
            if not hits:
                reasons.append(f"number '{tok}' is not in the ledger's scorecard nor a declared constant: {s}")
                continue
            ok = False
            for v, n, win, label in hits:
                if n not in [x.lstrip("+") for x in nums] and n != tok:
                    continue
                if win and not (win[0] in text and win[1] in text):
                    continue
                ok = True
                break
            if not ok:
                reasons.append(f"number '{tok}' lacks its denominator in the sentence, or the post lacks its window "
                               f"({hits[0][3]}: n {hits[0][1]}, window {hits[0][2]}): {s}")
    return reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--scorecard", required=True)
    ap.add_argument("--phase", choices=["pre_verdict", "post_verdict"], default="pre_verdict")
    a = ap.parse_args()
    reasons = check(open(a.draft, encoding="utf-8").read(), json.load(open(a.scorecard)), a.phase)
    print("PASS" if not reasons else "FAIL")
    for r in reasons:
        print(f"  - {r}")
    sys.exit(0 if not reasons else 1)


if __name__ == "__main__":
    main()
