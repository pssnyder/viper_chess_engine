# engine_metrics_app.
# A streamlit app version of the metrics_dashboard.py
# This app is used to display the metrics of the engine and monitor resource usage.
# run using the command streamlit run c:/Users/Pat/Documents/Programming/v7p3r_chess_bot_simple/engine_metrics_app.py

import streamlit as st
import psutil
import os
import time
import glob
import pandas as pd
import yaml
import re
from datetime import datetime

LOGGING_DIR = "../logging"
GAMES_DIR = "../games"
METRICS_DIR = "../metrics"

def load_yaml(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}

def parse_pgn(filepath):
    # Extract result and moves from PGN file
    result, moves = None, []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("[Result"):
                result = line.split('"')[1]
            if not line.startswith("[") and line.strip():
                moves.append(line.strip())
    return {
        "result": result,
        "moves": " ".join(moves)
    }

def parse_log(filepath):
    # Read log file as text
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""

def parse_csv(filepath):
    try:
        return pd.read_csv(filepath)
    except Exception:
        return pd.DataFrame()

def collect_files():
    # Recursively collect all files in logging, games, metrics
    files = []
    for folder in [LOGGING_DIR, GAMES_DIR, METRICS_DIR]:
        for root, _, filenames in os.walk(folder):
            for fn in filenames:
                files.append(os.path.join(root, fn))
    return files

def build_dataset():
    # Build a consolidated dataset from all sources
    files = collect_files()
    # Index configs and games by timestamp
    config_map = {}
    game_map = {}
    for f in files:
        if re.match(r".*eval_game_\d{8}_\d{6}\.ya?ml$", f):
            m = re.search(r"eval_game_(\d{8}_\d{6})\.ya?ml$", f)
            if m:
                config_map[m.group(1)] = f
        elif re.match(r".*eval_game_\d{8}_\d{6}\.pgn$", f):
            m = re.search(r"eval_game_(\d{8}_\d{6})\.pgn$", f)
            if m:
                game_map[m.group(1)] = f

    # Build records for each game/config pair
    records = []
    for ts, game_file in game_map.items():
        config_file = config_map.get(ts)
        game_info = parse_pgn(game_file)
        config_info = load_yaml(config_file) if config_file else {}
        record = {
            "timestamp": ts,
            "game_file": game_file,
            "config_file": config_file,
            "result": game_info.get("result"),
            "moves": game_info.get("moves"),
            **{f"cfg_{k}": v for k, v in (config_info or {}).items()}
        }
        records.append(record)

    # Optionally, add metrics and logs as additional columns
    # Example: add static_metrics.csv if present
    metrics_files = [f for f in files if f.endswith(".csv")]
    metrics_df = pd.concat([parse_csv(f) for f in metrics_files], ignore_index=True) if metrics_files else pd.DataFrame()
    df = pd.DataFrame(records)
    if not metrics_df.empty:
        df = pd.concat([df, metrics_df], axis=1)

    return df

def get_process_metrics():
    proc = psutil.Process(os.getpid())
    cpu = proc.cpu_percent(interval=0.1)
    mem = proc.memory_info().rss / (1024 * 1024)
    threads = proc.num_threads()
    return cpu, mem, threads

st.set_page_config(page_title="AI Performance & Tuning Dashboard", layout="wide")
st.title("AI Performance & Tuning Dashboard")

cpu_placeholder = st.empty()
mem_placeholder = st.empty()
threads_placeholder = st.empty()

update_interval = st.slider("Update interval (seconds)", min_value=1, max_value=10, value=2)

st.markdown("---")

df = build_dataset()
if df.empty:
    st.warning("No data found in logging, games, or metrics folders.")
    st.stop()

st.subheader("Combined Dataset")
st.dataframe(df, use_container_width=True)

# Filtering and analytics
st.sidebar.header("Filter & Query")
result_filter = st.sidebar.multiselect("Game Result", options=df["result"].dropna().unique(), default=list(df["result"].dropna().unique()))
df_filtered = df[df["result"].isin(result_filter)] if result_filter else df

# Show config columns for selection
config_cols = [c for c in df.columns if c.startswith("cfg_")]
if config_cols:
    st.sidebar.subheader("Config Parameter Correlation")
    param = st.sidebar.selectbox("Parameter", config_cols)
    if param:
        # Convert dicts/unhashable types to string for grouping
        if df_filtered[param].apply(lambda x: isinstance(x, dict)).any():
            df_filtered[param] = df_filtered[param].apply(lambda x: str(x) if isinstance(x, dict) else x)
        st.write(f"Correlation between `{param}` and game result:")
        st.bar_chart(df_filtered.groupby([param, "result"]).size().unstack(fill_value=0))

# Analytics: win/loss/draw rates by config
st.subheader("Win/Loss/Draw Rates by Config Parameter")
if config_cols:
    param2 = st.selectbox("Select config parameter for breakdown", config_cols)
    if param2:
        # Convert dicts/unhashable types to string for grouping
        if df_filtered[param2].apply(lambda x: isinstance(x, dict)).any():
            df_filtered[param2] = df_filtered[param2].apply(lambda x: str(x) if isinstance(x, dict) else x)
        summary = df_filtered.groupby([param2, "result"]).size().unstack(fill_value=0)
        st.dataframe(summary)
        st.bar_chart(summary)

# Show raw logs if desired
st.subheader("Raw Log Files")
log_files = [f for f in collect_files() if f.endswith(".log")]
log_choice = st.selectbox("Select log file", log_files)
if log_choice:
    st.text_area("Log Content", parse_log(log_choice), height=300)

# Download combined dataset
st.download_button("Download Combined Dataset (CSV)", df.to_csv(index=False), file_name="combined_ai_dataset.csv")

while True:
    cpu, mem, threads = get_process_metrics()
    cpu_placeholder.metric("CPU Usage (%)", f"{cpu:.2f}")
    mem_placeholder.metric("Memory Usage (MB)", f"{mem:.2f}")
    threads_placeholder.metric("Thread Count", threads)
    time.sleep(update_interval)
