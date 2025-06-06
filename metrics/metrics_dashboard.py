import os
import glob
import time
import psutil
import dash
from dash import dcc, html, Output, Input
import plotly.graph_objs as go
import pandas as pd

METRICS_DIR = "metrics"
GAMES_DIR = "games"
LOG_DIR = "logging"
LOG_FILES = [
    os.path.join(LOG_DIR, "chess_game.log"),
    os.path.join(LOG_DIR, "puzzle_manager.log"),
    os.path.join(LOG_DIR, "evaluation_engine.log"),
]

# Store previous disk IO and timestamp for speed calculation
_prev_disk_io = {"read_bytes": 0, "write_bytes": 0, "timestamp": time.time()}

# Prime psutil's cpu_percent so subsequent calls are meaningful
psutil.cpu_percent(interval=None)

def parse_pgn_metrics():
    # Parse all eval_game_*.pgn files for static metrics and trend data
    files = glob.glob(os.path.join(GAMES_DIR, "eval_game_*.pgn"))
    total_games = len(files)
    wins, losses, draws = 0, 0, 0
    trend_data = []
    for f in files:
        # Extract timestamp from filename: eval_game_YYYYMMDD_HHMMSS.pgn
        basename = os.path.basename(f)
        dt = None
        try:
            dt_str = basename.replace("eval_game_", "").replace(".pgn", "")
            dt = pd.to_datetime(dt_str, format="%Y%m%d_%H%M%S")
        except Exception:
            dt = None
        result = None
        with open(f, "r", encoding="utf-8", errors="ignore") as pgn:
            for line in pgn:
                if line.startswith("[Result"):
                    result = line.split('"')[1]
                    if result == "1-0":
                        wins += 1
                    elif result == "0-1":
                        losses += 1
                    elif result == "1/2-1/2":
                        draws += 1
                    break
        if dt and result:
            trend_data.append({"datetime": dt, "result": result})
    # Build DataFrame for trend
    if trend_data:
        df = pd.DataFrame(trend_data).sort_values("datetime")
        df["win"] = (df["result"] == "1-0").astype(int)
        df["loss"] = (df["result"] == "0-1").astype(int)
        df["draw"] = (df["result"] == "1/2-1/2").astype(int)
        df["cum_win"] = df["win"].cumsum()
        df["cum_loss"] = df["loss"].cumsum()
        df["cum_draw"] = df["draw"].cumsum()
    else:
        df = pd.DataFrame(columns=["datetime", "cum_win", "cum_loss", "cum_draw"])
    return {
        "total_games": total_games,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "trend_df": df,
    }

def get_system_metrics():
    # Use a blocking interval to get a real CPU usage sample
    return {
        "cpu": psutil.cpu_percent(interval=1),
        "ram": psutil.virtual_memory().percent,
    }

def get_disk_speed():
    global _prev_disk_io
    io = psutil.disk_io_counters()
    if io is None:
        return 0.0, 0.0
    now = time.time()
    elapsed = now - _prev_disk_io["timestamp"] if _prev_disk_io["timestamp"] else 1
    read_speed = (io.read_bytes - _prev_disk_io["read_bytes"]) / elapsed / 1024  # KB/s
    write_speed = (io.write_bytes - _prev_disk_io["write_bytes"]) / elapsed / 1024  # KB/s
    _prev_disk_io = {
        "read_bytes": io.read_bytes,
        "write_bytes": io.write_bytes,
        "timestamp": now
    }
    return max(read_speed, 0), max(write_speed, 0)

