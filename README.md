# CS 536 — Data Communication and Computer Networks

**Arpita Saha · Baris Sarper Tezcan · Anusha Sarraf · Shafiq-us Saleheen · Manmeet Singh Dang**

---

## Repository Structure

```
CS536/
├── HW1/                         # Assignment 1 — Network Measurement
├── hw2/                         # Assignment 2 — iPerf Throughput & TCP Stats
│   ├── iperf3_client.py         # From-scratch iperf3 protocol client
│   ├── plot_tcp_stats.py        # Per-algorithm TCP stats visualization
│   ├── plot_comparison.py       # Multi-algorithm comparison plots (45 s ablation)
│   ├── plot_comparison_10s.py   # Multi-run comparison plots (10 s)
│   ├── ML_model.py              # Ridge regression cwnd predictor
│   ├── run_experiment.sh        # One-shot experiment runner
│   ├── Dockerfile               # Containerized environment (Ubuntu 24.04)
│   ├── servers.txt              # Public iperf3 server list
│   └── results/
│       ├── 10s/                 # 10-second runs
│       │   ├── reno_baseline/
│       │   ├── cubic_baseline/
│       │   ├── mycc_all_1/      # mycc run 1
│       │   ├── mycc_all_2/      # mycc run 2
│       │   └── mycc_all_3/      # mycc run 3
│       ├── 45s/                 # 45-second ablation runs
│       │   ├── reno_baseline/
│       │   ├── cubic_baseline/
│       │   ├── mycc_loss_hold/          # Rule 1 only
│       │   ├── mycc_loss_hold_severe/   # Rules 1+2
│       │   ├── mycc_loss_hold_severe_mild/ # Rules 1+2+3
│       │   └── mycc_all/               # All 4 rules
│       ├── comparison_10s/      # Plots: 10 s reno vs cubic vs mycc_all
│       ├── comparison_r1/       # Plots: 45 s — reno, cubic, mycc_R1
│       ├── comparison_r2/       # Plots: 45 s — + mycc_R1+R2
│       ├── comparison_r3/       # Plots: 45 s — + mycc_R1+R2+R3
│       └── comparison_all/      # Plots: 45 s — all 6 variants
└── hw3/                         # Assignment 3 — Linux Kernel Module
    ├── tcp_mycc.c               # Custom TCP congestion control module
    └── Makefile                 # Kernel module build configuration
```

---

## Assignment 2 — iPerf Throughput & TCP Stats

### Overview

A from-scratch Python TCP client that implements the **iperf3 wire protocol**, connects to public iperf3 servers, measures goodput using `TCP_INFO`, extracts TCP statistics, and generates all required plots.

### Files

| File | Purpose |
|------|---------|
| `iperf3_client.py` | iperf3 protocol, goodput measurement, Q1 plots |
| `plot_tcp_stats.py` | Q2 — per-algorithm time-series and scatter plots |
| `plot_comparison.py` | 45 s ablation comparison across multiple algorithms |
| `plot_comparison_10s.py` | 10 s multi-run comparison (mycc_all × 3 runs) |
| `ML_model.py` | Ridge regression model for cwnd prediction (Q3) |
| `run_experiment.sh` | One-shot runner for all experiments |
| `Dockerfile` | Ubuntu 24.04 container with Python 3, matplotlib, numpy |
| `servers.txt` | 61 public iperf3 servers across Africa, Asia, and Europe |

### How to Run

#### With Docker (recommended)

```bash
cd hw2

# Build
docker build -t cs536-hw2 .

# Run with defaults (n=10, duration=20s, interval=1s, cc=system default)
docker run --rm -v $(pwd)/results:/app/results cs536-hw2

# Run with a specific congestion control algorithm
docker run --rm -v $(pwd)/results:/app/results cs536-hw2 \
  --n 10 --duration 45 --interval 1 --cc mycc
```

#### Directly (Linux with Python 3.10+, real kernel required for TCP_INFO)

