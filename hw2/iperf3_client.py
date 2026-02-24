#!/usr/bin/env python3
"""
CS 536 Assignment 2 - Part 1: iPerf Throughput Application

Usage:
    python3 iperf3_client.py [--n N] [--duration D] [--interval I] [--servers FILE] [--outdir DIR]
"""

import socket
import struct
import json
import time
import random
import string
import threading
import argparse
import csv
import sys
import os
import ctypes
from datetime import datetime

# ── iperf3 protocol state constants ──────────────────────────────────────────
TEST_START       = 1
TEST_RUNNING     = 2
TEST_END         = 4
PARAM_EXCHANGE   = 9
CREATE_STREAMS   = 10
SERVER_TERMINATE = 11
CLIENT_TERMINATE = 12
EXCHANGE_RESULTS = 13
DISPLAY_RESULTS  = 14
IPERF_START      = 15
IPERF_DONE       = 16
ACCESS_DENIED    = 255
SERVER_ERROR     = 254

COOKIE_SIZE = 37
BLKSIZE     = 128 * 1024   # 128 KB (iperf3 default)
TCP_INFO    = 11            # SOL_TCP / TCP_INFO optname (Linux)

# ── TCP_INFO struct (Linux) ───────────────────────────────────────────────────
class TcpInfo(ctypes.Structure):
    _fields_ = [
        ("tcpi_state",           ctypes.c_uint8),
        ("tcpi_ca_state",        ctypes.c_uint8),
        ("tcpi_retransmits",     ctypes.c_uint8),
        ("tcpi_probes",          ctypes.c_uint8),
        ("tcpi_backoff",         ctypes.c_uint8),
        ("tcpi_options",         ctypes.c_uint8),
        ("tcpi_snd_rcv_wscale",  ctypes.c_uint8),
        ("tcpi_delivery_app_lim",ctypes.c_uint8),
        ("tcpi_rto",             ctypes.c_uint32),
        ("tcpi_ato",             ctypes.c_uint32),
        ("tcpi_snd_mss",         ctypes.c_uint32),
        ("tcpi_rcv_mss",         ctypes.c_uint32),
        ("tcpi_unacked",         ctypes.c_uint32),
        ("tcpi_sacked",          ctypes.c_uint32),
        ("tcpi_lost",            ctypes.c_uint32),
        ("tcpi_retrans",         ctypes.c_uint32),
        ("tcpi_fackets",         ctypes.c_uint32),
        ("tcpi_last_data_sent",  ctypes.c_uint32),
        ("tcpi_last_ack_sent",   ctypes.c_uint32),
        ("tcpi_last_data_recv",  ctypes.c_uint32),
        ("tcpi_last_ack_recv",   ctypes.c_uint32),
        ("tcpi_pmtu",            ctypes.c_uint32),
        ("tcpi_rcv_ssthresh",    ctypes.c_uint32),
        ("tcpi_rtt",             ctypes.c_uint32),
        ("tcpi_rttvar",          ctypes.c_uint32),
        ("tcpi_snd_ssthresh",    ctypes.c_uint32),
        ("tcpi_snd_cwnd",        ctypes.c_uint32),
        ("tcpi_advmss",          ctypes.c_uint32),
        ("tcpi_reordering",      ctypes.c_uint32),
        ("tcpi_rcv_rtt",         ctypes.c_uint32),
        ("tcpi_rcv_space",       ctypes.c_uint32),
        ("tcpi_total_retrans",   ctypes.c_uint32),
        ("tcpi_pacing_rate",     ctypes.c_uint64),
        ("tcpi_max_pacing_rate", ctypes.c_uint64),
        ("tcpi_bytes_acked",     ctypes.c_uint64),
        ("tcpi_bytes_received",  ctypes.c_uint64),
        ("tcpi_segs_out",        ctypes.c_uint32),
        ("tcpi_segs_in",         ctypes.c_uint32),
        ("tcpi_notsent_bytes",   ctypes.c_uint32),
        ("tcpi_min_rtt",         ctypes.c_uint32),
        ("tcpi_data_segs_in",    ctypes.c_uint32),
        ("tcpi_data_segs_out",   ctypes.c_uint32),
        ("tcpi_delivery_rate",   ctypes.c_uint64),
    ]


def get_tcp_info(sock):
    try:
        raw  = sock.getsockopt(socket.IPPROTO_TCP, TCP_INFO, ctypes.sizeof(TcpInfo))
        info = TcpInfo()
        ctypes.memmove(ctypes.addressof(info), raw, min(len(raw), ctypes.sizeof(info)))
        return info
    except Exception:
        return None


