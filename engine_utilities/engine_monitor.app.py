# engine_utilities/engine_monitor.app.py
# TODO: Revise into a lighter weight, Streamlit-based dashboard for analyzing historical chess engine performance metrics over time. Does not provide real time CPU performance monitoring, nor system resource usage, but focuses on game results, config settings, and evaluation rule performance. Also does not provide access to running engines so no log files are available and therefore do not need to be displayed.

import streamlit as st
import psutil
import os
import time
import glob
import pandas as pd
import yaml
import re
from datetime import datetime
import importlib.util
import chess
import sqlite3

GAMES_DIR = "games"

# Dynamically import OpeningBook from engine_utilities/opening_book.py
def load_opening_fens():
    opening_book_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../engine_utilities/opening_book.py")
    )
    spec = importlib.util.spec_from_file_location("opening_book", opening_book_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module. Ensure the file exists at: {opening_book_path}")
    opening_book_mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(opening_book_mod)
    except Exception as e:
        raise ImportError(f"Failed to execute module: {e}")
    book = opening_book_mod.OpeningBook()
    return set(book.book.keys())

OPENING_FENS = load_opening_fens()

# --- Extract FENs from PGN moves ---
def extract_fens_from_moves(moves_str, max_depth=12):
    """Given a moves string, return a list of FENs after each ply up to max_depth."""
    board = chess.Board()
    fens = []
    moves = re.findall(r"\d+\.\s*([^\s]+)(?:\s+([^\s]+))?", moves_str)
    ply = 0
    for move_pair in moves:
        for move in move_pair:
            if move and ply < max_depth:
                try:
                    board.push_san(move)
                    fens.append(board.fen())
                    ply += 1
                except Exception:
                    continue
    return fens

# --- Annotate df with detected opening FEN ---
def annotate_openings(df):
    detected_openings = []
    for idx, row in df.iterrows():
        moves_str = row.get("moves", "")
        fens = extract_fens_from_moves(moves_str)
        found = None
        for fen in fens:
            # Only match up to the first space (piece placement, not castling/en passant/halfmove/fullmove)
            fen_key = " ".join(fen.split(" ")[:4])
            for opening_fen in OPENING_FENS:
                opening_fen_key = " ".join(opening_fen.split(" ")[:4])
                if fen_key == opening_fen_key:
                    found = opening_fen
                    break
            if found:
                break
        detected_openings.append(found)
    df["detected_opening_fen"] = detected_openings
    return df

# --- Match game files ---
def match_game_files():
    """Find and return a list of game files in the GAMES_DIR."""
    game_files = []
    for file in glob.glob(os.path.join(GAMES_DIR, "eval_game_*.pgn")):
        prefix = os.path.basename(file).replace(".pgn", "")
        game_files.append({
            "prefix": prefix,
            "pgn_file": file,
            "config_file": os.path.join(GAMES_DIR, f"{prefix}.yaml"),
            "log_file": os.path.join(GAMES_DIR, f"{prefix}.log"),
        })
    return game_files

# --- Build game dataset ---
def build_game_dataset():
    return fetch_game_data()

def load_yaml(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}

def parse_pgn_metrics(filepath):
    # Extract result, moves, move count, opening, etc.
    result, moves, opening = None, [], None
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("[Result"):
                result = line.split('"')[1]
            if line.startswith("[Opening"):
                opening = line.split('"')[1]
            if not line.startswith("[") and line.strip():
                moves.append(line.strip())
    move_str = " ".join(moves)
    move_count = len(re.findall(r"\d+\.", move_str))
    return {
        "result": result,
        "moves": move_str,
        "move_count": move_count,
        "opening": opening
    }

def parse_log_metrics(filepath):
    # Extract metrics like avg time per move, search depth, nodes, errors, etc.
    if not filepath or not os.path.exists(filepath):
        return {}
    times, depths, nodes, errors = [], [], [], 0
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # Example: "info depth 12 nodes 123456 time 1234"
            m = re.search(r"depth (\d+).*nodes (\d+).*time (\d+)", line)
            if m:
                depths.append(int(m.group(1)))
                nodes.append(int(m.group(2)))
                times.append(int(m.group(3)))
            if "error" in line.lower():
                errors += 1
    avg_time = sum(times) / len(times) if times else None
    avg_depth = sum(depths) / len(depths) if depths else None
    avg_nodes = sum(nodes) / len(nodes) if nodes else None
    return {
        "avg_time_per_move_ms": avg_time,
        "avg_search_depth": avg_depth,
        "avg_nodes": avg_nodes,
        "error_count": errors
    }

def get_database_connection():
    """Establish a connection to the metrics database."""
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../metrics/chess_metrics.db"))
    return sqlite3.connect(db_path)

def fetch_game_data():
    """Fetch game data from the database."""
    connection = get_database_connection()
    query = """
    SELECT gr.game_id, gr.timestamp, gr.winner, gr.game_length, 
           cs.white_ai_type, cs.black_ai_type, cs.white_engine, cs.black_engine
    FROM game_results gr
    LEFT JOIN config_settings cs ON gr.game_id = cs.game_id
    """
    df = pd.read_sql_query(query, connection)
    connection.close()
    return df

# --- Streamlit UI ---

st.set_page_config(page_title="Viper Chess Engine Analysis Dashboard", layout="wide")
st.title("Viper Chess Engine Analysis Dashboard")

df = build_game_dataset()
if df.empty:
    st.warning("No games found in the database.")
    st.stop()

# Summary statistics
st.subheader("Summary Metrics")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Games", len(df))
col2.metric("Win Rate as White", f"{100 * (df['winner'] == '1-0').mean():.0f}%" if 'winner' in df else "N/A")
col3.metric("Win Rate as Black", f"{100 * (df['winner'] == '0-1').mean():.0f}%" if 'winner' in df else "N/A")
col4.metric("Draw Rate", f"{100 * (df['winner'] == '1/2-1/2').mean():.0f}%" if 'winner' in df else "N/A")
col5.metric("Avg Game Length", f"{round(df['game_length'].mean()):.0f} moves" if 'game_length' in df else "N/A")

# Trends over time
st.subheader("Trends Over Time")
if "timestamp" in df and "winner" in df:
    df_sorted = df.sort_values("timestamp")
    win_trend = df_sorted["winner"].eq("1-0").rolling(10, min_periods=1).mean()
    st.line_chart({"Win Rate (last 10)": win_trend})

if "avg_search_depth" in df:
    st.line_chart({"Avg Search Depth": df.sort_values("timestamp")["avg_search_depth"]})

# Config correlation
st.subheader("Config Parameter Correlation")
config_cols = [c for c in df.columns if c.startswith("cfg_")]
if config_cols:
    param = st.selectbox("Select config parameter", config_cols)
    if param and "winner" in df:
        # Convert unhashable types (like dict) to string for grouping
        if df[param].apply(lambda x: not isinstance(x, (str, int, float, bool, type(None)))).any():
            df[param] = df[param].apply(lambda x: str(x) if not isinstance(x, (str, int, float, bool, type(None))) else x)
        st.bar_chart(df.groupby([param, "winner"]).size().unstack(fill_value=0))

# Opening stats # TODO load opening data from engine_utilities/opening_book.py 
if "opening" in df or "detected_opening_fen" in df:
    st.subheader("Most Common Openings (PGN tag or Detected)")
    # Show both PGN opening tag and detected opening FEN
    opening_counts = pd.Series(dtype=int)
    if "opening" in df:
        opening_counts = df["opening"].value_counts()
    if "detected_opening_fen" in df:
        detected_counts = df["detected_opening_fen"].value_counts()
        # Optionally, merge with opening_counts
        opening_counts = opening_counts.add(detected_counts, fill_value=0)
    st.dataframe(opening_counts.head(10))

# Error analysis
if "error_count" in df:
    st.subheader("Games with Errors")
    st.dataframe(df[df["error_count"] > 0][["timestamp", "error_count", "log_file"]])

# Raw data
st.subheader("Raw Game Data")
st.dataframe(df, use_container_width=True)

# Download
st.download_button("Download Dataset (CSV)", df.to_csv(index=False), file_name="chess_engine_eval_dataset.csv")

# --- Correlation Analysis Section ---
st.subheader("Correlation Analysis & Parameter Tuning Insights")

# Sidebar filters
with st.sidebar:
    st.header("Filter Games")
    # Filter by result
    result_options = df["winner"].dropna().unique().tolist()
    selected_results = st.multiselect("Game Result", result_options, default=result_options)
    # Filter by opening
    opening_options = df["opening"].dropna().unique().tolist() if "opening" in df else []
    selected_openings = st.multiselect("Opening", opening_options, default=opening_options if opening_options else None)
    # Filter by config parameter (optional)
    filter_param = st.selectbox("Filter by Config Parameter", ["None"] + config_cols if config_cols else ["None"])
    filter_value = None
    if filter_param != "None":
        unique_vals = df[filter_param].dropna().unique().tolist()
        filter_value = st.selectbox("Value", unique_vals)

# Apply filters
df_corr = df.copy()
if selected_results:
    df_corr = df_corr[df_corr["winner"].isin(selected_results)]
if opening_options and selected_openings:
    df_corr = df_corr[df_corr["opening"].isin(selected_openings)]
if filter_param != "None" and filter_value is not None:
    df_corr = df_corr[df_corr[filter_param] == filter_value]

# --- Config Parameter Correlation ---
st.markdown("#### Win/Draw/Loss Rate by Config Parameter")
if config_cols:
    param = st.selectbox("Select config parameter for correlation", config_cols, key="corr_param")
    # Convert unhashable types to string
    if df_corr[param].apply(lambda x: not isinstance(x, (str, int, float, bool, type(None)))).any():
        df_corr[param] = df_corr[param].apply(lambda x: str(x) if not isinstance(x, (str, int, float, bool, type(None))) else x)
    summary = df_corr.groupby([param, "winner"]).size().unstack(fill_value=0)
    st.dataframe(summary)
    st.bar_chart(summary)

# --- Evaluation Parameter Correlation ---
eval_cols = [c for c in df.columns if c.startswith("cfg_") and any(x in c for x in [
    "bonus", "penalty", "weight", "modifier", "multiplier"
])]
if eval_cols:
    st.markdown("#### Evaluation Parameter Impact")
    eval_param = st.selectbox("Select evaluation parameter", eval_cols, key="eval_param")
    # Convert unhashable types to string
    if df_corr[eval_param].apply(lambda x: not isinstance(x, (str, int, float, bool, type(None)))).any():
        df_corr[eval_param] = df_corr[eval_param].apply(lambda x: str(x) if not isinstance(x, (str, int, float, bool, type(None))) else x)
    # Show win rate, draw rate, avg game length, avg search depth by parameter value
    agg = df_corr.groupby(eval_param).agg(
        games=("winner", "count"),
        win_rate=("winner", lambda x: (x == "1-0").mean()),
        draw_rate=("winner", lambda x: (x == "1/2-1/2").mean()),
        avg_game_length=("game_length", "mean"),
        avg_search_depth=("avg_search_depth", "mean"),
        avg_time_per_move_ms=("avg_time_per_move_ms", "mean")
    ).sort_values("games", ascending=False)
    st.dataframe(agg)
    st.line_chart(agg[["win_rate", "draw_rate", "avg_game_length", "avg_search_depth"]])

# --- Pairwise Correlation Heatmap (numeric config/eval params only) ---
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

numeric_cols = [c for c in df_corr.columns if (str(c).startswith("cfg_") and pd.api.types.is_numeric_dtype(df_corr[c]))]
if numeric_cols:
    st.markdown("#### Pairwise Correlation Heatmap (Numeric Config/Eval Params)")
    corr_matrix = df_corr[numeric_cols + ["game_length", "avg_search_depth", "avg_time_per_move_ms"]].corr()
    fig, ax = plt.subplots(figsize=(min(12, 1+len(corr_matrix.columns)//2), 8))
    sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
    st.pyplot(fig)

# --- Scatter Plot for Custom Parameter vs. Metric ---
st.markdown("#### Custom Parameter vs. Metric Scatter Plot")
scatter_param = st.selectbox("X-axis: Config/Eval Parameter", numeric_cols, key="scatter_param")
scatter_metric = st.selectbox("Y-axis: Metric", ["game_length", "avg_search_depth", "avg_time_per_move_ms"], key="scatter_metric")
if scatter_param and scatter_metric:
    st.scatter_chart(df_corr[[scatter_param, scatter_metric]].dropna())

# --- Sidebar: Specific Config Filters ---
with st.sidebar:
    st.header("Filter by AI Config & Evaluation Rules")
    # AI config fields from your TODO
    ai_fields = [
        "cfg_ai_type", "cfg_ai_color", "cfg_depth", "cfg_use_solutions", "cfg_pst", "cfg_pst_weight",
        "cfg_move_ordering", "cfg_quiescence", "cfg_time_limit", "cfg_engine", "cfg_personality",
        "cfg_ruleset", "cfg_scoring_modifier"
    ]
    eval_fields = [
        "cfg_checkmate_bonus", "cfg_repetition_penalty", "cfg_center_control_bonus", "cfg_knight_activity_bonus",
        "cfg_bishop_activity_bonus", "cfg_king_safety_bonus", "cfg_king_threat_penalty", "cfg_undeveloped_penalty",
        "cfg_check_bonus", "cfg_in_check_penalty", "cfg_capture_bonus", "cfg_castling_bonus", "cfg_en_passant_bonus",
        "cfg_pawn_promotion_bonus", "cfg_passed_pawn_bonus", "cfg_hanging_piece_bonus", "cfg_trapped_piece_penalty",
        "cfg_piece_development_bonus", "cfg_piece_activity_bonus", "cfg_knight_pair_bonus", "cfg_knight_vision_penalty",
        "cfg_pawn_advancement_bonus", "cfg_rook_development_penalty", "cfg_castling_protection_bonus",
        "cfg_castling_protection_penalty", "cfg_material_weight", "cfg_piece_coordination_bonus",
        "cfg_doubled_pawn_penalty", "cfg_isolated_pawn_penalty", "cfg_backward_pawn_penalty", "cfg_bishop_vision_bonus",
        "cfg_tempo_bonus", "cfg_stacked_rooks_bonus", "cfg_coordinated_rooks_bonus", "cfg_stalemate_penalty",
        "cfg_draw_penalty", "cfg_undefended_piece_penalty", "cfg_pawn_structure_bonus", "cfg_file_control_bonus",
        "cfg_open_file_bonus", "cfg_rook_position_bonus", "cfg_exposed_king_penalty", "cfg_piece_mobility_bonus",
        "cfg_checkmate_move_bonus", "cfg_check_move_bonus", "cfg_hash_move_bonus", "cfg_capture_move_bonus",
        "cfg_promotion_move_bonus", "cfg_killer_move_bonus", "cfg_history_move_bonus", "cfg_counter_move_bonus"
    ]
    # Only show filters for fields present in the dataframe
    ai_fields_present = [f for f in ai_fields if f in df.columns]
    eval_fields_present = [f for f in eval_fields if f in df.columns]

    ai_filters = {}
    for f in ai_fields_present:
        vals = df[f].dropna().unique().tolist()
        if vals:
            ai_filters[f] = st.selectbox(f"AI Config: {f.replace('cfg_', '')}", ["All"] + [str(v) for v in sorted(vals)], key=f"ai_{f}")

    eval_filters = {}
    for f in eval_fields_present:
        vals = df[f].dropna().unique().tolist()
        if vals:
            eval_filters[f] = st.selectbox(f"Eval Rule: {f.replace('cfg_', '')}", ["All"] + [str(v) for v in sorted(vals)], key=f"eval_{f}")

# --- Apply specific config filters ---
df_filtered = df.copy()
for f, v in ai_filters.items():
    if v != "All":
        df_filtered = df_filtered[df_filtered[f].astype(str) == v]
for f, v in eval_filters.items():
    if v != "All":
        df_filtered = df_filtered[df_filtered[f].astype(str) == v]

# --- Correlation Table/Plot for Filtered Data ---
st.subheader("Outcome Correlation for Selected Config/Rule Values")
if not df_filtered.empty and "winner" in df_filtered:
    outcome_counts = df_filtered["winner"].value_counts()
    st.write("Game Outcomes (filtered):")
    st.bar_chart(outcome_counts)
    # Show win/draw/loss rates
    st.write({
        "Win Rate (White)": f"{100 * (df_filtered['winner'] == '1-0').mean():.1f}%",
        "Win Rate (Black)": f"{100 * (df_filtered['winner'] == '0-1').mean():.1f}%",
        "Draw Rate": f"{100 * (df_filtered['winner'] == '1/2-1/2').mean():.1f}%"
    })
    # Show average game length and search metrics
    st.write({
        "Avg Game Length": f"{df_filtered['game_length'].mean():.1f}" if 'game_length' in df_filtered else "N/A",
        "Avg Search Depth": f"{df_filtered['avg_search_depth'].mean():.1f}" if 'avg_search_depth' in df_filtered else "N/A",
        "Avg Time/Move (ms)": f"{df_filtered['avg_time_per_move_ms'].mean():.1f}" if 'avg_time_per_move_ms' in df_filtered else "N/A"
    })
else:
    st.info("No games match the selected config/rule filters.")