```bash
cd hw2

# Full experiment — Q1 + Q2 plots generated automatically
python3 iperf3_client.py --servers servers.txt --n 10 --duration 20 --interval 1

# With a specific congestion control algorithm
python3 iperf3_client.py --servers servers.txt --n 10 --duration 45 --interval 1 --cc mycc

# Generate Q2 per-algorithm plots separately
python3 plot_tcp_stats.py --csv results/45s/mycc_all/q2_goodput_samples.csv

# Specify a particular server for Q2 plots
python3 plot_tcp_stats.py \
  --csv results/45s/mycc_all/q2_goodput_samples.csv \
  --server "lg.vie.alwyzon.net:5203"
```

### Command-Line Arguments

#### `iperf3_client.py`

| Argument | Default | Description |
|----------|---------|-------------|
| `--n` | 10 | Number of servers to test |
| `--duration` | 20 | Test duration per server (seconds) |
| `--interval` | 1.0 | Goodput sampling interval (seconds) |
| `--servers` | built-in | Path to server list file |
| `--outdir` | `results/results_YYYYMMDD_HHMMSS/` | Output directory |
| `--cc` | system default | TCP congestion control (e.g. `cubic`, `reno`, `mycc`) |

#### `plot_comparison.py` — 45 s ablation

```bash
python3 plot_comparison.py \
    --datasets "reno:results/45s/reno_baseline/q2_goodput_samples.csv" \
               "cubic:results/45s/cubic_baseline/q2_goodput_samples.csv" \
               "mycc_R1:results/45s/mycc_loss_hold/q2_goodput_samples.csv" \
               "mycc_R1+R2:results/45s/mycc_loss_hold_severe/q2_goodput_samples.csv" \
               "mycc_R1+R2+R3:results/45s/mycc_loss_hold_severe_mild/q2_goodput_samples.csv" \
               "mycc_all:results/45s/mycc_all/q2_goodput_samples.csv" \
    --outdir results/comparison_all \
    --bin 2.0
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--datasets` | required | One or more `label:path` pairs |
| `--outdir` | `results/comparison` | Output directory |
| `--bin` | 2.0 | Time-bin width in seconds for time-series aggregation |

#### `plot_comparison_10s.py` — 10 s multi-run

```bash
python3 plot_comparison_10s.py \
    --base results/10s \
    --outdir results/comparison_10s
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--base` | `results/10s` | Root directory containing 10 s run folders |
| `--outdir` | `results/comparison_10s` | Output directory |

### Output Files

Each run directory contains:

| File | Description |
|------|-------------|
| `q2_goodput_samples.csv` | All samples with TCP stats (see schema below) |
| `q1_goodput_timeseries.pdf` | Goodput (Mbps) vs time, all destinations overlaid |
| `q1_goodput_summary_table.pdf` | Min / median / avg / P95 / max per destination |
| `q2_timeseries.pdf` | 4-panel time series: cwnd, RTT, retransmits, goodput |
| `q2_scatter_cwnd_goodput.pdf` | Scatter: congestion window vs goodput |
| `q2_scatter_rtt_goodput.pdf` | Scatter: RTT vs goodput |
| `q2_scatter_loss_goodput.pdf` | Scatter: total retransmissions vs goodput |

Each comparison directory contains:

| File | Description |
|------|-------------|
| `comparison_timeseries.pdf` | Overlaid time-series (goodput, RTT, cwnd, retransmits) |
| `comparison_summary_bars.pdf` | Bar chart: mean/median/P95 goodput, RTT, retransmits |
| `comparison_goodput_cdf.pdf` | CDF of per-sample goodput |
| `comparison_rtt_cdf.pdf` | CDF of per-sample RTT |

### CSV Schema

```
server, timestamp, elapsed_s, goodput_bps, goodput_mbps, bytes_acked,
snd_cwnd, rtt_us, rtt_ms, rttvar_us, retransmits, total_retrans,
lost, pacing_rate, delivery_rate, snd_ssthresh, cc_algo
```