def get_temperatures():
    """
    Try to get temperatures from psutil. If not available, try OpenHardwareMonitor WMI, LibreHardwareMonitor WMI,
    or SidebarDiagnostics JSON file. Returns up to 3 temperature sensors.
    """
    temps = []

    # 1. Try psutil (Linux, some Windows)
    sensors = getattr(psutil, "sensors_temperatures", None)
    if sensors is not None:
        try:
            sensors = sensors(fahrenheit=False)
            for label, entries in sensors.items():
                for entry in entries:
                    if getattr(entry, "current", None) is not None and entry.current > 0:
                        temps.append({
                            "label": f"{label} {getattr(entry, 'label', '') or ''}".strip(),
                            "value": entry.current
                        })
            if temps:
                return temps[:3]
        except Exception:
            pass

    # 2. Try LibreHardwareMonitor WMI (more modern, works with more hardware)
    try:
        import platform
        if platform.system() == "Windows":
            import wmi
            # Try LibreHardwareMonitor first
            for namespace in [r"root\LibreHardwareMonitor", r"root\OpenHardwareMonitor"]:
                try:
                    w = wmi.WMI(namespace=namespace)
                    for sensor in w.Sensor():
                        if getattr(sensor, "SensorType", "") == "Temperature" and getattr(sensor, "Value", None) is not None:
                            label = f"{getattr(sensor, 'HardwareType', '')} {getattr(sensor, 'Name', '')}".strip()
                            value = float(sensor.Value)
                            if value > 0:
                                temps.append({"label": label, "value": value})
                    if temps:
                        return temps[:3]
                except Exception:
                    continue
    except ImportError:
        pass
    except Exception:
        pass

    # 3. Try SidebarDiagnostics (Windows) via its JSON file if available
    try:
        sidebar_diag_path = os.path.expandvars(r"%LOCALAPPDATA%\Packages\SidebarDiagnostics.SidebarDiagnostics_gq1r6bfs4xg00\LocalState\data.json")
        if not os.path.exists(sidebar_diag_path):
            # Try common alternative install path (non-store version)
            sidebar_diag_path = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SidebarDiagnostics\data.json")
        if os.path.exists(sidebar_diag_path):
            import json
            with open(sidebar_diag_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for sensor in data.get("Sensors", []):
                    if sensor.get("Type") == "Temperature" and sensor.get("Value") is not None:
                        value = float(sensor["Value"])
                        if value > 0:
                            temps.append({
                                "label": sensor.get("Name", "Sensor"),
                                "value": value
                            })
            if temps:
                return temps[:3]
    except Exception:
        pass

    # 4. Try Windows Management Instrumentation (WMI) for CPU temp (very limited, often not available)
    try:
        import platform
        if platform.system() == "Windows":
            import wmi
            w = wmi.WMI(namespace="root\\WMI")
            for sensor in w.MSAcpi_ThermalZoneTemperature():
                # Value is in tenths of Kelvin
                kelvin = float(sensor.CurrentTemperature)
                celsius = kelvin / 10.0 - 273.15
                if celsius > 0:
                    temps.append({"label": "CPU (WMI)", "value": round(celsius, 1)})
            if temps:
                return temps[:3]
    except ImportError:
        pass
    except Exception:
        pass

    return temps

def tail_logfile(filepath, max_lines=1000, max_bytes=10*1024*1024):
    # Read last max_lines lines, up to max_bytes from end
    if not os.path.exists(filepath):
        return ""
    size = os.path.getsize(filepath)
    with open(filepath, "rb") as f:
        if size > max_bytes:
            f.seek(-max_bytes, os.SEEK_END)
        lines = f.read().decode(errors="ignore").splitlines()[-max_lines:]
    return "\n".join(lines)

def get_process_metrics():
    # Get current process CPU %, memory usage (MB), and thread count
    proc = psutil.Process(os.getpid())
    cpu = proc.cpu_percent(interval=0.1)
    mem = proc.memory_info().rss / (1024 * 1024)
    threads = proc.num_threads()
    return cpu, mem, threads

# Dash app
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H1("Chess Engine Metrics Dashboard"),
    html.Div([
        html.Div([
            html.H2("Static Metrics"),
            html.Div(id="static-metrics"),
        ], style={"flex": "1"}),
        html.Div([
            dcc.Graph(id="static-trend-graph", style={"height": "300px"}),
        ], style={"flex": "2"}),
    ], style={"display": "flex", "flexDirection": "row", "alignItems": "flex-start"}),
    html.H2("Live System Metrics"),
    dcc.Interval(id="interval", interval=4000, n_intervals=0),  # 4s for system metrics
    html.Div([
        dcc.Graph(id="cpu-graph", style={"minWidth": "260px", "flex": "1", "margin": "0 10px"}),
        dcc.Graph(id="ram-graph", style={"minWidth": "260px", "flex": "1", "margin": "0 10px"}),
        dcc.Graph(id="disk-graph", style={"minWidth": "260px", "flex": "1", "margin": "0 10px"}),
    ], style={"display": "flex", "flexDirection": "row", "justifyContent": "center", "alignItems": "flex-start"}),
    # Replace temperature gauges with process metrics
    html.Div([
        dcc.Graph(id="proc-cpu-graph", style={"minWidth": "260px", "flex": "1", "margin": "0 10px"}),
        dcc.Graph(id="proc-mem-graph", style={"minWidth": "260px", "flex": "1", "margin": "0 10px"}),
        dcc.Graph(id="proc-thread-graph", style={"minWidth": "260px", "flex": "1", "margin": "0 10px"}),
    ], style={"display": "flex", "flexDirection": "row", "justifyContent": "center", "alignItems": "flex-start"}),
    html.H2("Live Log Tail"),
    dcc.Dropdown(
        id="logfile-dropdown",
        options=[{"label": os.path.basename(f), "value": f} for f in LOG_FILES],
        value=LOG_FILES[0],
        clearable=False,
    ),
    dcc.Interval(id="log-interval", interval=5000, n_intervals=0),  # 5s for log tail
    html.Pre(id="log-tail", style={"height": "300px", "overflowY": "scroll", "background": "#eee"}),
])

