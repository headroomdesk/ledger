# PAFM — Public Research Ledger: Pre-Registration v1.3.1 — a Benchmarks-Only Forward Ledger of 4H BTC Forecasts, Committed Before Observation and Verifiable by a Stranger; 2026-11-02

**Seat:** Implementor.
**Status:** v1.3.1. **[v1.3.1]** v1.3 (`8c408ccc…3543`) with the two record lines of `Fable_Ruling_LedgerPageV13Read_…_2026-11-02.md` (`cfdbe1d5…8e80`): the stand-alone and no-market-number rules sit under Replies, and the audit sentence is R4.5(iv)'s. v1.3 succeeded v1.2 (`PAFM_PublicResearchLedger_PreRegistration_v1_2_2026-10-02.md`, `ee58e028…0cf8`). **[v1.3] It makes one change, to §10's X block, with its Rule 15 line in §11.4, under Fable's ruling `Fable_Ruling_LedgerSec10_AReplyIsAPost_…_2026-11-02.md` §2:** a reply is a post under §10; educational replies are permitted under a daily ceiling **N** that the operator signs; the pace within it is set by his dated lines; and every reply stands alone as an explainer that says nothing about the current market. Changes are marked **[v1.3]**; §13 lists them. Every other line is v1.2's. Nothing is live, and nothing has been published.

v1.2 succeeded v1.1 (`379a52f3…0d6`), which Fable's ruling `Fable_Ruling_PAFM_LedgerPageV11Accepted_…_2026-10-02.md` (`654b66b8…c312`) accepted. That ruling confirmed v1.1's 24 clarifications and Q1–Q5 as written, ruled Q6 with three additions, and pre-stated one contingency. v1.2 applied the ruling, marked **[v1.2]**:
- the `NO_FORECAST` reason list (§3, §5);
- the rehearsal's exit rule with the uptime threshold, the provoked failover and race, and the restart rule (§11.3);
- the P3 contingency (§11.2);
- the uptime threshold added to the Rule 15 list (§11.4);
- the scripts' new versions (§7).

v1.0's history stays in the **[v1.1]** marks; §13 lists every version's changes.
**Ruling applied:** v1.2 was "the page with §2 (the reason list), §3 and §4" of ruling `654b66b8` §5. **[v1.3]** v1.3 is v1.2 with §10's X block and §11.4's Rule 15 list changed as `Fable_Ruling_LedgerSec10_…_2026-11-02` §2–§3 rule. It may be frozen once the rehearsal passes and the operator signs §11.4.
**[v1.3] The rehearsal and this page:** the page is the contract the scripts carry, not a hashed script or the constants (§11.3). `page_sha256` is a field of each box's config. Replacing v1.2's hash with this page's is a configuration item, counted under (b), with no restart. The counted rehearsal chain keeps v1.2's hash in its entry 1 and is never merged; the public chain's entry 1 carries this page's hash.
**Once frozen:** this page is frozen by hash **before entry 1**. From then on it changes only by a dated, versioned successor, and **no entry is ever edited or deleted**.
**Governs against:**
- `Fable_Ruling_PAFM_Round3Confirmed_…_2026-10-02.md` (`4cec8435…4dd5`) §7(a)–(d).
- `Fable_Ruling_PAFM_WalkForwardV10Accepted_…_2026-10-02.md` (`bef24279…ceaa`) §4.
- **[v1.3]** `Fable_Ruling_LedgerSec10_AReplyIsAPost_…_2026-11-02.md` §1–§3; `Fable_Ruling_MarketStateWebTrack_Onboarding_R1toR6_2026-10-07.md` R1 amendments 1 and 3, R2, R4 items 2, 4, 5 and 8.
- The program's claim-precision vocabulary.
- The silent-by-construction family: a heartbeat on flow **and** on correctness of flow.

**Owner of product decisions:** the operator. He wants it solid, simple to understand, fully automated, and without room for error.

**What this ledger is, in one sentence:** every 4 hours, before each new BTC 4H candle, a small set of transparent, fixed-formula forecasts is published, timestamped by independent parties and chained so nothing can be edited. Each forecast is then scored in public against what happened, by a script anyone can run.

**What it is not:**
- It is not a tally row and is not a counted attempt (R §7a).
- It contains no model until test 1 is read.
- It contains no buy/sell call.
- Its forecasts are never tuned on the forward data they score.

---

## 1. Fence and exposure (R §7a)

- **Data read:** only Binance USDT-M BTCUSDT perpetual klines from **2026-08-01 00:00 UTC onward** (the *forward window*), plus the frozen constants of §4, which were estimated once on the development window and are filed by hash.
  - Every warm-up and lookback begins at or after 2026-08-01.
  - **The sealed year (2025-08-01 → 2026-07-31) is never read**, by any job or by the verifier.
  - **[v1.1] The fence is enforced in code.** Both data sources in the shared core (the live REST source and the archive source) refuse any request that starts before 2026-08-01, before a request is sent. The self-test runs a fake exchange that records any such request, and records none.
- **Dated line, written at go-live:** *"From 20YY-MM-DD HH:00 UTC the forward window (from 2026-08-01) is ledger-exposed."* PAFM's own forward window (4H_Algo's 90-day deployment read) is defined to begin at **PAFM's go-live**, not at 2026-08-01.
- **Each forward bar is read once, after the forecast that concerns it is committed**, by the scoring job only.
  - The forecast job reads only bars that closed at or before the forecast's commit instant.
  - §6 makes this provable to a stranger.

