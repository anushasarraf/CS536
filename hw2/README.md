# CS 536 Assignment 2 — Part 1: iPerf Throughput Application

## Overview

A from-scratch Python TCP client that implements the **iperf3 protocol** and connects to public iperf3 servers, measures goodput using `TCP_INFO`, and generates plots and a summary table.

## Files

| File | Purpose |
|------|---------|
| `iperf3_client.py` | Main client — protocol, measurement, plotting |
| `servers.txt` | Server list from https://iperf3serverlist.net/|
| `run_experiment.sh` | One-shot experiment runner |
| `Dockerfile` | Containerized environment (Ubuntu 24.04) |

---

## How to Run

### Directly (Linux with Python 3.10+)

```bash
# Auto-fetch servers from iperf3serverlist.net, test 10 of them for 20s each
python3 iperf3_client.py --n 10 --duration 20 --interval 1.0

# Use hand-curated server list
python3 iperf3_client.py --servers servers.txt --n 10 --duration 20

# Custom output directory
python3 iperf3_client.py --n 5 --outdir my_results/
```
# Build
docker build -t cs536-part1 .

# Run with defaults (n=10, duration=20s, interval=1s, servers.txt baked in)
docker run --rm -v $(pwd)/results:/app/results cs536-part1

# Override parameters
docker run --rm -v $(pwd)/results:/app/results cs536-part1 \
  --n 5 --duration 30 --interval 1

# Custom server file
docker run --rm \
  -v $(pwd)/results:/app/results \
  -v $(pwd)/my_servers.txt:/app/servers.txt \
  cs536-part1 --n 10 --duration 20

> **Requirement**: Must run on Linux or Windows WSL2 (real Linux kernel needed for `TCP_INFO`).

---

## Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--n` | 10 | Number of servers to test |
| `--duration` | 20 | Test duration per server (seconds) |
| `--interval` | 1.0 | Goodput sampling interval (seconds) |
| `--port` | 5201 | iperf3 server port |
| `--servers` | (auto) | Path to server list file |
| `--outdir` | `results/` | Output directory for CSV + PDF plots |

---

## Output

After running, `results/` (or `--outdir`) contains:

- `goodput_samples.csv` — all samples with columns:
  `server, timestamp, elapsed_s, goodput_bps, goodput_mbps, bytes_acked, snd_cwnd, rtt_us, rtt_ms, rttvar_us, retransmits, total_retrans, lost, pacing_rate, delivery_rate, snd_ssthresh`

- `goodput_timeseries.pdf` — goodput (Mbps) vs time, all destinations overlaid

- `goodput_summary_table.pdf` — table of min / median / avg / P95 / max per destination

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

```python
goodput(t) = (bytes_acked(t) - bytes_acked(t-1)) * 8
             ─────────────────────────────────────────
                        interval_length (s)
```

`tcpi_bytes_acked` counts bytes the receiver has ACK'd — this reflects actual application-layer delivery, not just bytes sent into the socket buffer.

---

## Error Handling

The client handles:
- Connection timeouts (10s connect timeout)
- `ACCESS_DENIED` (server busy — auto-skip)
- `SERVER_TERMINATE` / `SERVER_ERROR` signals
- Broken data connections
- Servers that don't respond or reject parameters
- Auto-replacement of failed servers from candidate pool
