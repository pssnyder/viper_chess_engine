# metrics_dashboard.py
# A locally running dashboard to visualize chess engine metrics, system performance, and log files while actively analyzing the engine's performance.

import os
import glob
import time
import psutil
import dash
from dash import dcc, html, Output, Input
import plotly.graph_objs as go
import pandas as pd
import re
from collections import defaultdict
import numpy as np
from metrics_store import MetricsStore
import threading
import yaml
import atexit

METRICS_DIR = "metrics"
GAMES_DIR = "games"
LOG_DIR = "logging"
LOG_FILES = [
    os.path.join(LOG_DIR, "chess_game.log"),
    os.path.join(LOG_DIR, "evaluation_engine.log"),
]

# Store previous disk IO and timestamp for speed calculation
_prev_disk_io = {"read_bytes": 0, "write_bytes": 0, "timestamp": time.time()}

# Prime psutil's cpu_percent so subsequent calls are meaningful
psutil.cpu_percent(interval=None)

# Initialize the metrics store globally
metrics_store = MetricsStore()

# Start data collection in background
def start_metrics_collection():
    # Collect initial data
    metrics_store.collect_all_data()
    # Start periodic collection (every 30 seconds)
    metrics_store.start_collection(interval=30)

# Start collection in a background thread to avoid blocking the dashboard
collection_thread = threading.Thread(target=start_metrics_collection, daemon=True)
collection_thread.start()

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

class LogAnalyzer:
    """Analyzes chess engine log files to extract structured data and metrics."""
    
    def __init__(self):
        self.log_entries = []
        self.metrics_by_function = defaultdict(list)
        self.metrics_by_label = defaultdict(list)
        self.metrics_by_side = {'w': defaultdict(list), 'b': defaultdict(list)}
        self.function_counts = defaultdict(int)
        self.label_counts = defaultdict(int)
        self.common_patterns = {}
        self.uncommon_messages = []
        self.message_frequency = defaultdict(int)
        
    def parse_log_file(self, filepath, max_lines=10000):
        """Parse a log file and extract structured data from it."""
        if not os.path.exists(filepath):
            return []
            
        log_data = []
        try:
            with open(filepath, 'r', errors='ignore') as f:
                lines = f.readlines()[-max_lines:]  # Read last max_lines
                
            for line in lines:
                entry = self._parse_log_line(line)
                if entry:
                    log_data.append(entry)
                    self._categorize_entry(entry)
                    
            # Identify common and uncommon patterns
            self._identify_patterns()
            
        except Exception as e:
            print(f"Error parsing log file {filepath}: {e}")
            
        self.log_entries = log_data
        return log_data
    
    def _parse_log_line(self, line):
        """Parse a single log line into structured data."""
        # Match pattern: "16:25:14 | _calculate_score | King safety score: 0.000 | FEN: fen_string"
        pattern = r'(\d{2}:\d{2}:\d{2}) \| (\w+) \| (.*?)(: [-\d\.]+)? \| FEN: (.*)'
        match = re.match(pattern, line)
        
        if match:
            time, function, label, value_part, fen = match.groups()
            
            # Extract the value if it exists
            value = None
            if value_part:
                value = float(value_part.replace(': ', ''))
                
            # Extract side from FEN
            side = 'w'  # Default to white
            if ' b ' in fen or fen.endswith(' b'):
                side = 'b'
                
            return {
                'time': time,
                'function': function,
                'label': label,
                'value': value,
                'fen': fen,
                'side': side,
                'raw': line.strip()
            }
        else:
            # For lines that don't match the main pattern, try a simpler one
            simple_pattern = r'(\d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)'
            match = re.match(simple_pattern, line)
            if match:
                time, function, message = match.groups()
                self.message_frequency[message.strip()] += 1
                return {
                    'time': time,
                    'function': function,
                    'message': message.strip(),
                    'raw': line.strip()
                }
        return None
    
    def _categorize_entry(self, entry):
        """Categorize log entry into various metrics collections."""
        if 'function' not in entry:
            return
            
        self.function_counts[entry['function']] += 1
        
        # Only process entries with numeric values
        if 'value' in entry and entry['value'] is not None:
            self.metrics_by_function[entry['function']].append(entry)
            
            if 'label' in entry:
                label = entry['label']
                self.label_counts[label] += 1
                self.metrics_by_label[label].append(entry)
                
                # Categorize by side
                if 'side' in entry:
                    side = entry['side']
                    self.metrics_by_side[side][label].append(entry)
    
    def _identify_patterns(self):
        """Identify common and uncommon patterns in the log data."""
        # Consider messages that appear >= 3 times as common
        threshold = 3
        
        self.common_patterns = {
            msg: count for msg, count in self.message_frequency.items()
            if count >= threshold
        }
        
        self.uncommon_messages = [
            msg for msg, count in self.message_frequency.items()
            if count < threshold
        ]
    
    def get_metrics_for_function(self, function_name):
        """Get all metrics for a specific function."""
        return self.metrics_by_function.get(function_name, [])
    
    def get_metrics_for_label(self, label):
        """Get all metrics for a specific label."""
        return self.metrics_by_label.get(label, [])
    
    def get_metrics_by_side(self, side):
        """Get all metrics for a specific side (w/b)."""
        return self.metrics_by_side.get(side, defaultdict(list))
    
    def get_side_performance_metrics(self, side):
        """
        Retrieve performance metrics for a specific side ('w' for white, 'b' for black).
        """
        metrics = []
        side_metrics = self.get_metrics_by_side(side)
        
        for label, entries in side_metrics.items():
            # Calculate average value
            if entries:
                values = [entry['value'] for entry in entries if 'value' in entry and entry['value'] is not None]
                if values:
                    avg_value = sum(values) / len(values)
                    metrics.append({
                        'label': label,
                        'avg_value': avg_value,
                        'count': len(values)
                    })
        
        return metrics
    
    def get_statistics(self, metric_list):
        """Calculate statistics for a list of metric entries with values."""
        values = [entry['value'] for entry in metric_list if 'value' in entry and entry['value'] is not None]
        
        if not values:
            return {'count': 0, 'avg': None, 'min': None, 'max': None, 'latest': None}
            
        return {
            'count': len(values),
            'avg': np.mean(values),
            'min': min(values),
            'max': max(values),
            'latest': values[-1]
        }
    
    def get_top_metrics(self, n=5, by_side=False):
        """Get top N most frequently occurring metrics."""
        if by_side:
            white_top = sorted(
                [(label, len(entries)) for label, entries in self.metrics_by_side['w'].items()],
                key=lambda x: x[1], reverse=True
            )[:n]
            
            black_top = sorted(
                [(label, len(entries)) for label, entries in self.metrics_by_side['b'].items()],
                key=lambda x: x[1], reverse=True
            )[:n]
            
            return {'w': white_top, 'b': black_top}
        else:
            return sorted(
                [(label, len(entries)) for label, entries in self.metrics_by_label.items()],
                key=lambda x: x[1], reverse=True
            )[:n]
    
    def get_errors_and_warnings(self):
        """Extract potential errors and warnings from logs."""
        errors = []
        for entry in self.log_entries:
            if 'message' in entry and ('error' in entry['message'].lower() or 
                                       'warning' in entry['message'].lower() or
                                       'exception' in entry['message'].lower()):
                errors.append(entry)
        return errors