## 2. The instrument, the bars, the clock

| Field | Value |
|---|---|
| Instrument | Binance USDT-M **BTCUSDT perpetual**: the program's declared proxy and PAFM's training series, so a later model row forecasts the instrument it was tested on. The operator's venue (Delta Exchange BTCUSD) may enter later as an added descriptive row family, by a successor page, never as a substitute |
| Source, live | Binance public REST `/fapi/v1/klines` at `1h` and `1m`; no API key |
| Source, verifier | Binance's public bulk archive (`data.binance.vision`, `futures/um/daily/klines/BTCUSDT/1m`, `1h`). **[v1.1]** Each daily file is checked against its `.CHECKSUM` file before use |
| 4H grid | UTC, opens at 00 / 04 / 08 / 12 / 16 / 20; bar *t* opens at T_t |
| Inputs for bar *t* | every **1h** bar with `close_time ≤ T_t` (the last one closes exactly at T_t), for V-EWMA, the bands and D-BASE. **[v1.1]** Also the **1m** bars of the 7 days before T_t (42 × 240 minutes), for V-HAR's realized-variance lags. v1.0 listed only the 1h bars |
| Target for bar *t* | the **1m** bars with `open_time ∈ [T_t, T_t + 4h)` (240 rows) |

**One input path [v1.1].** The forecast job and the stranger's verifier compute a forecast through the **same function** of the shared core. It is given a data source and a slot, and returns the forecasts and an input census. The verifier therefore recomputes exactly what the job computed, from the other source.

**Correctness of flow:**
- **Cadence census:** every 1h input and every 1m target bar is counted. A missing row is never interpolated.
  - If the hourly census is incomplete, the entry is a `NO_FORECAST`. **[v1.1]** The job first retries up to 6 times, 5 s apart, because the last hour can lag a few seconds at T + 5 s.
  - If only V-HAR's minutes are incomplete, the entry is published, and the V-HAR row alone carries `"status":"NO_FORECAST"`.
  - A target with fewer than 240 minutes is scored, with `minute_count` and `complete:"0"`.
- **The D1 v1.1 flat-line rule runs live [v1.1, made exact]:** a target bar holding a run of **≥ 5 consecutive minutes with volume 0 and O = H = L = C** carries `downtime:"1"`. It is still scored, with the flag on.
- **Two-source check [v1.1, made exact]:** a daily job (06:20 UTC) re-reads from the archive every `FORECAST` and every REST-sourced `SCORE` of the last 8 days whose bar ended at least 30 h earlier. It recomputes them and compares by **value**.
  - The archive prints prices without trailing zeros, so its bytes, and therefore its digests, differ from REST. Digests are compared only between two reads of the same source.
  - Any difference becomes one public `SOURCE_MISMATCH` entry naming the entry, the kind and the differing fields. Nothing is overwritten.
  - v1.0 named only scored bars. Forecast inputs are now checked too.
- **The 1-minute collector:** its state (recorded dead since 2026-07-31) is verified before go-live. The ledger does **not** depend on it; it carries its own fetcher and its own census.
- **Reachability (verified 10-02, curl):** both boxes reach Binance fapi and spot, `data.binance.vision`, the OpenTimestamps pool and GitHub. The TSA endpoints answer. **[v1.1]** A real klines pull, a real two-source comparison and a real RFC 3161 request are items P3–P7 of the pre-flight script (§11).

## 3. Entries and the chain

**Entry kinds [v1.1, the full list], in one append-only log:**
- `FORECAST`.
- `SCORE`, which references a `FORECAST` by hash (`refers_to`).
- Notices:
  - `NO_FORECAST`
  - `NO_SCORE`
  - `LATE`
  - `FAILOVER`
  - `SOURCE_MISMATCH`
  - `PAGE_FROZEN`
  - `DATED_LINE`
  - `GO_LIVE`
  - `CODE_CHANGE` (the announcement of §7)
  - `REHEARSAL_SUMMARY` (rehearsal chain only)

  Each notice is written as its own `kind`.

**Uniqueness rules [v1.1], enforced by the writer and checked by the verifier:**
- one `FORECAST`-or-`NO_FORECAST` per slot;
- at most one `SCORE`, one `NO_SCORE`, one `LATE`, one `FAILOVER` and one `SOURCE_MISMATCH` per referenced entry;
- one `PAGE_FROZEN`, one `DATED_LINE` and one `GO_LIVE` per chain.

**Canonical bytes:**
- UTF-8 JSON with keys sorted and no whitespace.
- **Every number is a decimal string [v1.1: including `seq` and counts; flags are `"0"`/`"1"`]:**
  - forecasts and scores at 10 significant digits (`'.9e'`);
  - prices exactly as the source prints them.

  The canonicaliser refuses any JSON number or boolean, so float formatting can never change a hash.
- The schema is fixed by `schema_version` (`"L1"`).

```
{"schema_version":"L1", "kind":"FORECAST", "seq":"<decimal, +1 per entry, gapless>",
 "prev_hash":"<sha256 of the previous line's bytes>", "row_family":"BENCH-1",
 "slot_utc":"2026-10-20T04:00:00Z", "target_open_utc":"2026-10-20T04:00:00Z",
 "inputs":{"last_1h_close_utc":"…","n_1h":"…","inputs_digest_1h":"<sha256 of the 1h rows as fetched>",
           "n_1m_har":"…","inputs_digest_1m_har":"…","har_inputs_complete":"1","source":"REST"},
 "forecasts":{ … §4 … },
 "code":{"job_sha256":"…","core_sha256":"…","constants_sha256":"…","page_sha256":"…"},
 "writer":"primary|secondary", "created_utc":"<the job's own clock — UNTRUSTED>"}
```