### iperf3 Protocol State Machine

```
Client                          Server
  |--- TCP connect (ctrl) ------->|
  |--- 37-byte cookie ----------->|
  |<-- PARAM_EXCHANGE (9) --------|
  |--- JSON params -------------->|  {"tcp":1, "time":D, "parallel":1, ...}
  |<-- CREATE_STREAMS (10) -------|
  |--- TCP connect (data) ------->|  (second connection, same cookie)
  |<-- TEST_START (1) ------------|
  |<-- TEST_RUNNING (2) ----------|
  |=== SEND DATA ================>|  (bulk TCP for `duration` seconds)
  |--- TEST_END (4) ------------->|
  |<-- EXCHANGE_RESULTS (13) -----|
  |--- JSON our results --------->|
  |<-- JSON server results -------|
  |<-- DISPLAY_RESULTS (14) ------|
  |--- IPERF_DONE (16) ---------->|
```

### Goodput Measurement

```
goodput(t) = (bytes_acked(t) − bytes_acked(t−1)) × 8 / Δt   [bits/s]
```

Measured via `getsockopt(IPPROTO_TCP, TCP_INFO)` → `tcpi_bytes_acked`.

---

## Assignment 3 — Linux Kernel Module (TCP Congestion Control)

### Overview

A Linux kernel module implementing **mycc**, a custom TCP congestion control algorithm. mycc extends Reno with four additional delay- and throughput-based rules that regulate window growth proactively, before packet loss occurs.

### Files

| File | Purpose |
|------|---------|
| `hw3/tcp_mycc.c` | Kernel module — full mycc implementation |
| `hw3/Makefile` | Kernel module build configuration |

### The mycc Algorithm

```
         ⌊0.5 × W⌋   if a loss event is detected          [Rule 1: multiplicative decrease]
         ⌊0.85 × W⌋  if RTT > 1.5 R₀  AND  Vt > 2 V₀    [Rule 2: severe queue buildup]
W(t+1) = W            if RTT > 1.4 R₀                     [Rule 3: mild RTT inflation — hold]
         W            if Gt < Gmin                         [Rule 4: low delivery rate — hold]
         W + 1        otherwise                            [additive increase]
```

Where:
- `R₀` — minimum observed RTT (baseline path delay)
- `V₀` — baseline RTT variation
- `Gt` — instantaneous delivery rate
- `Gmin = 0.65 × Gref` — minimum acceptable delivery rate
- `Gref` — asymmetrically smoothed reference throughput (rises fast: α=1/8, falls slow: α=1/32)

### Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_loss_hold` | 1 | Rule 1: pause growth after loss event |
| `enable_severe` | 1 | Rule 2: 0.85× cwnd on severe RTT+jitter |
| `enable_mild` | 1 | Rule 3: hold on mild RTT inflation |
| `enable_lowrate` | 1 | Rule 4: hold on low delivery rate |

### Building and Loading

```bash
cd hw3

# Build the kernel module
make

# Load into the kernel
sudo insmod tcp_mycc.ko

# Verify registration
sysctl net.ipv4.tcp_available_congestion_control
# Expected: reno cubic mycc

# Allow user-space to select mycc per socket
sudo sysctl -w net.ipv4.tcp_allowed_congestion_control="reno cubic mycc"

# Reload after recompile (development helper)
reloadcc() {
    make && { sudo rmmod tcp_mycc 2>/dev/null; sudo insmod tcp_mycc.ko; }
}
```

> Requires Linux kernel 5.10+ with kernel headers installed.

### Running Experiments

Use `hw2/iperf3_client.py` with `--cc mycc` to test the kernel module:

```bash
cd hw2

# 10-second run (repeat 3 times for mycc)
python3 iperf3_client.py --servers servers.txt --n 10 --duration 10 \
    --interval 1 --cc mycc --outdir results/10s/mycc_all_1

# 45-second run
python3 iperf3_client.py --servers servers.txt --n 10 --duration 45 \
    --interval 1 --cc mycc --outdir results/45s/mycc_all

# Baselines
python3 iperf3_client.py --servers servers.txt --n 10 --duration 45 \
    --interval 1 --cc reno --outdir results/45s/reno_baseline

python3 iperf3_client.py --servers servers.txt --n 10 --duration 45 \
    --interval 1 --cc cubic --outdir results/45s/cubic_baseline
```

### Ablation Study — Rule Toggle via Module Parameters

Each ablation variant is loaded with specific rules enabled:

```bash
# Rule 1 only (loss hold)
sudo insmod tcp_mycc.ko enable_loss_hold=1 enable_severe=0 enable_mild=0 enable_lowrate=0

# Rules 1+2
sudo insmod tcp_mycc.ko enable_loss_hold=1 enable_severe=1 enable_mild=0 enable_lowrate=0

# Rules 1+2+3
sudo insmod tcp_mycc.ko enable_loss_hold=1 enable_severe=1 enable_mild=1 enable_lowrate=0

# All rules (default)
sudo insmod tcp_mycc.ko
```

### Experimental Results Summary

#### 10-Second Comparison (mycc_all averaged over 3 runs)

| Algorithm | Mean Gp (Mbps) | Median Gp | P95 Gp | Mean RTT (ms) | Retrans |
|-----------|---------------|-----------|--------|---------------|---------|
| reno      | 15.4          | 16.0      | 27.9   | 309.0         | 1,645   |
| cubic     | 8.7           | 4.3       | 30.1   | 297.6         | 49      |
| mycc_all  | 20.3          | 22.3      | 40.7   | 334.2         | 15,191  |

mycc_all ramps up fastest (+31.8% over reno). Cubic's low mean reflects its slow ramp-up within a 10 s window.

#### 45-Second Ablation Study

| Algorithm     | Mean Gp (Mbps) | Median Gp | P95 Gp | Mean RTT (ms) | Retrans |
|---------------|---------------|-----------|--------|---------------|---------|
| reno          | 19.5          | 19.7      | 31.3   | 299.6         | 1,306   |
| cubic         | 26.0          | 30.8      | 41.6   | 296.9         | 660     |
| mycc_R1       | 20.6          | 22.1      | 40.3   | 330.9         | 18,132  |
| mycc_R1+R2    | 22.5          | 23.4      | 39.9   | 355.4         | 29,715  |
| mycc_R1+R2+R3 | 22.9          | 24.7      | 41.4   | 342.6         | 19,437  |
| mycc_all      | 25.1          | 26.8      | 42.3   | 314.4         | 16,363  |

**Incremental effect of each rule:**

| Transition | Goodput (Mean) | Retransmits | RTT (Mean) |
|------------|---------------|-------------|------------|
| Reno → R1 | +5.6% | +1,288% (worse) | +10.4% (worse) |
| R1 → R1+R2 | +9.2% | +63.8% (worse) | +7.4% (worse) |
| R1+R2 → R1+R2+R3 | +1.8% | −34.6% (better) | −3.6% (better) |
| R1+R2+R3 → all | +9.6% | −15.8% (better) | −8.2% (better) |
| Reno → mycc_all | **+28.7%** | +1,152% | +4.9% |
| CUBIC → mycc_all | −3.5% | +2,380% | +5.9% |

mycc_all achieves **97% of CUBIC's mean goodput** and **exceeds CUBIC's P95 goodput** (42.3 vs 41.6 Mbps).

### Generating Comparison Plots

```bash
cd hw2

# 10-second multi-run comparison
python3 plot_comparison_10s.py \
    --base results/10s \
    --outdir results/comparison_10s

# 45-second full ablation
python3 plot_comparison.py \
    --datasets "reno:results/45s/reno_baseline/q2_goodput_samples.csv" \
               "cubic:results/45s/cubic_baseline/q2_goodput_samples.csv" \
               "mycc_R1:results/45s/mycc_loss_hold/q2_goodput_samples.csv" \
               "mycc_R1+R2:results/45s/mycc_loss_hold_severe/q2_goodput_samples.csv" \
               "mycc_R1+R2+R3:results/45s/mycc_loss_hold_severe_mild/q2_goodput_samples.csv" \
               "mycc_all:results/45s/mycc_all/q2_goodput_samples.csv" \
    --outdir results/comparison_all \
    --bin 2.0
```