# ── Cookie / helpers ──────────────────────────────────────────────────────────
def make_cookie():
    chars = string.ascii_lowercase + string.digits
    return (''.join(random.choices(chars, k=36)) + '\0').encode('ascii')


def ctrl_recv_state(sock, timeout=10.0):
    sock.settimeout(timeout)
    data = sock.recv(1)
    if not data:
        raise ConnectionError("Control socket closed")
    b = data[0]
    if b == 255: return ACCESS_DENIED
    if b == 254: return SERVER_ERROR
    return b


def ctrl_send_state(sock, state):
    sock.sendall(bytes([state & 0xFF]))


def ctrl_send_json(sock, obj):
    payload = json.dumps(obj).encode('utf-8')
    sock.sendall(struct.pack('!I', len(payload)) + payload)


def ctrl_recv_json(sock, timeout=10.0):
    sock.settimeout(timeout)
    hdr = _recvall(sock, 4)
    if hdr is None: return None
    length = struct.unpack('!I', hdr)[0]
    if length == 0 or length > 1_000_000: return None
    raw = _recvall(sock, length)
    if raw is None: return None
    return json.loads(raw.decode('utf-8'))


def _recvall(sock, n):
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk: return None
        buf += chunk
    return buf


# ── Main iperf3 test ──────────────────────────────────────────────────────────
def run_iperf3_test(host, port, duration, interval, results_list, server_label):
    cookie    = make_cookie()
    ctrl_sock = None
    data_sock = None

    try:
        # 1. Control connection + cookie
        ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ctrl_sock.settimeout(10.0)
        ctrl_sock.connect((host, port))
        ctrl_sock.sendall(cookie)
        print(f"  [{server_label}] Connected")

        # 2. PARAM_EXCHANGE
        state = ctrl_recv_state(ctrl_sock, timeout=10.0)
        if state == ACCESS_DENIED:
            print(f"  [{server_label}] Access denied (server busy)")
            return False
        if state != PARAM_EXCHANGE:
            print(f"  [{server_label}] Expected PARAM_EXCHANGE(9), got {state}")
            return False

        params = {
            "tcp": 1, "omit": 0, "time": duration,
            "num": 0, "blockcount": 0, "parallel": 1,
            "len": BLKSIZE, "pacing_timer": 1000,
            "client_version": "3.17.1",
        }
        ctrl_send_json(ctrl_sock, params)

        # 3. CREATE_STREAMS
        state = ctrl_recv_state(ctrl_sock, timeout=10.0)
        if state != CREATE_STREAMS:
            print(f"  [{server_label}] Expected CREATE_STREAMS(10), got {state}")
            return False

        # 4. Open data connection + send cookie
        data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_sock.settimeout(10.0)
        data_sock.connect((host, port))
        data_sock.sendall(cookie)
        data_sock.settimeout(None)

        # 5. TEST_START + TEST_RUNNING
        state = ctrl_recv_state(ctrl_sock, timeout=10.0)
        if state != TEST_START:
            print(f"  [{server_label}] Expected TEST_START(1), got {state}")
            return False
        state = ctrl_recv_state(ctrl_sock, timeout=10.0)
        if state != TEST_RUNNING:
            print(f"  [{server_label}] Expected TEST_RUNNING(2), got {state}")
            return False

        print(f"  [{server_label}] Sending data for {duration}s ...")

        # 6. Send data + sample goodput
        send_buf          = os.urandom(BLKSIZE)
        test_start        = time.time()
        test_end          = test_start + duration
        prev_bytes_acked  = 0
        prev_sample_time  = test_start
        stop_flag         = threading.Event()

        def ctrl_watcher():
            try:
                ctrl_sock.settimeout(duration + 30)
                b = ctrl_sock.recv(1)
                if b and b[0] in (SERVER_TERMINATE, SERVER_ERROR, ACCESS_DENIED):
                    print(f"  [{server_label}] Server terminated early")
                    stop_flag.set()
            except Exception:
                pass

        ctrl_sock.settimeout(duration + 30)
        watcher = threading.Thread(target=ctrl_watcher, daemon=True)
        watcher.start()

        sending = True
        while time.time() < test_end and not stop_flag.is_set():
            try:
                data_sock.sendall(send_buf)
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                print(f"  [{server_label}] Data socket error: {e}")
                break

            now = time.time()
            if now - prev_sample_time >= interval and now <= test_end:
                info    = get_tcp_info(data_sock)
                elapsed = now - test_start
                if info is not None:
                    delta_bytes = info.tcpi_bytes_acked - prev_bytes_acked
                    delta_t     = now - prev_sample_time
                    goodput_bps = (delta_bytes * 8) / delta_t if delta_t > 0 else 0.0
                    prev_bytes_acked = info.tcpi_bytes_acked
                    results_list.append({
                        "server":        server_label,
                        "timestamp":     now,
                        "elapsed_s":     round(elapsed, 3),
                        "goodput_bps":   goodput_bps,
                        "goodput_mbps":  goodput_bps / 1e6,
                        "bytes_acked":   info.tcpi_bytes_acked,
                        "snd_cwnd":      info.tcpi_snd_cwnd,
                        "rtt_us":        info.tcpi_rtt,
                        "rtt_ms":        info.tcpi_rtt / 1000.0,
                        "rttvar_us":     info.tcpi_rttvar,
                        "retransmits":   info.tcpi_retrans,
                        "total_retrans": info.tcpi_total_retrans,
                        "lost":          info.tcpi_lost,
                        "pacing_rate":   info.tcpi_pacing_rate,
                        "delivery_rate": info.tcpi_delivery_rate,
                        "snd_ssthresh":  info.tcpi_snd_ssthresh,
                    })
                prev_sample_time = now

        # 7. Teardown
        try:
            ctrl_sock.settimeout(10.0)
            ctrl_send_state(ctrl_sock, TEST_END)
            state = ctrl_recv_state(ctrl_sock, timeout=15.0)
            if state == EXCHANGE_RESULTS:
                ctrl_send_json(ctrl_sock, {"cpu_util_total": 0.0, "streams": []})
                ctrl_recv_json(ctrl_sock, timeout=15.0)
            state = ctrl_recv_state(ctrl_sock, timeout=10.0)
            if state == DISPLAY_RESULTS:
                ctrl_send_state(ctrl_sock, IPERF_DONE)
        except Exception as e:
            print(f"  [{server_label}] Teardown warning: {e}")

        print(f"  [{server_label}] Done. {len(results_list)} samples collected.")
        return True

    except socket.timeout:
        print(f"  [{server_label}] Timeout")
        return False
    except ConnectionRefusedError:
        print(f"  [{server_label}] Connection refused")
        return False
    except Exception as e:
        print(f"  [{server_label}] Error: {e}")
        return False
    finally:
        for s in (data_sock, ctrl_sock):
            if s:
                try: s.close()
                except: pass