# Dynamically load AI types from the config.yaml file
# Load AI types from config.yaml
with open("config.yaml", "r") as config_file:
    config_data = yaml.safe_load(config_file)
    AI_TYPES = config_data.get("ai_types", [])

# Dash app
app = dash.Dash(__name__)
app.layout = html.Div([
    html.Div([
        html.H1("Viper Chess Engine Dashboard", style={"textAlign": "center", "marginBottom": "20px"}),
    ]),

    # Condensed system metrics into one row
    html.Div([
        dcc.Interval(id="interval", interval=4000, n_intervals=0),
        html.Div([
            html.Div([
                dcc.Graph(id="cpu-graph", style={"height": "150px"}),
            ], style={"flex": "1", "margin": "0 10px"}),
            html.Div([
                dcc.Graph(id="ram-graph", style={"height": "150px"}),
            ], style={"flex": "1", "margin": "0 10px"}),
            html.Div([
                dcc.Graph(id="disk-graph", style={"height": "150px"}),
            ], style={"flex": "1", "margin": "0 10px"}),
        ], style={"display": "flex", "flexDirection": "row", "justifyContent": "center", "alignItems": "flex-start"}),
    ], style={"marginBottom": "30px"}),

    # Process metrics row - Added back missing components
    html.Div([
        html.Div([
            dcc.Graph(id="proc-cpu-graph", style={"height": "150px"}),
        ], style={"flex": "1", "margin": "0 10px"}),
        html.Div([
            dcc.Graph(id="proc-mem-graph", style={"height": "150px"}),
        ], style={"flex": "1", "margin": "0 10px"}),
        html.Div([
            dcc.Graph(id="proc-thread-graph", style={"height": "150px"}),
        ], style={"flex": "1", "margin": "0 10px"}),
    ], style={"display": "flex", "flexDirection": "row", "justifyContent": "center", "alignItems": "flex-start", "marginBottom": "30px"}),

    # Static metrics section
    html.Div([
        html.Div([
            html.H2("Static Metrics", style={"textAlign": "center"}),
            html.Div(id="static-metrics", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], style={"flex": "1", "marginRight": "20px"}),
        html.Div([
            dcc.Graph(id="static-trend-graph", style={"height": "300px"}),
        ], style={"flex": "2"}),
    ], style={"display": "flex", "flexDirection": "row", "alignItems": "flex-start", "marginBottom": "30px"}),

    # Smart Log Analysis section
    html.Div([
        html.Div([
            html.H3("Analysis by Side", style={"textAlign": "center"}),
            dcc.Dropdown(
                id="side-selector",
                options=[
                    {"label": "White", "value": "white"},
                    {"label": "Black", "value": "black"}
                ],
                value="white",
                clearable=False,
                style={"marginBottom": "10px"}
            ),
            dcc.Dropdown(
                id="ai-type-selector",
                options=[
                    {"label": ai_type.capitalize(), "value": ai_type} for ai_type in AI_TYPES
                ],
                value="type1",
                clearable=False,
                style={"marginBottom": "10px"}
            ),
            html.Div(id="side-analysis", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], style={"flex": "1", "marginRight": "20px"}),

        html.Div([
            html.H3("Top Metrics", style={"textAlign": "center"}),
            html.Div(id="top-metrics", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], style={"flex": "1", "marginRight": "20px"}),

        html.Div([
            html.H3("Potential Issues", style={"textAlign": "center"}),
            html.Div(id="log-issues", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], style={"flex": "1"}),
    ], style={"display": "flex", "flexDirection": "row", "gap": "20px", "marginBottom": "30px"}),

    # Metrics Trends section
    html.Div([
        html.H3("Metrics Trends", style={"textAlign": "center"}),
        dcc.Graph(id="metrics-trend-graph"),
    ], style={"marginBottom": "30px"}),

    # Live Log Tail section
    html.Div([
        html.H3("Live Log Tail", style={"textAlign": "center"}),
        dcc.Dropdown(
            id="logfile-dropdown",
            options=[{"label": os.path.basename(f), "value": f} for f in LOG_FILES],
            value=LOG_FILES[0],
            clearable=False,
        ),
        dcc.Interval(id="log-interval", interval=5000, n_intervals=0),
        dcc.Interval(id="log-analysis-interval", interval=5000, n_intervals=0),  # Missing component added
        html.Pre(id="log-tail", style={"height": "300px", "overflowY": "scroll", "background": "#eee", "padding": "10px", "borderRadius": "5px"}),
    ]),
], style={"fontFamily": "Arial, sans-serif", "padding": "20px"})

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
    
    # Smaller gauge layout for condensed metrics
    gauge_layout_dict = dict(height=140, width=140, margin=dict(t=25, b=0, l=0, r=0))
    
    thresholds = [
        {"range": [0, 50], "color": "lightgreen"},
        {"range": [50, 75], "color": "yellow"},
        {"range": [75, 90], "color": "orange"},
        {"range": [90, 100], "color": "red"},
    ]
    
    # Create system metrics figures with more compact layout
    cpu_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=sys_metrics["cpu"],
        title={"text": "CPU %", "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "blue"},
            "steps": thresholds,
            "threshold": {
                "line": {"color": "red", "width": 2},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))
    
    ram_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=sys_metrics["ram"],
        title={"text": "RAM %", "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "blue"},
            "steps": thresholds,
            "threshold": {
                "line": {"color": "red", "width": 2},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))
    
    # Apply compact layout - Fix: Use individual parameters instead of unpacking dict
    cpu_fig.update_layout(
        height=gauge_layout_dict["height"],
        width=gauge_layout_dict["width"],
        margin=gauge_layout_dict["margin"]
    )
    
    ram_fig.update_layout(
        height=gauge_layout_dict["height"],
        width=gauge_layout_dict["width"],
        margin=gauge_layout_dict["margin"]
    )

    # Disk performance: show read/write speed as a bar chart
    disk_fig = go.Figure(data=[
        go.Bar(name="Read", x=["KB/s"], y=[read_speed], marker_color="blue"),
        go.Bar(name="Write", x=["KB/s"], y=[write_speed], marker_color="green"),
    ])
    disk_fig.update_layout(
        title={"text": "Disk I/O", "font": {"size": 14}},
        barmode="group",
        height=gauge_layout_dict["height"],
        width=gauge_layout_dict["width"],
        margin=gauge_layout_dict["margin"],
        showlegend=False
    )

    # Process CPU usage gauge
    proc_cpu_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=proc_cpu,
        title={"text": "Proc CPU", "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "purple"},
            "steps": thresholds,
            "threshold": {
                "line": {"color": "red", "width": 2},
                "thickness": 0.75,
                "value": 90
            }
        }
    ))

    # Process memory usage gauge
    proc_mem_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=proc_mem,
        title={"text": "Proc MB", "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 1024]},
            "bar": {"color": "orange"},
        }
    ))

    # Process thread count gauge
    proc_thread_fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=proc_threads,
        title={"text": "Threads", "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 50]},
            "bar": {"color": "teal"},
        }
    ))

    # Apply compact layout to process gauges - Fix: Use individual parameters
    proc_cpu_fig.update_layout(
        height=gauge_layout_dict["height"],
        width=gauge_layout_dict["width"],
        margin=gauge_layout_dict["margin"]
    )
    
    proc_mem_fig.update_layout(
        height=gauge_layout_dict["height"],
        width=gauge_layout_dict["width"],
        margin=gauge_layout_dict["margin"]
    )
    
    proc_thread_fig.update_layout(
        height=gauge_layout_dict["height"],
        width=gauge_layout_dict["width"],
        margin=gauge_layout_dict["margin"]
    )

    return cpu_fig, ram_fig, disk_fig, proc_cpu_fig, proc_mem_fig, proc_thread_fig