**Time [R2 §4 addition 1]:** `created_utc` is the job's own clock and is labelled **untrusted**. The only time any score or check reads is **τ**, the earliest timestamp token (§6).

**LATE [v1.1].** v1.0 wrote a late entry "with `"late":true`". An entry cannot carry its own τ, because τ is the timestamp of the entry's own hash. So:
- the writer appends a separate `LATE` notice referring to the late `FORECAST`;
- **the binding judgement is the verifier's**, from the tokens;
- a disagreement between the two is listed in the verifier's report.

**`SCORE` entries [R2 §4 addition 3]** carry:
- `target_source` (`REST` or `ARCHIVE`) and `target_digest`;
- `minute_count`, `complete`, `downtime` and `late_score`;
- the target (`R`, `RV`, `up`, `dn`).

**[v1.1]** The scores are computed from the **published 10-digit target**, so anyone can recompute every score from the entry alone. The verifier does this for every `SCORE` before it touches any data.

**`NO_SCORE` [R2 §4 addition 2]:**
- If the scoring job has not scored a bar by its close + 30 min, the watchdog appends `NO_SCORE`.
- **[v1.1]** The REST scoring job then leaves that bar alone. The daily job scores it from the archive (`target_source:"ARCHIVE"`, `late_score:"1"`), with no age limit. It is never scored silently.

**`NO_FORECAST` reasons [v1.2; ruling `654b66b8` §2 Q4].** Every `NO_FORECAST` carries a `reason_code` from a fixed list, so the uptime figure is attributable. A free-text `reason` sits beside it.

| `reason_code` | Meaning | Written by |
|---|---|---|
| `SOURCE_GAP` | the exchange's inputs were incomplete after the retries, or the exchange did not answer | the forecast job (incomplete), or the watchdog from the job's recorded attempt (no answer) |
| `REMOTE_UNREACHABLE` | the git remote (GitHub) could not be read or written | the watchdog, from the job's recorded attempt |
| `JOB_ERROR` | any other failure of the forecast job: a program error | the watchdog, from the job's recorded attempt |
| `WATCHDOG_ONLY` | no forecast attempt is recorded for the slot on the writing box (the job did not run: a box down, a timer, or a start after T + 9 min) | the watchdog |

- How the cause is known: each forecast attempt records its outcome on its own box (`state/attempts/<slot>.json`), and the watchdog reads that record.
- The verifier fails any `NO_FORECAST` without a listed code.
- The scorecard's uptime counts `NO_FORECAST`s by code.

**The chain:**
- `entry_hash = sha256(line bytes)`.
- Each entry carries `prev_hash`, and `seq` is gapless. **Deleting or editing any entry breaks every hash after it**, and the verifier reports the first break.
- **[v1.1] Repository layout** (v1.0 proposed monthly files; one file is simpler and the CI rule is simpler):

  | Path | Contents |
  |---|---|
  | `ledger.jsonl` | the chain, one file |
  | `proofs/<seq>.entry` | the entry's exact bytes |
  | `proofs/<seq>.tsa<i>.tsr` | the timestamp tokens |
  | `proofs/<seq>.entry.ots` | the OpenTimestamps proof |
  | `proofs/tsa_certs/` | the TSAs' certificates |
  | `page/` | this frozen page |
  | `constants/` | the frozen V-HAR constants |
  | `code/` | every script that writes or checks an entry |

- **[v1.1] What GitHub can and cannot enforce.** v1.0 said "a required CI check rejects any commit that modifies or removes an existing line". GitHub's required checks gate pull-request merges, not direct pushes, and the boxes push directly. The protections are therefore:
  1. On the main branch, force-push and deletion are blocked.
  2. Write access is held only by the two boxes' deploy keys.
  3. A CI run on **every push** applies the append-only rule in public:
     - `ledger.jsonl` may only grow by whole lines;
     - no `.entry`, `.tsr`, constants, page or code file may change or disappear;
     - `.ots` files may be upgraded.

     A violation shows as a failed run, in public.
  4. Above all, the chain plus third-party tokens make any edit detectable by anyone, whatever GitHub does. The self-test shows this: a single changed byte, a fully re-hashed chain, a moved token and a substituted CA certificate all fail verification.

## 4. The rows: benchmarks only, fixed formulas, declared parameters

Every row family is versioned. **A change to any formula or constant is a new row family (`BENCH-2`, …) that starts its own record. It is never an edit** (R §7b).

**Notation:**
- r_k: the hourly log returns, the first taken from the first bar's open.
- R: the 4H log return, ln(C_close / O_open) over [T, T + 4h).
- RV: Σ of the 240 squared 1-minute log returns in [T, T + 4h), the first taken from the first minute's open.
- h = 4 hours.