@app.callback(
    [Output("static-metrics", "children"),
     Output("static-trend-graph", "figure")],
    Input("interval", "n_intervals"),
)
def update_static_metrics(_):
    metrics = parse_pgn_metrics()
    # Save to metrics file
    os.makedirs(METRICS_DIR, exist_ok=True)
    metrics_file = os.path.join(METRICS_DIR, "static_metrics.csv")
    pd.DataFrame([metrics]).to_csv(metrics_file, index=False)
    # Trend graph
    df = metrics["trend_df"]
    if not df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["datetime"], y=df["cum_win"], mode="lines+markers", name="Wins", line=dict(color="green")))
        fig.add_trace(go.Scatter(x=df["datetime"], y=df["cum_loss"], mode="lines+markers", name="Losses", line=dict(color="red")))
        fig.add_trace(go.Scatter(x=df["datetime"], y=df["cum_draw"], mode="lines+markers", name="Draws", line=dict(color="gray")))
        fig.update_layout(title="Cumulative Results Over Time", xaxis_title="Date/Time", yaxis_title="Count", height=300, margin=dict(t=40, b=0, l=0, r=0))
    else:
        fig = go.Figure()
        fig.update_layout(title="No Data", height=300, margin=dict(t=40, b=0, l=0, r=0))
    return html.Ul([
        html.Li(f"Total Games: {metrics['total_games']}"),
        html.Li(f"Wins: {metrics['wins']}"),
        html.Li(f"Losses: {metrics['losses']}"),
        html.Li(f"Draws: {metrics['draws']}"),
    ]), fig

@app.callback(
    [Output("cpu-graph", "figure"),
     Output("ram-graph", "figure"),
     Output("disk-graph", "figure"),
     Output("proc-cpu-graph", "figure"),
     Output("proc-mem-graph", "figure"),
     Output("proc-thread-graph", "figure")],
    Input("interval", "n_intervals"),
)
def update_system_graphs(_):
    sys_metrics = get_system_metrics()
    read_speed, write_speed = get_disk_speed()
    proc_cpu, proc_mem, proc_threads = get_process_metrics()
    gauge_layout = dict(height=250, width=250, margin=dict(t=40, b=0, l=0, r=0))
    thresholds = [
        {"range": [0, 50], "color": "lightgreen"},
        {"range": [50, 75], "color": "yellow"},
        {"range": [75, 90], "color": "orange"},
        {"range": [90, 100], "color": "red"},
    ]
    cpu_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=sys_metrics["cpu"],
        title={"text": "CPU %"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "blue"},
            "steps": thresholds,
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))
    ram_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=sys_metrics["ram"],
        title={"text": "RAM %"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "blue"},
            "steps": thresholds,
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))
    cpu_fig.update_layout(**gauge_layout)
    ram_fig.update_layout(**gauge_layout)

    # Disk performance: show read/write speed as a bar chart
    disk_fig = go.Figure(data=[
        go.Bar(name="Read KB/s", x=["Read"], y=[read_speed], marker_color="blue"),
        go.Bar(name="Write KB/s", x=["Write"], y=[write_speed], marker_color="green"),
    ])
    disk_fig.update_layout(
        title="Disk Performance (KB/s)",
        barmode="group",
        height=250,
        width=250,
        margin=dict(t=40, b=0, l=0, r=0),
        yaxis=dict(title="KB/s", rangemode="tozero")
    )

    # Process CPU usage gauge
    proc_cpu_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=proc_cpu,
        title={"text": "Process CPU %"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "purple"},
            "steps": thresholds,
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))
    proc_cpu_fig.update_layout(**gauge_layout)

    # Process memory usage gauge
    proc_mem_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=proc_mem,
        title={"text": "Process Memory (MB)"},
        gauge={
            "axis": {"range": [0, 2048]},
            "bar": {"color": "orange"},
        }
    ))
    proc_mem_fig.update_layout(**gauge_layout)

    # Process thread count gauge
    proc_thread_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=proc_threads,
        title={"text": "Process Threads"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "teal"},
        }
    ))
    proc_thread_fig.update_layout(**gauge_layout)

    return cpu_fig, ram_fig, disk_fig, proc_cpu_fig, proc_mem_fig, proc_thread_fig

@app.callback(
    Output("log-tail", "children"),
    [Input("log-interval", "n_intervals"), Input("logfile-dropdown", "value")]
)
def update_log_tail(_, logfile):
    return tail_logfile(logfile)

if __name__ == "__main__":
    app.run(debug=True)