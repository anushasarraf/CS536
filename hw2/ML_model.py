#!/usr/bin/env python3
"""
CS 536 Assignment 2 — Q3: ML Model for Congestion Window Prediction
Pure NumPy implementation — no sklearn/scipy dependency.

Usage:
    python3 ml_model.py --csv q2_goodput_samples.csv --plots plots/ --models models/
"""

import os, sys, argparse, warnings, logging, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_pdf import PdfPages

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── objective weights  η(t) = goodput(t) − α·RTT(t) − β·loss(t) ────────────
ALPHA  = 0.3
BETA   = 0.5
WINDOW = 3

plt.rcParams.update({
    "figure.dpi":        130,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.25,
    "font.size":         9,
})


# ─────────────────────────────────────────────────────────────────────────────
# Pure-NumPy helpers  (no sklearn)
# ─────────────────────────────────────────────────────────────────────────────

class Scaler:
    """Zero-mean unit-variance scaler."""
    def fit(self, X):
        self.mean_ = X.mean(axis=0)
        self.std_  = X.std(axis=0) + 1e-9
        return self
    def transform(self, X):
        return (X - self.mean_) / self.std_
    def fit_transform(self, X):
        return self.fit(X).transform(X)
    def save(self, path):
        np.savez(path, mean=self.mean_, std=self.std_)
    @classmethod
    def load(cls, path):
        d = np.load(path)
        s = cls(); s.mean_ = d["mean"]; s.std_ = d["std"]
        return s


class RidgeModel:
    """Ridge regression  (closed-form: w = (XᵀX + λI)⁻¹ Xᵀy)."""
    def __init__(self, alpha=1.0):
        self.alpha = alpha
        self.w_ = None

    def fit(self, X, y):
        n, p   = X.shape
        A      = X.T @ X + self.alpha * np.eye(p)
        b      = X.T @ y
        self.w_ = np.linalg.solve(A, b)
        return self

    def predict(self, X):
        return X @ self.w_

    def save(self, path):
        np.save(path, self.w_)

    @classmethod
    def load(cls, path):
        m = cls(); m.w_ = np.load(path)
        return m


def _mse(y, yp):   return float(np.mean((y - yp)**2))
def _rmse(y, yp):  return float(np.sqrt(_mse(y, yp)))
def _r2(y, yp):
    ss_res = np.sum((y - yp)**2)
    ss_tot = np.sum((y - y.mean())**2) + 1e-9
    return float(1 - ss_res / ss_tot)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Load & normalise
# ─────────────────────────────────────────────────────────────────────────────

def load_data(csv_path):
    df = pd.read_csv(csv_path)
    df = df.rename(columns={
        "server":    "destination",
        "elapsed_s": "elapsed",
        "rtt_us":    "srtt_us",
        "rtt_ms":    "srtt_ms",
    })
    df["pacing_mbps"]   = df["pacing_rate"]  / 1e6
    df["delivery_mbps"] = df["delivery_rate"] / 1e6
    df["rttvar_ms"]     = df["rttvar_us"]     / 1e3
    df["snd_cwnd"]      = pd.to_numeric(df["snd_cwnd"], errors="coerce").ffill().bfill()

    per_host = {}
    for dest, grp in df.groupby("destination"):
        g = grp.sort_values("elapsed").reset_index(drop=True)
        if len(g) >= 8:
            per_host[dest] = g
        else:
            log.warning(f"Skipping {dest}: only {len(g)} rows")
    return per_host


# ─────────────────────────────────────────────────────────────────────────────
# 2. Feature engineering
# ─────────────────────────────────────────────────────────────────────────────

FEAT_COLS = [
    "goodput_mbps", "srtt_ms", "rttvar_ms",
    "total_retrans", "snd_cwnd", "pacing_mbps", "delivery_mbps",
]

def _minmax(s):
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo + 1e-9)

def add_eta(df):
    df = df.copy()
    df["eta"] = (
        df["goodput_mbps"]
        - ALPHA * _minmax(df["srtt_ms"])
        - BETA  * _minmax(df["total_retrans"])
    )
    return df

