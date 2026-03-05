# CS 536 Assignment 2 — iPerf Throughput & TCP Stats

## Overview

A from-scratch Python TCP client that implements the **iperf3 protocol**, connects to public iperf3 servers, measures goodput using `TCP_INFO`, extracts TCP statistics, and generates all required plots.

## Files

| File | Purpose |
|------|---------|
| `iperf3_client.py` | Main client — iperf3 protocol, measurement, Q1 plotting |
| `plot_tcp_stats.py` | Q2(b) — TCP stats visualization (time-series + scatter plots) |
| `servers.txt` | Server list from https://iperf3serverlist.net/ |
| `run_experiment.sh` | One-shot experiment runner |
| `Dockerfile` | Containerized environment (Ubuntu 24.04) |

---

## How to Run

### With Docker (recommended)

```bash
# Build
docker build -t cs536-hw2 .

# Run with defaults (n=10, duration=20s, interval=1s)
# Q1 + Q2 plots are generated automatically
docker run --rm -v $(pwd)/results:/app/results cs536-hw2

# Override parameters
docker run --rm -v $(pwd)/results:/app/results cs536-hw2 \
  --n 5 --duration 30 --interval 1 --cc cubic

```

### Directly (Linux with Python 3.10+)

```bash
# Run full experiment (Q1 + Q2 plots generated automatically)
python3 iperf3_client.py --servers servers.txt --n 10 --duration 20 --interval 1

# Run with a specific congestion control (per-socket)
python3 iperf3_client.py --servers servers.txt --n 10 --duration 20 --interval 1 --cc mycc

# Generate Q2 plots separately (if needed)
python3 plot_tcp_stats.py --csv results/results_YYYYMMDD_HHMMSS/goodput_samples.csv

# Specify a particular server for Q2 plots
python3 plot_tcp_stats.py --csv results/results_YYYYMMDD_HHMMSS/goodput_samples.csv \
  --server "lg.vie.alwyzon.net:5203"
```

> **Requirement**: Must run on Linux or Windows WSL2 (real Linux kernel needed for `TCP_INFO`).

---

## Command-Line Arguments

### `iperf3_client.py`

| Argument | Default | Description |
|----------|---------|-------------|
| `--n` | 10 | Number of servers to test |
| `--duration` | 20 | Test duration per server (seconds) |
| `--interval` | 1.0 | Goodput sampling interval (seconds) |
| `--servers` | (built-in list) | Path to server list file |
| `--outdir` | `results/results_YYYYMMDD_HHMMSS/` | Output directory |
| `--cc` | (system default) | TCP congestion control algorithm (e.g., `cubic`, `bbr`, `mycc`) |

### `plot_tcp_stats.py`

| Argument | Default | Description |
|----------|---------|-------------|
| `--csv` | (required) | Path to `goodput_samples.csv` |
| `--outdir` | (same dir as CSV) | Output directory for plots |
| `--server` | (auto: most samples) | Server label for representative plots |

---

## Output

After running, the timestamped output directory contains:

### Q1 — Goodput Measurement
| File | Description |
|------|-------------|
| `q2_goodput_samples.csv` | All samples with TCP stats (see columns below) |
| `q1_goodput_timeseries.pdf` | Goodput (Mbps) vs time, all destinations overlaid |
| `q1_goodput_summary_table.pdf` | Table of min / median / avg / P95 / max per destination |

### Q2 — TCP Stats Visualization
| File | Description |
|------|-------------|
| `q2_timeseries.pdf` | 4-panel time series: cwnd, RTT, retransmits, goodput |
| `q2_scatter_cwnd_goodput.pdf` | Scatter: congestion window vs goodput |
| `q2_scatter_rtt_goodput.pdf` | Scatter: RTT vs goodput |
| `q2_scatter_loss_goodput.pdf` | Scatter: total retransmissions vs goodput |

### CSV Columns
```
server, timestamp, elapsed_s, goodput_bps, goodput_mbps, bytes_acked,
snd_cwnd, rtt_us, rtt_ms, rttvar_us, retransmits, total_retrans,
lost, pacing_rate, delivery_rate, snd_ssthresh, cc_algo
```

---

## iperf3 Protocol Implementation

The client implements the full iperf3 state machine:

```
Client                          Server
  |                               |
  |--- TCP connect (ctrl) ------->|
  |--- 37-byte cookie ----------->|
  |<-- PARAM_EXCHANGE (9) --------|
  |--- JSON params -------------->|  {"tcp":1, "time":20, "parallel":1, ...}
  |<-- CREATE_STREAMS (10) -------|
  |--- TCP connect (data) ------->|  (second connection)
  |--- 37-byte cookie ----------->|  (same cookie, identifies stream)
  |<-- TEST_START (1) ------------|
  |<-- TEST_RUNNING (2) ----------|
  |=== SEND DATA ================>|  (bulk TCP data for `duration` seconds)
  |--- TEST_END (4) ------------->|
  |<-- EXCHANGE_RESULTS (13) -----|
  |--- JSON our results --------->|
  |<-- JSON server results -------|
  |<-- DISPLAY_RESULTS (14) ------|
  |--- IPERF_DONE (16) ---------->|
```

State bytes are single unsigned bytes on the control channel. JSON payloads are prefixed with a 4-byte big-endian length.

---

## Goodput Measurement

Goodput is measured using `getsockopt(TCP_INFO)` on the data socket:

```
goodput(t) = (bytes_acked(t) - bytes_acked(t-1)) × 8 / Δt   [bits/s]
```

`tcpi_bytes_acked` counts bytes the receiver has ACK'd — this reflects actual application-layer delivery, not just bytes sent into the socket buffer.

---

## Error Handling

The client handles:
- Connection timeouts (10s connect timeout)
- `ACCESS_DENIED` (server busy — auto-skip)
- `SERVER_TERMINATE` / `SERVER_ERROR` signals
- Broken data connections mid-transfer
- Servers that don't respond or reject parameters
- Auto-replacement of failed servers from candidate pool