---

## Assignment 3 — Code Implementation (`hw3/tcp_mycc.c`)

The module is a standard Linux kernel TCP congestion control plugin. It registers with the kernel's `tcp_congestion_ops` interface and hooks into the two main callbacks the kernel provides: the ACK path and the loss path.

---

### Module Registration and Lifecycle

**Lines 236–262**

```c
static struct tcp_congestion_ops mycc __read_mostly = {
    .init         = mycc_init,
    .ssthresh     = mycc_ssthresh,
    .cong_control = mycc_cong_control,
    .undo_cwnd    = mycc_undo_cwnd,
    .name         = MYCC_NAME,
    .owner        = THIS_MODULE,
};
```

The `tcp_congestion_ops` struct is the kernel's plugin interface for congestion control. Four callbacks are registered:

| Callback | Trigger | Role |
|----------|---------|------|
| `mycc_init` | New connection | Initialise per-connection state |
| `mycc_ssthresh` | Loss event | Compute new slow-start threshold |
| `mycc_cong_control` | Every ACK with rate sample | Update baselines, evaluate rules, grow or hold cwnd |
| `mycc_undo_cwnd` | Loss recovery undo | Return current cwnd (conservative undo) |

At module load, `mycc_register()` calls `tcp_register_congestion_control()`. The `BUILD_BUG_ON` guard (line 247) ensures that `struct mycc` fits within the `ICSK_CA_PRIV_SIZE` bytes the kernel allocates per-connection for private congestion control state — if the struct ever grows too large the module will fail to compile rather than silently corrupt memory.

---

### Per-Connection State (`struct mycc`, lines 41–50)

```c
struct mycc {
    u32 r0_us;              // minimum SRTT seen (baseline path delay)
    u32 v0_us;              // baseline RTT variance (best seen during low-queue periods)
    u64 g_ref_Bps;          // asymmetrically smoothed reference delivery rate (bytes/s)
    u32 prev_total_retrans; // retransmit snapshot for computing Lt (new losses this ACK)
    u32 severe_persist_us;  // persistence timer for severe queue signal
    u32 mild_persist_us;    // persistence timer for mild RTT signal
    u32 lowrate_persist_us; // persistence timer for low delivery-rate signal
    u32 reduce_cooldown_us; // cooldown timer after a cwnd reduction
};
```

Each TCP connection gets its own private `struct mycc`. The three `*_persist_us` fields accumulate elapsed time while a congestion signal is active — rules only fire after the signal has been sustained for approximately one RTT (severe) or three RTTs (mild, low-rate), avoiding false positives from transient noise. The `reduce_cooldown_us` field prevents back-to-back reductions on the same congestion event.

---

### Initialisation (`mycc_init`, lines 78–95)

```c
static void mycc_init(struct sock *sk)
{
    ca->r0_us = (tp->srtt_us >> 3);   // SRTT is stored shifted left by 3
    ca->v0_us = tp->rttvar_us;
    ca->g_ref_Bps = 0;
    ca->prev_total_retrans = tp->total_retrans;
    // all persist/cooldown timers start at zero
}
```

The kernel stores `srtt_us` left-shifted by 3 (i.e. multiplied by 8) for fixed-point precision; right-shifting by 3 recovers the actual SRTT in microseconds. The initial baselines are set from the connection's first RTT measurement. If either is zero (connection just starting), a floor of 1 µs prevents division-by-zero in threshold comparisons.

---

### Loss Path (`mycc_ssthresh`, lines 223–228)

```c
static u32 mycc_ssthresh(struct sock *sk)
{
    return max(tp->snd_cwnd >> 1U, 2U);
}
```