def build_features(df, window=WINDOW):
    df = add_eta(df)
    df["delta_cwnd"] = df["snd_cwnd"].diff().fillna(0)
    all_cols = FEAT_COLS + ["eta"]

    rows = []
    for i in range(window, len(df)):
        feat = {}
        for lag in range(window):
            src = df.iloc[i - lag - 1]
            for col in all_cols:
                feat[f"{col}_lag{lag}"] = float(src[col])
        feat["target"] = float(df.iloc[i]["delta_cwnd"])
        rows.append(feat)

    return pd.DataFrame(rows).fillna(0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Train / evaluate
# ─────────────────────────────────────────────────────────────────────────────

def chrono_split(feat_df, test_frac=0.30):
    cut = int(len(feat_df) * (1 - test_frac))
    return feat_df.iloc[:cut].copy(), feat_df.iloc[cut:].copy()

def train_model(train_df):
    X = train_df.drop(columns=["target"]).values.astype(float)
    y = train_df["target"].values.astype(float)
    scaler = Scaler()
    Xs     = scaler.fit_transform(X)
    model  = RidgeModel(alpha=1.0).fit(Xs, y)
    return model, scaler

def eval_model(model, scaler, test_df):
    X  = test_df.drop(columns=["target"]).values.astype(float)
    y  = test_df["target"].values.astype(float)
    yp = model.predict(scaler.transform(X))
    return {
        "rmse":   _rmse(y, yp),
        "r2":     _r2(y, yp),
        "y_true": y,
        "y_pred": yp,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Simulate cwnd from test_start onward
# ─────────────────────────────────────────────────────────────────────────────

def simulate_cwnd(df, model, scaler, test_start, window=WINDOW):
    df       = add_eta(df)
    all_cols = FEAT_COLS + ["eta"]
    n_feats  = window * len(all_cols)
    sim      = df["snd_cwnd"].values.copy().astype(float)

    for i in range(max(window, test_start), len(df)):
        feat = []
        for lag in range(window):
            src = df.iloc[i - lag - 1]
            for col in all_cols:
                val = sim[i - lag - 1] if col == "snd_cwnd" else float(src[col])
                feat.append(val)

        fv = np.array(feat, dtype=float).reshape(1, -1)
        if fv.shape[1] < n_feats:
            fv = np.pad(fv, ((0,0),(0, n_feats - fv.shape[1])))
        elif fv.shape[1] > n_feats:
            fv = fv[:, :n_feats]

        try:
            delta = model.predict(scaler.transform(fv))[0]
        except Exception:
            delta = 0.0
        sim[i] = max(1.0, sim[i-1] + delta)

    return sim


# ─────────────────────────────────────────────────────────────────────────────
# 5. Plots
# ─────────────────────────────────────────────────────────────────────────────

def short(host):
    return (host.replace("speedtest.", "").replace(":5201","")
                .replace(":5207","").replace(":5203","")
                .replace(":60001","").replace(":9212",""))

def _draw_cwnd(ax, df, sim, test_start, host):
    t  = df["elapsed"].values
    ac = df["snd_cwnd"].values
    ts = t[test_start]
    ax.plot(t,              ac,               color="steelblue",  lw=1.6, label="Actual")
    ax.plot(t[test_start:], sim[test_start:], color="darkorange", lw=1.6,
            ls="--", label="Predicted")
    ax.axvline(ts, color="crimson", ls=":", lw=1.1, label="Train/Test split")
    ax.fill_betweenx([ac.min()*0.9, ac.max()*1.1], ts, t[-1],
                     alpha=0.07, color="darkorange")
    ax.set_title(short(host), fontsize=8)
    ax.set_xlabel("Elapsed (s)", fontsize=8)
    ax.set_ylabel("snd_cwnd", fontsize=8)
    ax.legend(fontsize=7, loc="upper left")


def plot_cwnd_grid(results):
    n    = len(results)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6*cols, 4*rows))
    axes = np.array(axes).flatten()
    for idx, (host, df, sim, ts) in enumerate(results):
        _draw_cwnd(axes[idx], df, sim, ts, host)
    for ax in axes[n:]:
        ax.set_visible(False)
    fig.suptitle("Q3 — Actual vs Predicted snd_cwnd", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.96])
    return fig


def plot_cwnd_individual(results, pdf):
    for host, df, sim, ts in results:
        fig, ax = plt.subplots(figsize=(11, 4.5))
        _draw_cwnd(ax, df, sim, ts, host)
        ax.set_title(f"Q3 — snd_cwnd: {host}", fontsize=10, fontweight="bold")
        fig.tight_layout()
        pdf.savefig(fig); plt.close(fig)


