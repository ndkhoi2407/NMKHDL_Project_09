"""Shared helpers for the report pages (m1_crawling.md, m2_parsing.md).

Reads only the small files in m1_data/ and m2_data/ (never the real corpus, which is not
in the book repository). Draws interactive charts with plotly; if plotly is not installed
it falls back to matplotlib so that the page still builds.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:                                   # pragma: no cover
    HAS_PLOTLY = False
    import matplotlib.pyplot as plt

MB = 1024 ** 2


# ---------------------------------------------------------------- loading data

def load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path.resolve()}. Run src/make_report_data.py to create the report data, "
            "then commit the m1_data/ and m2_data/ folders to the book repository.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path.resolve()}")
    return pd.read_csv(path)


def get(d, *keys, default=None):
    """get(S, 'timing', 'wall_seconds') -> nested value, or the default when a key is missing."""
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return default if d is None else d


# ---------------------------------------------------------------- formatting

def num(v, nd=2):
    return "Not measured" if v is None or pd.isna(v) else f"{v:,.{nd}f}"


def pct(v, nd=2):
    return "Not measured" if v is None or pd.isna(v) else f"{v * 100:.{nd}f}%"


def quantity(value, unit, nd=2):
    """Attach a unit only to an available numeric measurement."""
    return "Not measured" if value is None or pd.isna(value) else f"{num(value, nd)} {unit}"


def scale(value, divisor):
    return None if value is None else value / divisor


def difference(before, after):
    return None if before is None or after is None else before - after


def mb(v):
    return None if v is None else v / MB


def duration(seconds):
    if seconds is None:
        return "Not measured"
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s ({seconds:,.1f} s)" if h else f"{m}m {s:02d}s ({seconds:,.1f} s)"


def kv_table(rows) -> pd.DataFrame:
    """rows: list of (metric, value) pairs -> two-column DataFrame for display()."""
    return pd.DataFrame([(k, "Not measured" if v is None else str(v)) for k, v in rows], columns=["Metric", "Value"])


# ---------------------------------------------------------------- charts

def _empty(title):
    print(f"[No data to plot: {title}]")


def hist(values, title, xlabel, ylabel="Count", nbins=30):
    s = pd.Series(values).dropna()
    if s.empty:
        return _empty(title)
    if HAS_PLOTLY:
        fig = px.histogram(s.to_frame("x"), x="x", nbins=nbins, title=title)
        fig.update_layout(xaxis_title=xlabel, yaxis_title=ylabel, bargap=0.05)
        fig.show()
    else:
        plt.figure(figsize=(9, 4.5))
        plt.hist(s, bins=nbins, edgecolor="black")
        plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title)
        plt.grid(axis="y", alpha=.3); plt.tight_layout(); plt.show()


def bar(categories, series: dict, title, ylabel="Count", log_y=False):
    """series: {group_name: [values, one per category]} -> grouped bar chart."""
    categories = [str(c) for c in categories]
    if not categories or not series:
        return _empty(title)
    if HAS_PLOTLY:
        fig = go.Figure([go.Bar(name=n, x=categories, y=v) for n, v in series.items()])
        fig.update_layout(barmode="group", title=title, yaxis_title=ylabel,
                          yaxis_type="log" if log_y else "linear")
        fig.show()
    else:
        plt.figure(figsize=(9, 4.5))
        w = 0.8 / len(series)
        for i, (n, v) in enumerate(series.items()):
            plt.bar([x + i * w for x in range(len(categories))], v, w, label=n)
        plt.xticks([x + w * (len(series) - 1) / 2 for x in range(len(categories))], categories, rotation=20)
        if log_y:
            plt.yscale("log")
        plt.ylabel(ylabel); plt.title(title)
        if len(series) > 1:
            plt.legend()
        plt.grid(axis="y", alpha=.3); plt.tight_layout(); plt.show()


def box(df: pd.DataFrame, cols: dict, title, ylabel, log_y=False):
    """cols: {dataframe_column: display_label} -> box plot comparing the columns."""
    long = df[list(cols)].rename(columns=cols).melt(var_name="Group", value_name="v").dropna()
    if long.empty:
        return _empty(title)
    if HAS_PLOTLY:
        fig = px.box(long, x="Group", y="v", points="outliers", title=title, log_y=log_y)
        fig.update_layout(yaxis_title=ylabel)
        fig.show()
    else:
        plt.figure(figsize=(9, 4.5))
        names = list(cols.values())
        plt.boxplot([long.loc[long["Group"] == n, "v"] for n in names], tick_labels=names)
        if log_y:
            plt.yscale("log")
        plt.ylabel(ylabel); plt.title(title)
        plt.grid(axis="y", alpha=.3); plt.tight_layout(); plt.show()


def line(x, y, title, xlabel, ylabel):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if df.empty:
        return _empty(title)
    if HAS_PLOTLY:
        fig = px.line(df, x="x", y="y", title=title)
        fig.update_layout(xaxis_title=xlabel, yaxis_title=ylabel)
        fig.show()
    else:
        plt.figure(figsize=(10, 4.5))
        plt.plot(df["x"], df["y"])
        plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title)
        plt.grid(alpha=.3); plt.tight_layout(); plt.show()