| Row | Forecast | Definition (parameters frozen) |
|---|---|---|
| **V-EWMA** | 4H variance σ²_f | 4 × EWMA of r_k², half-life **24 h**; seeded with r_1² at the first hourly bar ≥ 2026-08-01 |
| **V-HAR** | 4H variance σ²_f | log-HAR (Corsi): ln RV_4h on x₁ = ln RV of the last 4H, x₂ = ln of the mean RV of the last 6 4H bars (1 d), x₃ = ln of the mean RV of the last 42 (7 d). Coefficients b₀…b₃ and the residual variance s² estimated once on the development window's 1-minute data and frozen by hash (`constants_sha256`). **[v1.1] Map: σ²_f = exp(b₀ + b·x + s²/2)**, the lognormal mean of the fitted log-RV, so σ²_f is a forecast of the variance and not of its median |
| **B-RET80** | 80% interval for R | ±1.2816 σ_f (V-EWMA), centred at 0 |
| **B-EXC80** | 80% bounds for the up and down excursions | up: ln(H / O) ≤ 1.2816 σ_f; down: ln(O / L) ≤ 1.2816 σ_f (reflection principle for a driftless Brownian path, V-EWMA's σ_f) |
| **D-HALF** | P(up) | 0.5, constant |
| **D-BASE** | P(up) | (ups + 0.5) / (ups + downs + 1): the up-rate of 4H closes from 2026-08-01 to T_t with a 0.5 prior weight of 1 bar. **[v1.1]** A bar with C = O counts as neither |

**V-HAR's estimation [R2 §4, L3]:**
- The estimation script `ledger_har_estimate_v1_2026-10-02.py` (`8148afc8…91fa`, self-test PASS) runs once on the primary box. It reads the development window's 1-minute files by hash, refuses the sealed year, and writes `ledger_har_constants_v1.json`, write-once.
- The output's hash is filed before entry 1.

**Scoring rules, each with its denominator** (R §7b):

| Row | Primary score | Beside |
|---|---|---|
| V-EWMA, V-HAR | **log-score of R under N(0, σ²_f)** | QLIKE of RV vs σ²_f; MSE of ln RV vs ln σ²_f; Mincer–Zarnowitz slope of ln RV on ln σ²_f |
| B-RET80, B-EXC80 | **coverage** (target 0.80) with its binomial 95% CI | mean width; the excursion pair scored separately |
| D-HALF, D-BASE | **log-loss** | Brier; hit rate. **D-BASE is the reference row any direction row is read against** |

**[v1.1] Ties and flags:**
- A bar with **R = 0** is a TIE for the direction rows: it is not scored for them, and it is counted.
- The hit rate leaves out a probability of exactly 0.5, so D-HALF has no hit rate.
- The **primary block** of the scorecard leaves out:
  - every `LATE` forecast (scored **beside**, in its own block);
  - every bar flagged `complete:"0"` or `downtime:"1"`, counted as *flags excluded (k)*.

**Every published score states:** *N scored bars / N scheduled bars, window [first, last], flags excluded (k).* The scorecard (`scorecard.json`, written by the verifier) carries:
- each number with its `n`;
- each block with its window;
- **uptime**: scheduled, published, on time, `NO_FORECAST` (with **[v1.2]** a count per `reason_code`), `LATE`, and single-token entries.

**Running scores are recomputed from the full log every day. Nothing is a stored running total.**

**Why these rows:** they are the yardstick PAFM must later beat in public, and anyone can recompute them by hand. They also give the record a working, gapless history from day one.

## 5. The schedule and NO_FORECAST

| Instant (UTC) | Action |
|---|---|
| T − 10 min | **[v1.1] pre-flight inside the watchdog:** clock offset against the exchange's server time (< 1 s), disk (≥ 1 GiB), both TSAs (a real request on a test digest). Alerts only; it writes nothing |
| T + 5 s | the forecast job: fetch inputs; census (≤ 6 tries); compute; canonicalise; hash; request timestamps (§6); append; push. **[v1.1]** The job refuses to start after T + 9 min; that slot then belongs to the watchdog |
| T + 60 s | the secondary's forecast job (started at T + 5 s, waiting) writes only if no entry for T exists (§8) |
| **T + 120 s (L_max)** | **the commit deadline.** A `FORECAST` whose earliest token is later than T + 120 s, or which has no token, is LATE: a `LATE` notice is appended, and the forecast is excluded from every primary score and scored beside |
| T + 10 min | the scoring job scores every bar that closed ≥ 10 min ago (the bar that just closed) and appends a `SCORE` |
| T + 10 min | if no entry exists for T, the watchdog (every 5 min, at :x0:30 and :x5:30) appends `NO_FORECAST` for **every** slot since go-live that lacks one, with its `reason_code` (§3). **Nothing is ever back-filled** |
| close + 30 min | if a bar is still unscored, the watchdog appends `NO_SCORE` (§3) |
| daily 06:20 | the archive cross-check (§2); `SOURCE_MISMATCH` if any; archive scores after a `NO_SCORE`; OpenTimestamps upgrades |
| daily 07:40 | GitHub Actions runs the full verifier from the archive (public run log; the scorecard as a run artifact) |

**The uptime figure** (scheduled vs published on time) is itself a published score.

**[v1.1] Declared limitation.** If GitHub is unreachable at T, no entry can be published. The forecast is not held and pushed later. The slot becomes a `NO_FORECAST` (`REMOTE_UNREACHABLE`) when the watchdog can next write, and is never back-filled (ruling `654b66b8` Q4).

## 6. Commit-before-observe, provable by a stranger (R §7b)

A daily Merkle root proves the day, not the 4H forecast. **Per entry**, three independent proofs:

1. **RFC 3161 timestamps from Time-Stamp Authorities the operator does not control.** Two are requested **in parallel** on `entry_hash` at commit. **τ is the earliest token.** [R2 §4, L4]
   - **[v1.1] Token files:**
     - `proofs/<seq>.tsa1.tsr` — DigiCert (`timestamp.digicert.com`);
     - `proofs/<seq>.tsa2.tsr` — Sectigo (`timestamp.sectigo.com`);
     - `proofs/<seq>.tsa3.tsr` — FreeTSA (`freetsa.org/tsr`), requested **only when fewer than two of the first pair answer**.
   - Each token is a signed statement by a third party: "this hash existed at time τ".
   - **[v1.1] Certificates.** The TSAs' certificate chains are stored in the repository (`proofs/tsa_certs/`). They are built by the pre-flight script from each TSA's own token plus the box's system trust store (completed up to a self-signed root), checked by verifying a real token against them, and filed by hash.
   - The verifier checks each token with `openssl ts -verify`: its `messageImprint` must equal `entry_hash`, and its signature must chain to the stored certificates.
   - **[v1.2] Checked at write time too.** The writing job verifies each new token against the same stored certificates at once. A token that fails (a TSA has changed its signing certificate) raises an alert within seconds, rather than first showing in CI.
     - The new chain is then added to `proofs/tsa_certs/` as a **new** file, by hash; existing files never change.
     - The pre-flight's chain builder handles a token that carries a cross-signed copy of its root (DigiCert does this; pre-flight v1.1, found in Phase A).
   - **Primary scoring requires τ ≤ T + 120 s.** **[v1.1]** Normally two tokens are present. One verified token is enough for τ; entries with a single token are listed in the verifier's report. This is v1.0's "single-TSA outage: one token plus the OTS proof, marked".
2. **OpenTimestamps** submission of each entry's bytes (`ots stamp`; a calendar receipt at once). **[v1.1]** The daily job runs `ots upgrade` until the proof carries its Bitcoin attestation. An upgrade changes the `.ots` proof file only, never an entry or a hash. This is the long-horizon proof if a TSA ever disappears.
3. **For the benchmark rows, recomputation:** the forecasts are deterministic functions of public data that closed at or before T. The verifier recomputes every one from the archive.
   - **[v1.1] Tolerance:** the decimal strings must be identical, or within one unit of the 10th significant digit. The primary box is ARM (aarch64) and the CI runner is x86, and their math libraries may round a last digit differently. Every such case is counted and listed. In the self-test (v1.2) all 586 compared values were exact. In Phase A the ARM box and the x86 box produced character-identical forecasts for the same live slot.

**How a stranger checks entry N, written on the website:**
1. Download the repo.
2. Recompute `sha256` of line N and verify the chain to N.
3. `openssl ts -verify` the tokens against the stored certificates, giving τ.
4. Check τ ≤ T + 120 s.
5. For a benchmark row, recompute the forecast from Binance's archive.
6. Recompute the score.

A script in the repo does all six: `python3 code/ledger_verify_v1_1_2026-10-02.py --repo .`

**For any future model row** (§9), where the weights are not public, (1) and (2) are the proof, and **the model row's PRIMARY score is the post-commit target** [R2 §4, L1 amended]: R and RV measured from the first full minute after τ to the bar's close. The full-bar score from T_t is beside it. The ledger's primary claim is therefore free of the ≤ 120 s latency, and a user acting on the forecast lives in the post-commit bar anyway. **Benchmark rows** keep the full bar from T_t as primary: they are deterministic in data closed at T_t, so the latency cannot help them.

## 7. The scripts, by hash [v1.1: the actual files; v1.2: the versions after ruling `654b66b8`]

v1.0 listed three job scripts by role. They are implemented as one jobs script with modes, on one shared core:

| Script | Role | Runs |
|---|---|---|
| `ledger_core_v1_2026-10-02.py` | canonical bytes, the chain, the two sources and the fence, the formulas, the target and flags, the scores, the TSA calls | imported by the jobs, the verifier and the pre-flight |
| `ledger_jobs_v1_1_2026-10-02.py` **[v1.2]** | `--forecast`, `--score`, `--watchdog` (with the pre-flight), `--crosscheck` (with OTS upgrades), `--notice` | on both boxes, systemd timers |
| `ledger_verify_v1_1_2026-10-02.py` **[v1.2]** | the chain, the proofs, τ, the rules, the recomputation, the scorecard; `--append-only` for CI — **the stranger's script** | GitHub Actions on every push (no recomputation) and daily (full), and anyone, any time |
| `ledger_claims_check_v1_2026-10-02.py` | rejects any draft post that breaks §10 | before every X post |
| `ledger_har_estimate_v1_2026-10-02.py` | V-HAR's constants, once | once, on the primary box |
| `ledger_preflight_v1_2_2026-10-02.py` **[v1.2]** | the pre-flight items P1–P11 (§11), and the TSA certificate files | once per box before the rehearsal, and again before go-live |
| `ledger_repo_init_v1_1_2026-10-02.py` **[v1.2]** | lays out a repository (no entries) | once for the rehearsal repository, once for the public one |

- Every script, the frozen constants file and the TSA certificate files are filed by hash in both libraries **before entry 1**.
- `job_sha256` and `core_sha256` in every entry name the code that wrote it. The verifier requires that code to be present in `code/`.
- A code change is a new version, announced by a `CODE_CHANGE` notice before it writes.
- **[v1.2] What changed in the new versions:**
  - jobs v1.1: the `NO_FORECAST` reason codes and attempt records; the write-time token check; the rehearsal-only drill hold. The drill is refused unless the config says `"rehearsal": true`.
  - verify v1.1: the reason-code rule; uptime by reason and the single-token count on the scorecard.
  - pre-flight v1.2: the cross-signed-root case (v1.1); a fresh OpenTimestamps test file on every run.
  - repo-init v1.1: the new file names.
  - core, claims check and HAR estimator: unchanged.
- **The self-test** (`test_ledger_v1_2_2026-10-02.py` **[v1.2]**) runs everything offline against constructed data (seed 990501):
  - fakes: a fake exchange (REST and archive), three fake TSAs signing real RFC 3161 tokens, a fake OpenTimestamps command, a local git remote, and a controllable clock;
  - scenarios: failover, a lost push race, retries and `NO_FORECAST`, `NO_SCORE` and the archive late score, `LATE`, a TSA outage, the downtime flag, a source mismatch, the pre-flight, tampering, the CI rule and the claims check;
  - **[v1.2]** also: each `reason_code` produced by its real cause (the git remote removed during a forecast; a program error); the provoked lost-push race through the drill hold, and the drill refused outside a rehearsal; a token from an unknown chain alerting at write time; a `NO_FORECAST` without a code failing verification; DigiCert's cross-signed root;
  - result: **65/65 PASS** (v1: 59/59).

## 8. Failover: what the second box may and may not write

- **Primary:** the New box (`btc-bot-new`). **Secondary:** the old box, which runs the same jobs in shadow.
- The secondary appends **only if** no entry for T exists at T + 60 s. It writes `"writer":"secondary"` and pushes a fast-forward on the same chain.
- **[v1.1] Before every write, each box re-reads the remote head and re-applies the uniqueness rule (§3).** If a push loses the race, the box discards its local entry and re-reads the head. So there is **one chain, never a fork** (tested: the loser leaves no entry and no stray proof file).
- For benchmark rows both boxes compute identical forecasts. The verifier recomputes every forecast, whoever wrote it.
- **The secondary never writes a SCORE for a forecast the primary wrote** (the verifier checks this), and never edits anything. **[v1.1]** It scores the forecasts it wrote itself; the primary may score those too, whichever comes first.
- A `FAILOVER` notice records each use.
- **[v1.1] Wrong-box rule:** each box's config names its host; a job on any other host alerts and writes nothing.

## 9. The period of benchmarks only, and PAFM's row (R §7a, §7c)

- **Benchmarks only at least until walk-forward test 1 is read.**
- PAFM's row family (`MODEL-PAFM-<config hash>`) enters only by a dated successor page, on R §7c's conditions:
  - after test 1 is read;
  - the exact tested object, frozen as certified, or labelled *not certified*;
  - trained on the development window only until the sealed read;
  - its 6-month retraining cadence declared on the row;
  - labelled **"untested display"** until a pre-registered forward window reads it;
  - its primary score is the post-commit target (§6);
  - a variance or band row from the model's shape heads only under Roadmap C2's certificate.

## 10. What may be said in public (R §7d, carried verbatim into the repo's README)

**Before any real-data verdict:**
- Say "research in progress".
- The rows are "transparent benchmarks".
- Every synthetic result carries the word *synthetic* in its sentence.
- Do not use "edge", "beats", "predicts" or "signal".

**After a null:** publish the cell name, N and the window, the same day it is filed.

**After certification:** use the certification sentence of R §7d. Never say "profitable". Make no forward claim until the forward window is read.

**Always:**
- Every number carries its denominator and window.
- Nothing is promoted up the descriptive → candidate → finding ladder in public before it is on a filed page.

**The README also carries [R2 §4 addition 5]:** *"The benchmark rows are a yardstick, not forecasts anyone should trade."*

**X:** **[v1.3]** a reply is a post under this section.
- **Originals:** one educational post a day at most.
- **[v1.3] Replies:** educational replies, **at most N a day**, where **N is a Rule 15 number signed by the operator's dated line (§11.4)**. **The pace within the ceiling** is set by the operator's dated lines. Engagement analytics are an input to the pace (cadence is timing), never to a word, a number, a claim or a target chosen for the conclusion it would let the program imply. Topic and target selection by demand is permitted; conclusion selection is refused.
- **Every original and every reply:**
  - an agent drafts it; the operator approves it;
  - `ledger_claims_check` must pass, and **[v1.3]** so must the content line's second claims check;
  - never a forecast and never a call.
- **[v1.3.1] Every reply, in addition:**
  - **no number from the market;**
  - **it stands alone as an explainer and says nothing about the current market.** Read without its parent, a reply is a definition or a mechanism explained. It does not describe, characterise or react to today's price, funding, open interest or move. The parent's content is the parent's; the reply's is the program's.
- **[v1.3] Replies are their own template class** for their first eight weeks (R4.5): one-tap approval by the operator; an audit of at least 10 % of approved replies and never fewer than five. **[v1.3.1] One failure found in audit restarts the class's eight weeks of one-tap approval and is entered in the public corrections log.**

**[v1.1] What the claims check enforces, mechanically:**
- **Numbers.** Every number in a draft must be one of:
  - a value in the current `scorecard.json`, at the precision shown, with its `n` in the same sentence and its window's dates in the post. **Only a rate (a coverage or a hit rate) may be written as a percentage.**
  - a declared constant: 24, 80%, 0.80, 0.5, 1.2816, 120, 240, 42;
  - a date or a time of day.

  Other counts are written in words, so "3%" can never pass as a constant.
- **Words before a verdict:** "edge", "beat(s)", "predict(s/ion)" and "signal(s)" are rejected, in every inflection.
- **Words always rejected:** "profit(able)", "guarantee(d)", "buy", "sell", "go long", "go short", "take-profit", "stop-loss", "entry price", "target price", "price target", "moon", "100x" and "alpha".
- **Synthetic results:** a sentence that mentions a backtest, a simulation or a test set must carry "synthetic".

## 11. Before go-live (the burn-in), and the go-live entry

1. Scripts, constants and this page are filed by hash. Fable reads this page.
2. **[v1.1] Pre-flight**, on each box (`ledger_preflight_v1`). The items:
   - host;
   - clock;
   - **P3, the full hourly census since 2026-08-01**. If a single historical hour is missing, every forecast would be `NO_FORECAST`, because nothing is interpolated. **[v1.2] Contingency (ruling `654b66b8` §4):**
     - if P3 finds a gap, the lookback origin moves to the first complete hour after the last gap;
     - the move is declared by the `DATED_LINE` before entry 1, with the gap listed;
     - fence (D) and the formulas are unchanged; only their seed date moves.

     **Phase A result: no gap**, 1,504 of 1,504 hours on both boxes (`PAFM_Ledger_PhaseA_Results_2026-10-02.md`). The P3 check is repeated before go-live;
   - the 7-day minute census;
   - a timed live forecast;
   - a full archived day compared with REST, value by value;
   - each TSA: latency, genTime against the local clock, the chain built and verified;
   - `ots stamp`;
   - the git remote;
   - a Telegram test message;
   - disk.

   The V-HAR estimation runs on the primary box (§4).
3. **Rehearsal [R2 §4, L6]:** 14 days of the full machinery writing to a **private** repository, on a **separate chain that is never merged** into the public one. Every failure is counted and fixed, and the counts are disclosed in the go-live notice. Rehearsal entries are never presented as record.

   **[v1.2] The exit rule (ruling `654b66b8` §3).** The rehearsal passes only when, over 14 consecutive days:
   - (a) the daily full verification from the archive passes every day;
   - (b) every failure is counted, with its cause and fix filed;
   - (c) no unexplained `SOURCE_MISMATCH` remains;
   - (d) **≥ 95 % of scheduled slots are published on time (≥ 80 of 84)**. Source-caused gaps count against uptime and are reported by `reason_code`;
   - (e) **no program-caused failure in the final 7 days**: a job error, a wrong-box run, or a lost race leaving a stray;
   - (f) **one failover is exercised on purpose**: the primary's forecast timer is stopped for one scheduled slot, and the secondary must write that slot with its `FAILOVER` notice;
   - (g) **one lost-push race is provoked on purpose** with the drill hold: the rehearsal config names one slot, and the primary holds that slot's push long enough for the secondary to write first. The primary must lose and leave nothing behind.

   The `REHEARSAL_SUMMARY` notice names both drill slots.

   **The restart rule:**
   - A change to any **hashed script or the constants** restarts the 14 days on a fresh chain.
   - A change to configuration or infrastructure that alters no hashed file (a timer, a key, a path, a host name) is counted and filed, and does not restart the clock.
   - The `REHEARSAL_SUMMARY` carries both lists.

   **An uncounted shakedown** on its own chain may run first. It is never counted, and the counted 14 days begin on a fresh chain.
4. The operator signs: the instrument and sources; the rows and their constants; the failover rule; the claims rule; and **the Rule 15 items [R2 §4 addition 4], chosen numbers named as such:**
   - the EWMA half-life of **24 h**;
   - D-BASE's prior weight of **1 bar** at 0.5;
   - the 80% band quantile **1.2816**;
   - **L_max 120 s**;
   - **the TSAs** (DigiCert and Sectigo; FreeTSA in reserve);
   - **the go-live date** (the dated line of §1);
   - **[v1.2] the uptime threshold** of the rehearsal's exit rule: **≥ 95 % of scheduled slots on time (≥ 80 of 84), and no program-caused failure in the final 7 days**;
   - **[v1.3] the reply ceiling N** of §10: the most educational replies on X in one UTC day. The pace within it is the operator's by dated line.
5. **Entry 1** is `PAGE_FROZEN`, carrying this page's SHA-256 (the page file sits in `page/`; the verifier checks it). **Entry 2** is `DATED_LINE` (the exposure line of §1). Forecasts begin at the next 4H open. **[v1.1]** The public repository is laid out fresh by `ledger_repo_init` at go-live; nothing from the rehearsal repository is copied into it except the code, the constants, this page and the certificate files, all by hash.

## 12. Rulings applied (R2 §4)

| # | Ruling |
|---|---|
| L1 | Benchmark rows: the full bar from T_t, committed within L_max 120 s. **Model rows: the post-commit target is primary**, the full bar beside |
| L2 | Σ of 240 one-minute squared returns, with the `minute_count` flag |
| L3 | HAR coefficients estimated once on the development window and frozen by hash; the script and window filed; never the sealed year |
| L4 | Two RFC 3161 TSAs requested in parallel, τ the earlier token, `messageImprint` and the certificate chain checked, certificates in the repo; plus OpenTimestamps and recomputation |
| L5 | Log-score of R under N(0, σ²_f) primary; QLIKE, MSE-of-log and Mincer–Zarnowitz beside |
| L6 | 14 days private, on a separate chain never merged; the failure counts in the go-live notice |
| **[v1.3] X1** | A reply is a post under §10. Replies under a ceiling N (Rule 15); pace by the operator's dated lines, analytics an input to pace only; every reply a stand-alone explainer with no number from the market and nothing about the current market; both claims checks; a template class for eight weeks (`Fable_Ruling_LedgerSec10_…_2026-11-02` §1–§2) |

**Additions:** (1) `created_utc` untrusted, τ the only time read; (2) `NO_SCORE`; (3) target digest and source on every `SCORE`; (4) the Rule 15 list of §11.4; (5) the README sentence of §10.

**Sequence (ruling `654b66b8` §5):** page v1.2 → filed by hash with the scripts and constants → Phase A pre-flight on both boxes (done: no P3 gap) and the one-time V-HAR estimation (done: `5a112c0b…fe6a`) → Phase B, the private rehearsal under §11.3 → the `REHEARSAL_SUMMARY` to Fable with the counts → the operator signs §11.4 with the uptime numbers → entry 1 (`PAGE_FROZEN`). Nothing is published before entry 1.

**[v1.3] Sequence for this version:** page v1.3 → filed by hash → one Fable read → the operator's dated line for N → `page_sha256` updated in both boxes' config, counted under (b) on the `REHEARSAL_SUMMARY` → replies begin at the pace his line sets. Until the read and the line: originals one a day; replies held.

## 13. What v1.3, v1.2 and v1.1 change

**v1.3.1** applies `Fable_Ruling_LedgerPageV13Read_…_2026-11-02` (`cfdbe1d5…8e80`): the stand-alone and no-market-number bullets moved under Replies (originals keep §10's existing rules); the audit sentence made R4.5(iv)'s.

**v1.3** applies `Fable_Ruling_LedgerSec10_…_2026-11-02`, with no open question:
- §10, X: a reply is a post; originals one a day; replies at most N a day, the pace by the operator's dated lines; every reply a stand-alone explainer, with no number from the market and nothing about the current market; both claims checks; the eight-week template class;
- §11.4: the reply ceiling N as a Rule 15 item;
- §12: row X1 and the v1.3 sequence;
- the status block: v1.3's line, the configuration note on `page_sha256`, and the governing ruling.

**Nothing else moved.**

**v1.2** applies ruling `654b66b8`, with no open question:
- the `NO_FORECAST` reason list (§3, §5);
- the write-time token check (§6);
- the scripts' new versions and the 65-check self-test (§7);
- the P3 contingency and the Phase A result (§11.2);
- the rehearsal's exit rule, the drills and the restart rule (§11.3);
- the uptime threshold as a Rule 15 item (§11.4).

Q1–Q5 below were confirmed as written by that ruling; Q6 was ruled with the additions now in §11.3.

### v1.1

**Clarifications (implementation made exact; no v1.0 rule reversed):**

| # | Where | Change |
|---|---|---|
| 1 | §1 | the fence enforced in code |
| 2 | §2 | V-HAR's inputs: the 1m bars of 7 days, not only 1h |
| 3 | §2 | one input path for the job and the verifier |
| 4 | §2 | the flat-line rule exactly |
| 5 | §2 | the two-source check daily, on forecasts and scores, by value |
| 6 | §2 | the last-hour retry |
| 7 | §3 | the full kind list and the uniqueness rules |
| 8 | §3 | every number a decimal string, including `seq` |
| 9 | §3 | `LATE` as a separate notice, the verifier's τ binding |
| 10 | §3 | scores computed from the published target |
| 11 | §3 | `NO_SCORE` bars scored from the archive, with no age limit |
| 12 | §3 | one `ledger.jsonl` and the proofs layout |
| 13 | §4 | the HAR map exp(b·x + s²/2) |
| 14 | §4 | D-BASE ties |
| 15 | §4 | R = 0 is a TIE |
| 16 | §4 | the scorecard's contents |
| 17 | §5 | the timers; the pre-flight inside the watchdog; the forecast job's T + 9 min refusal |
| 18 | §6 | token file names; the reserve requested only on need; how the certificates are built |
| 19 | §6 | OTS upgrades |
| 20 | §6 | the last-digit tolerance (ARM vs x86) |
| 21 | §7 | the actual scripts |
| 22 | §8 | re-check after every sync; the secondary scores its own forecasts; the wrong-box rule |
| 23 | §10 | the claims check's mechanics |
| 24 | §11 | the pre-flight items, P3 above all |

**Asked of Fable (each is my reading, recommended as written):**
- **Q1.** The primary block leaves out flagged bars (`complete:"0"`, `downtime:"1"`) and counts them. v1.0 said such bars are "scored with the flag on" and that scores state "flags excluded (k)". Confirm.
- **Q2.** One verified token suffices for τ, with single-token entries listed (v1.0's single-TSA-outage parenthesis). Confirm. The alternative is to require two tokens for the primary block.
- **Q3.** GitHub cannot reject a direct push. Accept the protection set of §3: no force-push or deletion; deploy keys only; a public CI append-only check on every push; tamper-evidence from the chain and the tokens.
- **Q4.** A GitHub outage at T yields `NO_FORECAST`, with no hold-and-push-later path. A later push would rest on the tokens alone, and the simpler rule leaves nothing to argue. Accept.
- **Q5.** `LATE` as a separate notice, with the verifier's τ binding (an entry cannot carry its own τ). Accept.