def plot_accuracy(metrics, pdf):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    ax.scatter(metrics["y_true"], metrics["y_pred"],
               alpha=0.5, s=18, color="steelblue", edgecolors="none")
    lim = max(np.abs(metrics["y_true"]).max(), np.abs(metrics["y_pred"]).max()) * 1.1
    ax.plot([-lim, lim], [-lim, lim], "r--", lw=1, label="perfect")
    ax.set_xlabel("True Δcwnd (segments)")
    ax.set_ylabel("Predicted Δcwnd (segments)")
    ax.set_title(f"Accuracy  R²={metrics['r2']:.3f}  RMSE={metrics['rmse']:.2f}")
    ax.legend(fontsize=8)

    ax = axes[1]
    res = metrics["y_pred"] - metrics["y_true"]
    ax.hist(res, bins=30, color="steelblue", edgecolor="white", alpha=0.85)
    ax.axvline(0, color="red", lw=1.2, ls="--")
    ax.set_xlabel("Residual (predicted − true)")
    ax.set_ylabel("Count")
    ax.set_title(f"Residuals  mean={res.mean():.2f}  std={res.std():.2f}")

    fig.suptitle("Q3 — Model evaluation on held-out test set", fontsize=11, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.95])
    pdf.savefig(fig); plt.close(fig)


def plot_weights(model, feature_names, pdf):
    """Show ridge regression coefficients (abs value) as a proxy for importance."""
    w   = np.abs(model.w_)
    idx = np.argsort(w)[-20:]
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(idx)))
    ax.barh([feature_names[i] for i in idx], w[idx], color=colors)
    ax.set_xlabel("|Ridge coefficient|")
    ax.set_title("Q3 — Top-20 feature weights", fontsize=11, fontweight="bold")
    fig.tight_layout()
    pdf.savefig(fig); plt.close(fig)


def plot_eta_vs_cwnd(per_host, pdf):
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = plt.cm.tab10.colors
    for i, (host, df) in enumerate(per_host.items()):
        df2 = add_eta(df).copy()
        df2["delta_cwnd"] = df2["snd_cwnd"].diff().fillna(0)
        ax.scatter(df2["eta"], df2["delta_cwnd"],
                   alpha=0.6, s=22, label=short(host),
                   color=colors[i % len(colors)], edgecolors="none")
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.set_xlabel("η(t)  =  goodput − α·RTT_norm − β·loss_norm")
    ax.set_ylabel("Δsnd_cwnd (segments)")
    ax.set_title("Q3 — Objective η vs congestion window update", fontsize=11, fontweight="bold")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    pdf.savefig(fig); plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Main
# ─────────────────────────────────────────────────────────────────────────────

def run(csv_path, plots_dir, models_dir):
    os.makedirs(plots_dir,  exist_ok=True)
    os.makedirs(models_dir, exist_ok=True)

    per_host = load_data(csv_path)
    log.info(f"Loaded {len(per_host)} destinations")

    feat_dfs = {h: build_features(df) for h, df in per_host.items()}
    combined = pd.concat(feat_dfs.values(), ignore_index=True).fillna(0)
    train_df, test_df = chrono_split(combined, test_frac=0.30)
    log.info(f"Dataset: {len(combined)} samples  |  train={len(train_df)}  test={len(test_df)}")

    log.info("Training Ridge regression (pure NumPy) …")
    model, scaler = train_model(train_df)
    metrics       = eval_model(model, scaler, test_df)
    log.info(f"Test  RMSE={metrics['rmse']:.4f}  R²={metrics['r2']:.4f}")

    # save model weights
    model.save( os.path.join(models_dir, "cwnd_model.npy"))
    scaler.save(os.path.join(models_dir, "cwnd_scaler.npz"))

    hosts   = [h for h in per_host if len(per_host[h]) >= 10][:5]
    results = []
    for host in hosts:
        df         = per_host[host]
        test_start = int(len(df) * 0.70)
        sim        = simulate_cwnd(df, model, scaler, test_start)
        results.append((host, df, sim, test_start))
        log.info(f"  Simulated {host} — test from t={df['elapsed'].iloc[test_start]:.1f}s")

    pdf_path      = os.path.join(plots_dir, "q3_results.pdf")
    feature_names = [c for c in train_df.columns if c != "target"]

    with PdfPages(pdf_path) as pdf:
        pdf.savefig(plot_cwnd_grid(results)); plt.close("all")
        log.info("  Page 1: cwnd overview grid")

        plot_cwnd_individual(results, pdf)
        log.info("  Pages 2–6: per-destination cwnd")

        plot_accuracy(metrics, pdf)
        log.info("  Page 7: accuracy + residuals")

        plot_weights(model, feature_names, pdf)
        log.info("  Page 8: feature weights")

        plot_eta_vs_cwnd(per_host, pdf)
        log.info("  Page 9: η vs Δcwnd")

    log.info(f"Saved: {pdf_path}")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv",    default="q2_goodput_samples.csv")
    parser.add_argument("--plots",  default="plots")
    parser.add_argument("--models", default="models")
    args = parser.parse_args()
    run(args.csv, args.plots, args.models)