# ── Server list ───────────────────────────────────────────────────────────────
def fetch_server_list():
    """Hardcoded fallback list of public iperf3 servers."""
    servers = [
        ("ping.online.net",            5201),
        ("iperf.he.net",               5201),
        ("bouygues.testdebit.info",    5201),
        ("speedtest.wtnet.de",         5201),
        ("lon.speedtest.clouvider.net",5201),
        ("nyc.speedtest.clouvider.net",5201),
        ("ams.speedtest.clouvider.net",5201),
        ("la.speedtest.clouvider.net", 5201),
        ("dal.speedtest.clouvider.net",5201),
        ("syd.speedtest.clouvider.net",5201),
    ]
    print(f"Using {len(servers)} built-in servers (no --servers file provided)")
    return servers


def load_servers_from_file(filepath):
    """
    Parse servers.txt. Each line: IP/hostname,port_or_range[,...]
    Port range like 9201-9240 picks a random port in that range.
    Returns list of (host, port) tuples.
    """
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts      = line.split(',')
            host       = parts[0].strip()
            port_field = parts[1].strip() if len(parts) > 1 else '5201'
            if '-' in port_field:
                lo, hi = port_field.split('-', 1)
                try:    port = random.randint(int(lo), int(hi))
                except: port = 5201
            else:
                try:    port = int(port_field)
                except: port = 5201
            entries.append((host, port))
    return entries


