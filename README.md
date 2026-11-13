# BTC 4H Benchmark Ledger — research in progress

Every 4 hours, before each new BTC 4H candle (Binance USDT-M BTCUSDT perpetual), this repository publishes a small set of
transparent, fixed-formula **benchmark** forecasts. Each entry is timestamped by two independent Time-Stamp Authorities and
OpenTimestamps, and chained by SHA-256 so nothing can be edited. Each forecast is later scored, in public, against what
happened. Anyone can re-check all of it with one script.

**The benchmark rows are a yardstick, not forecasts anyone should trade.**

Research in progress. The rows are transparent benchmarks. There is no model in this ledger yet, and no buy/sell call.

## How to check it yourself

```
git clone <this repository> && cd <it>
python3 code/ledger_verify_v1_1_2026-10-02.py --repo . --source archive
```
Python 3 and `openssl` only. For every entry the script:
1. recomputes the SHA-256 of each line and verifies the chain (`seq`, `prev_hash`);
2. checks `proofs/<seq>.entry` is the line, byte for byte;
3. verifies each timestamp token `proofs/<seq>.tsa<i>.tsr` (`openssl ts -verify`) against the certificates in
   `proofs/tsa_certs/`, giving tau, the earliest token's time;
4. checks tau <= slot + 120 s; a forecast committed later is LATE and leaves every primary score;
5. recomputes every benchmark forecast from Binance's public archive (data.binance.vision);
6. recomputes every score.
It writes `verify_out/scorecard.json`: every number with its denominator and window. The OpenTimestamps proofs
(`proofs/<seq>.entry.ots`) can be checked with `ots verify`.

`created_utc` in an entry is the writing machine's own clock and is **untrusted**; only tau is read.

## What may be said in public (carried verbatim from the frozen page, §10)

**Before any real-data verdict:**
- Say "research in progress".
- The rows are "transparent benchmarks".
- Every synthetic result carries the word *synthetic* in its sentence.
- Do not use "edge", "beats", "predicts" or "signal".

**After a null:** publish the cell name, N and the window, the same day it is filed.

**After certification:** use the certification sentence. Never say "profitable". Make no forward claim until the forward
window is read.

**Always:**
- Every number carries its denominator and window.
- Nothing is promoted up the descriptive → candidate → finding ladder in public before it is on a filed page.

## Layout
- `ledger.jsonl` — the chain, one canonical JSON entry per line, append-only.
- `proofs/` — per entry: the exact bytes, the TSA tokens, the OpenTimestamps proof; `tsa_certs/` the TSAs' certificates.
- `page/` — the frozen pre-registration page (entry 1 names its SHA-256).
- `constants/` — the frozen V-HAR constants (every forecast names their SHA-256).
- `code/` — every script that writes or checks an entry (every entry names the SHA-256 of the code that wrote it).