@app.callback(
    Output("log-tail", "children"),
    [Input("log-interval", "n_intervals"), Input("logfile-dropdown", "value")]
)
def update_log_tail(_, logfile):
    return tail_logfile(logfile)

@app.callback(
    [Output("side-analysis", "children"),
     Output("top-metrics", "children"),
     Output("log-issues", "children"),
     Output("metrics-trend-graph", "figure")],
    [Input("log-analysis-interval", "n_intervals"),
     Input("logfile-dropdown", "value")]
)
def update_log_analysis(_, log_file):
    # We'll still use the LogAnalyzer for immediate log file analysis
    analyzer = LogAnalyzer()
    analyzer.parse_log_file(log_file)
    
    # Side analysis - now using both live data and stored metrics
    side_analysis = []
    for side, label in [('w', "White"), ('b', "Black")]:
        # Get stored metrics for this side
        stored_metrics = metrics_store.get_side_performance_metrics(side)
        
        # Live metrics from the analyzer
        metrics = analyzer.get_metrics_by_side(side)
        
        # Combine metrics (prioritize live data)
        combined_metrics = {}
        for metric in stored_metrics:
            metric_name = metric['label']
            combined_metrics[metric_name] = {
                'avg': metric['avg_value'],
                'count': metric['count']
            }
        
        # Add metrics from live analysis
        for metric_name, entries in metrics.items():
            if len(entries) >= 3:  # Skip metrics with too few entries
                stats = analyzer.get_statistics(entries)
                if stats['avg'] is not None:
                    combined_metrics[metric_name] = stats
        
        # Create UI components
        content_components = []
        content_components.append(html.H4(f"{label} Side Metrics"))
        
        # Show metrics with proper formatting
        for metric_name, stats in sorted(combined_metrics.items(), key=lambda x: x[0]):
            if 'min' in stats and 'max' in stats and 'latest' in stats:
                # Full stats available
                metric_div = html.Div([
                    html.B(f"{metric_name}:"),
                    html.Span(f" Avg: {stats['avg']:.3f}, Min: {stats['min']:.3f}, Max: {stats['max']:.3f}, Latest: {stats['latest']:.3f}")
                ])
            else:
                # Basic stats only
                metric_div = html.Div([
                    html.B(f"{metric_name}:"),
                    html.Span(f" Avg: {stats['avg']:.3f}, Count: {stats['count']}")
                ])
            content_components.append(metric_div)
        
        side_analysis.append(html.Div(content_components, style={"marginBottom": "15px"}))
    
    # Top metrics - combine live and stored data
    top_metrics = []
    # Get functions from analyzer
    for function, count in sorted(analyzer.function_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        metrics = analyzer.get_metrics_for_function(function)
        if metrics:
            stats = analyzer.get_statistics(metrics)
            if stats['avg'] is not None:
                top_metrics.append(html.Div([
                    html.B(f"{function} ({count} calls):"),
                    html.Span(f" Avg: {stats['avg']:.3f}, Range: {stats['min']:.3f} to {stats['max']:.3f}")
                ]))
    
    # Enhanced Issues Display - now using both live data and stored errors
    # Get stored errors
    stored_errors = metrics_store.get_errors_and_warnings(limit=10)
    # Get live errors
    live_errors = analyzer.get_errors_and_warnings()
    
    # Combine errors (prioritize live data)
    all_errors = stored_errors.copy()
    live_error_texts = [e.get('raw', '') for e in live_errors]
    for stored_error in stored_errors:
        # Safely access the 'raw' key with a default value
        if stored_error.get('raw', '') not in live_error_texts:
            all_errors.append(stored_error)
    
    # Limit to top 10
    all_errors = all_errors[:10]
    
    # Get uncommon messages from analyzer
    uncommon = analyzer.uncommon_messages[:10]  # Define the variable that was missing
    
    # Prepare error display
    issues = []
    if all_errors:
        error_items = []
        for error in all_errors:
            # Determine if it's an error, warning, or exception
            message_type = "Error"
            message_color = "#ff5252"  # Red for errors
            
            if 'message' in error:
                message = error['message']
                if isinstance(message, str):
                    if 'warning' in message.lower():
                        message_type = "Warning"
                        message_color = "#ffb300"  # Amber for warnings
                    elif 'exception' in message.lower():
                        message_type = "Exception"
                        message_color = "#d50000"  # Deep red for exceptions
            
            # Format the entry for clearer display
            time = error.get('time', '')
            function = error.get('function', '')
            message = error.get('message', error.get('raw', ''))
            
            # Create a formatted message item with improved styling
            error_items.append(html.Div([
                html.Span(f"{time} ", style={"color": "#757575", "fontSize": "0.9em"}),
                html.Span(f"[{function}] ", style={"color": "#2196f3", "fontWeight": "bold"}),
                html.Span(f"{message_type}: ", style={"color": message_color, "fontWeight": "bold"}),
                html.Span(f"{message}")
            ], style={"marginBottom": "5px", "padding": "5px", "borderLeft": f"3px solid {message_color}", "backgroundColor": "#f5f5f5"}))
        
        issues.append(html.Div([
            html.H4("Errors/Warnings:"),
            html.Div(error_items, style={"maxHeight": "250px", "overflowY": "auto"})
        ]))
    
    if uncommon:
        uncommon_items = []
        for msg in uncommon:  # Limit to 10 uncommon messages
            # Extract time and function if possible using regex
            match = re.match(r'(\d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)', msg)
            if match:
                time, function, message = match.groups()
                uncommon_items.append(html.Div([
                    html.Span(f"{time} ", style={"color": "#757575", "fontSize": "0.9em"}),
                    html.Span(f"[{function}] ", style={"color": "#2196f3", "fontWeight": "bold"}),
                    html.Span(f"{message}")
                ], style={"marginBottom": "5px", "padding": "5px", "borderLeft": "3px solid #9e9e9e", "backgroundColor": "#f5f5f5"}))
            else:
                uncommon_items.append(html.Div(msg, style={"marginBottom": "5px", "padding": "5px", "borderLeft": "3px solid #9e9e9e", "backgroundColor": "#f5f5f5"}))
        
        issues.append(html.Div([
            html.H4("Uncommon Messages:"),
            html.Div(uncommon_items, style={"maxHeight": "200px", "overflowY": "auto"})
        ]))
    
    # Trend graph - use store data for more robust trends
    fig = go.Figure()
    
    # Get metrics trends from store
    white_trend_data = metrics_store.get_metrics_trend_data("King safety score", side='w', limit=100)
    black_trend_data = metrics_store.get_metrics_trend_data("King safety score", side='b', limit=100)
    
    # Add white trend line if we have data
    if white_trend_data:
        # Parse timestamps and sort by timestamp
        times = [pd.to_datetime(item['timestamp']) for item in white_trend_data]
        values = [item['metric_value'] for item in white_trend_data]
        # Sort by timestamp
        data_pairs = sorted(zip(times, values), key=lambda x: x[0])
        if data_pairs:
            times, values = zip(*data_pairs)
            fig.add_trace(go.Scatter(
                x=times, 
                y=values, 
                mode='lines+markers',
                name=f"White: King Safety",
                line=dict(color='blue')
            ))
    
    # Add black trend line if we have data
    if black_trend_data:
        # Parse timestamps and sort by timestamp
        times = [pd.to_datetime(item['timestamp']) for item in black_trend_data]
        values = [item['metric_value'] for item in black_trend_data]
        # Sort by timestamp
        data_pairs = sorted(zip(times, values), key=lambda x: x[0])
        if data_pairs:
            times, values = zip(*data_pairs)
            fig.add_trace(go.Scatter(
                x=times, 
                y=values, 
                mode='lines+markers',
                name=f"Black: King Safety",
                line=dict(color='red')
            ))
    
    # If no store data, fall back to analyzer's data
    if not white_trend_data and not black_trend_data:
        top_metrics_data = analyzer.get_top_metrics(n=3, by_side=True)
        
        # Add white side metrics
        if isinstance(top_metrics_data, dict) and 'w' in top_metrics_data:
            white_metrics = top_metrics_data.get('w', [])
            for label, _ in white_metrics:
                entries = analyzer.metrics_by_side.get('w', {}).get(label, [])
                if len(entries) >= 5:  # Only show metrics with enough data points
                    times = [pd.to_datetime(e['time']) for e in entries]
                    values = [e['value'] for e in entries]
                    fig.add_trace(go.Scatter(
                        x=times, 
                        y=values, 
                        mode='lines+markers',
                        name=f"White: {label}",
                        line=dict(color='blue')
                    ))
        
        # Add black side metrics
        if isinstance(top_metrics_data, dict) and 'b' in top_metrics_data:
            black_metrics = top_metrics_data.get('b', [])
            for label, _ in black_metrics:
                entries = analyzer.metrics_by_side.get('b', {}).get(label, [])
                if len(entries) >= 5:  # Only show metrics with enough data points
                    times = [pd.to_datetime(e['time']) for e in entries]
                    values = [e['value'] for e in entries]
                    fig.add_trace(go.Scatter(
                        x=times, 
                        y=values, 
                        mode='lines+markers',
                        name=f"Black: {label}",
                        line=dict(color='red')
                    ))
    
    fig.update_layout(
        title="Metrics Trends Over Time",
        xaxis_title="Time",
        yaxis_title="Value",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=40, b=0, l=0, r=0)
    )
    
    return side_analysis, top_metrics, issues, fig