# ── Stats + output ────────────────────────────────────────────────────────────
def compute_stats(values):
    if not values:
        return {"min": 0, "median": 0, "mean": 0, "p95": 0, "max": 0, "count": 0}
    s  = sorted(values)
    n  = len(s)
    md = s[n//2] if n % 2 else (s[n//2-1] + s[n//2]) / 2
    return {"min": s[0], "median": md, "mean": sum(s)/n,
            "p95": s[int(0.95*n)], "max": s[-1], "count": n}


def save_csv(samples, outfile):
    if not samples: return
    with open(outfile, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
        w.writeheader(); w.writerows(samples)
    print(f"Saved CSV: {outfile}")


def make_plots(all_samples, outdir):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np
    except ImportError:
        print("matplotlib not available — skipping plots"); return

    os.makedirs(outdir, exist_ok=True)
    servers = {}
    for s in all_samples:
        servers.setdefault(s['server'], []).append(s)

    colors = cm.tab10(np.linspace(0, 1, max(len(servers), 1)))

    # Goodput time series
    fig, ax = plt.subplots(figsize=(12, 5))
    for (srv, samps), color in zip(servers.items(), colors):
        ax.plot([s['elapsed_s'] for s in samps],
                [s['goodput_mbps'] for s in samps],
                label=srv, color=color, linewidth=1.5)
    ax.set_xlabel("Time (s)"); ax.set_ylabel("Goodput (Mbps)")
    ax.set_title("Goodput Time Series — All Destinations")
    ax.legend(fontsize=7, ncol=2); ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p1 = os.path.join(outdir, "goodput_timeseries.pdf")
    fig.savefig(p1); plt.close(fig); print(f"Saved: {p1}")

    # Summary table
    fig, ax = plt.subplots(figsize=(11, max(2, len(servers)*0.5+1.5)))
    ax.axis('off')
    rows = []
    for srv, samps in servers.items():
        st = compute_stats([s['goodput_mbps'] for s in samps])
        rows.append([srv[:42], f"{st['min']:.2f}", f"{st['median']:.2f}",
                     f"{st['mean']:.2f}", f"{st['p95']:.2f}",
                     f"{st['max']:.2f}", str(st['count'])])
    tbl = ax.table(cellText=rows,
                   colLabels=["Server","Min (Mbps)","Median","Avg","P95","Max","N"],
                   loc='center', cellLoc='center')
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.4)
    ax.set_title("Goodput Summary Table", fontsize=12, pad=12)
    fig.tight_layout()
    p2 = os.path.join(outdir, "goodput_summary_table.pdf")
    fig.savefig(p2); plt.close(fig); print(f"Saved: {p2}")


def print_summary(all_samples):
    servers = {}
    for s in all_samples:
        servers.setdefault(s['server'], []).append(s)
    hdr = f"{'Server':<45} {'Min':>8} {'Median':>8} {'Mean':>8} {'P95':>8} {'Max':>8} {'N':>5}"
    print("\n" + "="*len(hdr))
    print("GOODPUT SUMMARY (Mbps)")
    print("="*len(hdr))
    print(hdr)
    print("-"*len(hdr))
    for srv, samps in servers.items():
        st = compute_stats([s['goodput_mbps'] for s in samps])
        print(f"{srv:<45} {st['min']:>8.2f} {st['median']:>8.2f} {st['mean']:>8.2f} "
              f"{st['p95']:>8.2f} {st['max']:>8.2f} {st['count']:>5}")
    print("="*len(hdr))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CS 536 iperf3 Python client")
    parser.add_argument('--n',        type=int,   default=10,      help='Number of servers to test')
    parser.add_argument('--duration', type=int,   default=20,      help='Test duration per server (s)')
    parser.add_argument('--interval', type=float, default=1.0,     help='Sampling interval (s)')
    parser.add_argument('--servers',  type=str,   default=None,    help='servers.txt file path')
    parser.add_argument('--outdir',   type=str,   default=None, help='Output directory')
    args = parser.parse_args()

    if args.outdir is None:
        args.outdir = f"results/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    os.makedirs(args.outdir, exist_ok=True)

    # Load servers — returns list of (host, port) tuples
    if args.servers:
        candidates = load_servers_from_file(args.servers)
        print(f"Loaded {len(candidates)} servers from {args.servers}")
    else:
        candidates = fetch_server_list()

    if not candidates:
        print("ERROR: No servers available."); sys.exit(1)

    random.shuffle(candidates)

    print(f"\nStarting tests: n={args.n}, duration={args.duration}s, interval={args.interval}s\n")

    all_samples = []
    tested = 0
    tried  = 0

    while tested < args.n and tried < len(candidates):
        host, port = candidates[tried]
        tried += 1
        label = f"{host}:{port}"
        print(f"\n[{tested+1}/{args.n}] Testing {label} ...")

        server_samples = []
        success = run_iperf3_test(host, port, args.duration,
                                  args.interval, server_samples, label)

        if success and server_samples:
            all_samples.extend(server_samples)
            tested += 1
        else:
            print(f"  Skipping — trying next server ...")

        if tried >= len(candidates) and tested < args.n:
            print(f"\nWarning: exhausted all {tried} candidates ({tested} successful)")
            break

    if all_samples:
        save_csv(all_samples, os.path.join(args.outdir, "goodput_samples.csv"))
        print_summary(all_samples)
        make_plots(all_samples, args.outdir)
    else:
        print("\nNo data collected.")

    print(f"\nDone. {tested}/{args.n} servers tested successfully.")


if __name__ == '__main__':
    main()