The kernel calls `ssthresh` when it detects a loss event (duplicate ACKs / SACK, or RTO) and needs to enter a congestion-reduction phase. This is **Reno-compatible multiplicative decrease**: the slow-start threshold is set to half the current congestion window, with a floor of 2 segments. The actual cwnd reduction is handled by the kernel's loss recovery state machine; `ssthresh` only sets the ceiling for the recovery target.

---

### ACK Path (`mycc_cong_control`, lines 97–221)

This is the core of the algorithm. It is called on every ACK that carries a valid `rate_sample`. The function executes the following steps in order:

#### 1. Baseline RTT Update (lines 116–117)

```c
if (srtt_us > 0 && srtt_us < ca->r0_us)
    ca->r0_us = srtt_us;
```

`r0_us` tracks the **minimum SRTT seen over the lifetime of the connection** — an estimate of the unloaded propagation delay. It only decreases, never increases.

#### 2. Delivery Rate Estimation (lines 121–124)

```c
u64 num = (u64)rs->delivered * (u64)max_t(u32, tp->mss_cache, 1) * 1000000ULL;
gt_Bps = div64_u64(num, (u64)rs->interval_us);
```

The kernel's `rate_sample` provides `delivered` (packets ACK'd in the interval) and `interval_us` (interval duration in µs). Multiplying by `mss_cache` converts packets to bytes, and multiplying by 10⁶ then dividing by µs gives bytes/second. `div64_u64` is used for safe 64-bit division in the kernel.

#### 3. Asymmetric Smoothing of Reference Throughput (lines 131–139)

```c
if (gt_Bps >= ca->g_ref_Bps)
    ca->g_ref_Bps = ((ca->g_ref_Bps * 7ULL) + gt_Bps) / 8ULL;   // α = 1/8  (fast rise)
else
    ca->g_ref_Bps = ((ca->g_ref_Bps * 31ULL) + gt_Bps) / 32ULL; // α = 1/32 (slow decay)
```

`g_ref_Bps` tracks the **typical delivery capacity** of the path. When throughput improves, the reference rises quickly (exponential smoothing with α = 1/8). When throughput drops, the reference decays slowly (α = 1/32), making it robust to short transient congestion events. The minimum acceptable rate is `gmin = 0.65 × g_ref` (line 140).

#### 4. Loss Detection (lines 142–143)

```c
lt = tp->total_retrans - ca->prev_total_retrans;
ca->prev_total_retrans = tp->total_retrans;
```

`total_retrans` is a cumulative counter maintained by the kernel. Diffing against the last snapshot gives the number of new retransmissions since the previous ACK callback — `lt > 0` means a loss was observed. This is distinct from the `ssthresh` callback: `ssthresh` fires on the loss-event boundary; `lt > 0` on the ACK path provides a softer secondary signal.

#### 5. Persistence and Cooldown Timers (lines 145–162)

```c
sample_us = (rs->interval_us > 0) ? rs->interval_us : max(srtt_us / 8, 1000U);
severe_persist_target_us = max(srtt_us, 4000U);        // ≈ 1 RTT, floor 4 ms
soft_persist_target_us   = max(srtt_us * 3, 12000U);  // ≈ 3 RTT, floor 12 ms
cooldown_target_us       = max(srtt_us * 2, 10000U);  // ≈ 2 RTT, floor 10 ms
```

`sample_us` is the elapsed time covered by this ACK. Each call accumulates `sample_us` into the relevant persistence timer. Rules only fire after the timer exceeds its target — this implements the "sustained for N RTTs" requirement. The cooldown timer prevents a second reduction from firing while the network is still recovering from the first.

#### 6. Rule Evaluation (lines 170–218)

Rules are evaluated in priority order — higher-priority rules short-circuit lower ones:

**Rule 1 — Loss Hold (lines 170–175)**
```c
if (enable_loss_hold && lt > 0) {
    // reset all delay/rate timers and return without growing cwnd
    ca->severe_persist_us = 0;
    ca->mild_persist_us = 0;
    ca->lowrate_persist_us = 0;
    return;
}
```
If new retransmissions are observed, growth is paused entirely and all delay-based persistence timers are cleared. The function returns without calling `mycc_ack_driven_increase`, so cwnd neither grows nor shrinks (the actual reduction already happened via `ssthresh`).

**Rule 2 — Severe Queue Buildup (lines 177–195)**
```c
severe_queue = (srtt_us > (ca->r0_us * 150U) / 100U) &&
               (rttvar_us > (ca->v0_us * 200U) / 100U);

if (enable_severe && severe_queue) {
    ca->severe_persist_us += sample_us;
    if (cooldown_active || persist < target) return;  // soft hold first
    cwnd = (cwnd * 85U) / 100U;                       // 15% reduction
    tp->snd_cwnd = mycc_clamp_cwnd(cwnd);
    ca->reduce_cooldown_us = cooldown_target_us;
    ca->severe_persist_us = 0;
    return;
}
```
Both RTT (>1.5×baseline) and RTT variance (>2×baseline) must be elevated simultaneously — requiring both signals prevents false triggers from either noise alone. After accumulating for ≈1 RTT, cwnd is reduced by 15%. The cooldown is then armed to prevent repeated reductions before the queue has a chance to drain.

**Rule 3 — Mild RTT Inflation (lines 198–208)**
```c
mild_rtt = (srtt_us > (ca->r0_us * 140U) / 100U);

if (enable_mild && mild_rtt) {
    ca->mild_persist_us += sample_us;
    if (persist >= soft_persist_target_us) return;  // hold: no growth
}
```
A softer threshold (1.4×) that only requires RTT elevation — no jitter check. After accumulating for ≈3 RTTs, growth is suspended without reducing cwnd. This acts as an early-warning mechanism that intercepts congestion before it becomes severe enough to trigger Rule 2.

**Rule 4 — Low Delivery Rate (lines 210–218)**
```c
low_rate = (gmin_Bps > 0 && gt_Bps > 0 && gt_Bps < gmin_Bps);

if (enable_lowrate && low_rate) {
    ca->lowrate_persist_us += sample_us;
    if (persist >= soft_persist_target_us) return;  // hold: no growth
}
```
Detects congestion through throughput degradation rather than delay. If the delivery rate drops below 65% of the reference for ≈3 RTTs, cwnd growth is suspended. This catches early-stage congestion on paths where shallow buffers cause throughput drops before RTT inflates noticeably.

#### 7. Additive Increase (`mycc_ack_driven_increase`, lines 61–76)

```c
static void mycc_ack_driven_increase(struct sock *sk, const struct rate_sample *rs)
{
    if (tcp_in_slow_start(tp))
        acked = tcp_slow_start(tp, acked);   // standard Reno slow start
    if (acked)
        tcp_cong_avoid_ai(tp, tcp_snd_cwnd(tp), acked);  // standard AIMD +1/RTT
}
```

If no rule fires, the function falls through to `mycc_ack_driven_increase`. This uses the kernel's own `tcp_slow_start` and `tcp_cong_avoid_ai` helpers — making slow start and congestion avoidance fully Reno-compatible. `tcp_cong_avoid_ai` increments cwnd by approximately 1 segment per RTT when in congestion avoidance.

---

### Module Parameters for Ablation (lines 17–31)

```c
static bool enable_loss_hold = true;
static bool enable_severe    = true;
static bool enable_mild      = false;   // off by default in final config
static bool enable_lowrate   = false;   // off by default in final config
module_param(enable_loss_hold, bool, 0644);
```

Each rule is a module parameter settable at `insmod` time or live via `/sys/module/tcp_mycc/parameters/`. The `0644` permission allows root to toggle rules at runtime without reloading the module, which was used during development for rapid A/B testing without rebooting.

---

## LLM Usage

Large Language Models were used to polish report language and assist with implementing utility functions such as plotting and overall code structuring.