# Update the static metrics to use stored data
@app.callback(
    [Output("static-metrics", "children"),
     Output("static-trend-graph", "figure")],
    Input("interval", "n_intervals"),
)
def update_static_metrics(_):
    # Get game statistics from metrics store
    game_stats = metrics_store.get_game_statistics()
    
    # Traditional PGN metrics as a backup
    pgn_metrics = parse_pgn_metrics()
    
    # Use store metrics if available, otherwise fall back to parsed metrics
    metrics = {
        "total_games": game_stats['total_games'] if game_stats['total_games'] > 0 else pgn_metrics['total_games'],
        "wins": game_stats['white_wins'] if game_stats['total_games'] > 0 else pgn_metrics['wins'],
        "losses": game_stats['black_wins'] if game_stats['total_games'] > 0 else pgn_metrics['losses'],
        "draws": game_stats['draws'] if game_stats['total_games'] > 0 else pgn_metrics['draws'],
    }
    
    # Save to metrics file
    os.makedirs(METRICS_DIR, exist_ok=True)
    metrics_file = os.path.join(METRICS_DIR, "static_metrics.csv")
    pd.DataFrame([metrics]).to_csv(metrics_file, index=False)
    
    # Trend graph - use pgn_metrics for now as it has the trend data built in
    df = pgn_metrics["trend_df"]
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

# Clean up when the app is closed
def cleanup():
    metrics_store.close()

atexit.register(cleanup)

if __name__ == "__main__":
    import socket
    # Get local IP address for LAN access
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"
    port = 8050
    print(f"\nDash is running on: http://{local_ip}:{port} (accessible from your LAN)\n")
    print(f"Or on this machine: http://localhost:{port}\n")
    # Use host="0.0.0.0" to allow access from other machines on your LAN
    app.run(debug=True, host="0.0.0.0", port=port)