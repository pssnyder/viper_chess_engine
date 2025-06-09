# local_metrics_dashboard.py
# A locally running dashboard to visualize chess engine metrics, system performance, and log files while actively analyzing the engine's performance.
# TODO add functionality that, upon initialization of the metrics dash, backs up the database so we have a snapshot, then cleans up any incomplete games that could skew the metrics since we don't actually know the result. then it should create fresh test records for white and black color selections, under a metrics-test engine name (formerly ai_type) so we can test the dashboard without affecting the actual metrics. These test metrics will need to cover basic scenarios for data appearing in the visuals to allow for end to end testing in the event there is no real game data populated in the dev environment, the metrics dash will always initialize with its own test data ready, marking it as exclude from metrics in production branches but exclude from metrics False in dev branches for testing.

import os
import glob
import time
import psutil
import dash
from dash import dcc, html, Output, Input, State # Import State
import plotly.graph_objs as go
import pandas as pd
import re
from collections import defaultdict
import numpy as np
from metrics_store import MetricsStore # Use the existing MetricsStore
import threading
import yaml
import atexit
from datetime import datetime # Import datetime for parsing timestamps

METRICS_DIR = "metrics"
GAMES_DIR = "games"
LOG_DIR = "logging"
LOG_FILES = [
    os.path.join(LOG_DIR, "chess_game.log"),
    os.path.join(LOG_DIR, "evaluation_engine.log"),
    os.path.join(LOG_DIR, "stockfish_handler.log"), # Include Stockfish handler log
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

# Load AI types from config.yaml (for dropdowns)
try:
    with open("config.yaml", "r") as config_file:
        config_data = yaml.safe_load(config_file)
        AI_TYPES = config_data.get("ai_types", [])
        # Extract unique AI types and ensure 'Viper' and 'Stockfish' are present
        unique_ai_types = sorted(list(set(AI_TYPES + ['Viper', 'Stockfish'])))
        # Prepare options for dropdown
        AI_TYPE_OPTIONS = [{"label": ai_type.capitalize(), "value": ai_type} for ai_type in unique_ai_types]
except Exception as e:
    print(f"Error loading config.yaml for AI types: {e}")
    AI_TYPES = []
    AI_TYPE_OPTIONS = []

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
                lines = f.readlines()[-max_lines:]
                
            for line in lines:
                entry = self._parse_log_line(line)
                if entry:
                    log_data.append(entry)
                    self._categorize_entry(entry)
                    
            self._identify_patterns()
            
        except Exception as e:
            print(f"Error parsing log file {filepath}: {e}")
            
        self.log_entries = log_data
        return log_data
    
    def _parse_log_line(self, line):
        """Parse a single log line into structured data."""
        # This regex needs to be robust enough to handle the various log formats you have
        # from chess_game.log, evaluation_engine.log, and stockfish_handler.log.
        # This is a generic attempt; specific parsing might be needed for very different formats.

        # Example patterns:
        # 16:25:14 | _calculate_score | King safety score: 0.000 | FEN: fen_string (evaluation_engine.log)
        # 16:25:14 | process_ai_move  | AI (White) played: e2e4 (Eval: 0.20) | Time: 0.1500s | Nodes: 1500 (chess_game.log)
        # 16:25:14 | _start_engine    | Sent: uci (stockfish_handler.log)

        # Pattern for evaluation_engine and chess_game info lines with FEN/metrics
        pattern_eval_metrics = r'(\d{2}:\d{2}:\d{2}) \| (\w+) \| (.*?)(?:: ([-\d\.]+))?(?: \| (FEN: .*))?(?: \| Time: ([-\d\.]+)s)?(?: \| Nodes: (\d+))?'
        match = re.match(pattern_eval_metrics, line)
        
        if match:
            time_str, function, label_or_message, value_str, fen_part, time_taken_str, nodes_str = match.groups()

            value = float(value_str) if value_str else None
            time_taken = float(time_taken_str) if time_taken_str else None
            nodes = int(nodes_str) if nodes_str else None
            fen = fen_part.replace('FEN: ', '') if fen_part else None

            # Extract side from FEN if present, otherwise infer from label/message
            side = None
            if fen and ' b ' in fen:
                side = 'b'
            elif fen and ' w ' in fen:
                side = 'w'
            elif 'White' in label_or_message:
                side = 'w'
            elif 'Black' in label_or_message:
                side = 'b'

            return {
                'time': time_str,
                'function': function,
                'label': label_or_message.strip(), # This might contain the actual label like "King safety score" or just "AI (White) played: e2e4"
                'value': value,
                'fen': fen,
                'side': side,
                'time_taken': time_taken,
                'nodes': nodes,
                'raw': line.strip()
            }
        else:
            # Generic pattern for other log messages (e.g., Stockfish communication, errors)
            simple_pattern = r'(\d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)'
            match_simple = re.match(simple_pattern, line)
            if match_simple:
                time_str, function, message = match_simple.groups()
                self.message_frequency[message.strip()] += 1
                return {
                    'time': time_str,
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
        
        # Only process entries with numeric values that are likely to be metrics
        # Filter specific labels or patterns for metric collection
        if 'label' in entry and entry['value'] is not None and \
           ("score" in entry['label'].lower() or "eval" in entry['label'].lower() or "mobility" in entry['label'].lower()):
            
            label = entry['label'].strip()
            # Clean up label for consistent grouping (e.g., "King safety score: 0.000" -> "King safety score")
            clean_label = re.sub(r':\s*[-\d\.]+', '', label).strip()
            
            self.label_counts[clean_label] += 1
            self.metrics_by_label[clean_label].append(entry)
            
            # Categorize by side
            if 'side' in entry:
                side = entry['side']
                self.metrics_by_side[side][clean_label].append(entry)
        
        # Also, capture nodes and time_taken as separate metrics for general function calls like process_ai_move
        if 'nodes' in entry and entry['nodes'] is not None and entry['function'] == 'process_ai_move':
            # This is a specific metric related to AI move
            nodes_label = "Nodes Searched"
            if 'side' in entry:
                self.metrics_by_side[entry['side']][nodes_label].append({'value': entry['nodes'], 'time': entry['time']})
            self.metrics_by_label[nodes_label].append({'value': entry['nodes'], 'time': entry['time']})

        if 'time_taken' in entry and entry['time_taken'] is not None and entry['function'] == 'process_ai_move':
            time_label = "Time Taken (s)"
            if 'side' in entry:
                self.metrics_by_side[entry['side']][time_label].append({'value': entry['time_taken'], 'time': entry['time']})
            self.metrics_by_label[time_label].append({'value': entry['time_taken'], 'time': entry['time']})


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

    # A/B Testing & Dynamic Metric Filters
    html.Div([
        html.H2("A/B Testing & Metric Trends", style={"textAlign": "center", "marginBottom": "15px"}),
        html.Div([
            html.Div([
                html.Label("White AI Type:"),
                dcc.Dropdown(
                    id="white-ai-type-filter",
                    options=[{"label": str(option["label"]), "value": str(option["value"])} for option in AI_TYPE_OPTIONS],
                    multi=True,
                    placeholder="Select White AI Type(s)"
                )
            ], style={'width': '30%', 'display': 'inline-block', 'margin-right': '2%', 'verticalAlign': 'top'}),
            html.Div([
                html.Label("Black AI Type:"),
                dcc.Dropdown(
                    id="black-ai-type-filter",
                    options=[{"label": str(option["label"]), "value": str(option["value"])} for option in AI_TYPE_OPTIONS],
                    multi=True,
                    placeholder="Select Black AI Type(s)"
                )
            ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top'}),
             html.Div([
                html.Label("Metric to Plot:"),
                dcc.Dropdown(
                    id="dynamic-metric-selector",
                    options=[], # Populated dynamically
                    placeholder="Select a metric (e.g., eval, nodes)"
                )
            ], style={'width': '30%', 'display': 'inline-block', 'margin-left': '2%', 'verticalAlign': 'top'}),
        ], style={'marginBottom': '15px'}),
        
        dcc.Graph(id="ab-test-trend-graph", style={"height": "400px"}),
        html.Div(id="move-metrics-details", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px", "marginTop": "20px"}),

    ], style={"marginBottom": "30px", "border": "1px solid #ccc", "padding": "15px", "borderRadius": "8px"}),


    # Smart Log Analysis section
    html.Div([
        html.Div([
            html.H3("Analysis by Side", style={"textAlign": "center"}),
            dcc.Dropdown(
                id="side-selector",
                options=[
                    {"label": "White", "value": "w"}, # Changed to 'w' and 'b' for consistency with DB
                    {"label": "Black", "value": "b"}
                ],
                value="w",
                clearable=False,
                style={"marginBottom": "10px"}
            ),
            # AI type selector removed from here, integrated into A/B testing filters
            html.Div(id="side-analysis", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px", "minHeight": "200px"}),
        ], style={"flex": "1", "marginRight": "20px"}),

        html.Div([
            html.H3("Top Metrics (from Logs)", style={"textAlign": "center"}),
            html.Div(id="top-metrics", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px", "minHeight": "200px"}),
        ], style={"flex": "1", "marginRight": "20px"}),

        html.Div([
            html.H3("Potential Issues (from Logs)", style={"textAlign": "center"}),
            html.Div(id="log-issues", style={"padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px", "minHeight": "200px"}),
        ], style={"flex": "1"}),
    ], style={"display": "flex", "flexDirection": "row", "gap": "20px", "marginBottom": "30px"}),

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
        dcc.Interval(id="log-analysis-interval", interval=5000, n_intervals=0),
        html.Pre(id="log-tail", style={"height": "300px", "overflowY": "scroll", "background": "#eee", "padding": "10px", "borderRadius": "5px", "whiteSpace": "pre-wrap", "wordBreak": "break-all"}),
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
    Output("dynamic-metric-selector", "options"),
    Input("log-analysis-interval", "n_intervals"),
)
def update_dynamic_metric_options(_):
    # This callback updates the dropdown options based on available move metrics
    # It queries the distinct metric_names from the move_metrics table in MetricsStore
    move_metric_names = metrics_store.get_distinct_move_metric_names()
    options = [{'label': name.replace('_', ' ').title(), 'value': name} for name in move_metric_names]
    return options

@app.callback(
    [Output("side-analysis", "children"),
     Output("top-metrics", "children"),
     Output("log-issues", "children"),
     Output("ab-test-trend-graph", "figure"), # This graph now supports A/B testing
     Output("move-metrics-details", "children")], # New output for move metrics details
    [Input("log-analysis-interval", "n_intervals"),
     Input("logfile-dropdown", "value"), # Not directly used for analysis but triggers refresh
     Input("white-ai-type-filter", "value"),
     Input("black-ai-type-filter", "value"),
     Input("dynamic-metric-selector", "value"),
     Input("side-selector", "value")] # Keep this for individual side analysis
)
def update_log_analysis(_, log_file_path, white_ai_types, black_ai_types, selected_metric, side_for_analysis):
    # This callback now powers multiple sections and integrates with MetricsStore for A/B data

    # --- Live Log Analysis (from LogAnalyzer) ---
    analyzer = LogAnalyzer()
    # It's important to parse the *main* evaluation/chess log for log analyzer
    # The dashboard will only display a tail of `logfile-dropdown` value
    # but the analysis itself should run on the main logs.
    analyzer.parse_log_file(LOG_FILES[0]) # evaluation_engine.log
    if len(LOG_FILES) > 1: # Also parse chess_game.log for broader messages
        analyzer.parse_log_file(LOG_FILES[1])
    if len(LOG_FILES) > 2: # And stockfish_handler.log
        analyzer.parse_log_file(LOG_FILES[2])

    # Side analysis
    side_analysis_components = []
    # Use selected_side_for_analysis from dropdown
    for side, label in [(side_for_analysis, "Selected Side")]: # Only show the selected side
        stored_metrics = metrics_store.get_side_performance_metrics(side)
        
        content_components = []
        content_components.append(html.H4(f"{label} Metrics (Avg from All Games)"))
        
        if stored_metrics:
            for metric in sorted(stored_metrics, key=lambda x: x['label']):
                if metric['avg_value'] is not None:
                    content_components.append(html.Div([
                        html.B(f"{metric['label']}:"),
                        html.Span(f" Avg: {metric['avg_value']:.3f}, Count: {metric['count']}")
                    ]))
        else:
            content_components.append(html.P("No data for this side yet."))
        
        side_analysis_components.append(html.Div(content_components, style={"marginBottom": "15px"}))

    # Top metrics (from LogAnalyzer - focus on frequently occurring metrics in live logs)
    top_metrics_list = []
    top_metrics_analyzer = analyzer.get_top_metrics(n=5) # Overall top metrics
    for label, count in top_metrics_analyzer:
        metrics = analyzer.get_metrics_for_label(label)
        stats = analyzer.get_statistics(metrics)
        if stats['avg'] is not None:
            top_metrics_list.append(html.Div([
                html.B(f"{label} ({count} entries):"),
                html.Span(f" Avg: {stats['avg']:.3f}, Min: {stats['min']:.3f}, Max: {stats['max']:.3f}, Latest: {stats['latest']:.3f}")
            ]))
        else:
            top_metrics_list.append(html.Div([
                html.B(f"{label} ({count} entries):"),
                html.Span(" (No numeric value)")
            ]))


    # Potential Issues (from LogAnalyzer)
    errors_and_warnings = analyzer.get_errors_and_warnings()
    uncommon_messages = analyzer.uncommon_messages
    
    issues_components = []
    if errors_and_warnings:
        error_items = []
        for error in errors_and_warnings[:5]: # Limit display to 5
            message_type = "Error"
            message_color = "#ff5252"
            if 'message' in error:
                msg_content = error['message']
                if 'warning' in msg_content.lower(): message_type = "Warning"; message_color = "#ffb300"
                elif 'exception' in msg_content.lower(): message_type = "Exception"; message_color = "#d50000"
            
            error_items.append(html.Div([
                html.Span(f"{error.get('timestamp', '')} ", style={"color": "#757575", "fontSize": "0.9em"}),
                html.Span(f"[{error.get('function_name', '')}] ", style={"color": "#2196f3", "fontWeight": "bold"}),
                html.Span(f"{message_type}: ", style={"color": message_color, "fontWeight": "bold"}),
                html.Span(f"{error.get('message', error.get('raw', ''))}")
            ], style={"marginBottom": "5px", "padding": "5px", "borderLeft": f"3px solid {message_color}", "backgroundColor": "#f5f5f5"}))
        issues_components.append(html.Div([html.H4("Errors/Warnings:"), html.Div(error_items)]))
    
    if uncommon_messages:
        uncommon_items = []
        for msg in uncommon_messages[:5]: # Limit display to 5
             match = re.match(r'(\d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)', msg)
             if match:
                 time_str, function, message = match.groups()
                 uncommon_items.append(html.Div([
                     html.Span(f"{time_str} ", style={"color": "#757575", "fontSize": "0.9em"}),
                     html.Span(f"[{function}] ", style={"color": "#2196f3", "fontWeight": "bold"}),
                     html.Span(f"{message}")
                 ], style={"marginBottom": "5px", "padding": "5px", "borderLeft": "3px solid #9e9e9e", "backgroundColor": "#f5f5f5"}))
             else:
                 uncommon_items.append(html.Div(msg, style={"marginBottom": "5px", "padding": "5px", "borderLeft": "3px solid #9e9e9e", "backgroundColor": "#f5f5f5"}))
        issues_components.append(html.Div([html.H4("Uncommon Messages:"), html.Div(uncommon_items)]))

    if not errors_and_warnings and not uncommon_messages:
        issues_components.append(html.P("No significant issues detected in recent logs."))


    # --- A/B Testing Trend Graph (using move_metrics from MetricsStore) ---
    fig_ab_test = go.Figure()
    move_metrics_details = []

    # Get data based on filters
    filtered_moves = metrics_store.get_filtered_move_metrics(
        white_ai_types=white_ai_types,
        black_ai_types=black_ai_types,
        metric_name=selected_metric # Pass the selected metric name
    )
    
    if filtered_moves:
        df_moves = pd.DataFrame(filtered_moves)
        df_moves['created_at_dt'] = pd.to_datetime(df_moves['created_at'])
        df_moves = df_moves.sort_values('created_at_dt') # Ensure chronological order

        # Aggregate for plotting (e.g., average eval per game, or raw data)
        # For evaluation, plot raw points
        if selected_metric:
            fig_ab_test.add_trace(go.Scatter(
                x=df_moves['created_at_dt'],
                y=df_moves[selected_metric], # Plot the actual metric values
                mode='markers',
                name=f'{selected_metric.replace("_", " ").title()} Trend',
                marker=dict(size=5, opacity=0.6)
            ))
            fig_ab_test.update_layout(
                title=f"{selected_metric.replace('_', ' ').title()} Trends for Selected AIs",
                xaxis_title="Time",
                yaxis_title=selected_metric.replace('_', ' ').title(),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            # Display some details from the filtered move metrics
            move_metrics_details.append(html.H4(f"Details for {selected_metric.replace('_', ' ').title()}"))
            # Display average, min, max, count for the filtered set
            avg_val = df_moves[selected_metric].mean()
            min_val = df_moves[selected_metric].min()
            max_val = df_moves[selected_metric].max()
            count_val = df_moves[selected_metric].count()
            
            move_metrics_details.append(html.Ul([
                html.Li(f"Average: {avg_val:.3f}"),
                html.Li(f"Min: {min_val:.3f}"),
                html.Li(f"Max: {max_val:.3f}"),
                html.Li(f"Count: {count_val}"),
                html.Li(f"Filtered Games: {len(df_moves['game_id'].unique())}")
            ]))

            # Optionally, display a table of recent moves
            # move_metrics_details.append(html.H5("Recent Moves:"))
            # move_metrics_details.append(
            #     dash.dash_table.DataTable(
            #         id='table-move-metrics',
            #         columns=[{"name": i, "id": i} for i in df_moves[['game_id', 'move_number', 'player_color', 'move_uci', selected_metric]].columns],
            #         data=df_moves[['game_id', 'move_number', 'player_color', 'move_uci', selected_metric]].tail(10).to_dict('records'),
            #         style_table={'overflowX': 'auto'},
            #         style_cell={'textAlign': 'left', 'padding': '5px'}
            #     )
            # )

        else:
            fig_ab_test.update_layout(title="Select a metric and AI types to see trends.")
            move_metrics_details.append(html.P("No data to display based on current filters."))

    else:
        fig_ab_test.update_layout(title="No move metrics data found for the selected filters.")
        move_metrics_details.append(html.P("No data to display based on current filters."))

    return side_analysis_components, top_metrics_list, issues_components, fig_ab_test, move_metrics_details


# Update the static metrics to use stored data
@app.callback(
    [Output("static-metrics", "children"),
     Output("static-trend-graph", "figure")],
    Input("interval", "n_intervals"),
)
def update_static_metrics(_):
    # Get game statistics from metrics store
    game_stats = metrics_store.get_game_statistics()
    
    metrics = {
        "total_games": game_stats['total_games'],
        "wins": game_stats['white_wins'],
        "losses": game_stats['black_wins'],
        "draws": game_stats['draws'],
    }
    
    # Trend graph for overall game results
    df_games = metrics_store.get_all_game_results_df() # New method to get all game results
    
    if not df_games.empty:
        # Sort by timestamp to ensure correct cumulative trend
        df_games['timestamp_dt'] = pd.to_datetime(df_games['timestamp'], format="%Y%m%d_%H%M%S", errors='coerce')
        df_games = df_games.sort_values('timestamp_dt').reset_index(drop=True)
        
        # Calculate cumulative wins, losses, draws
        df_games['cum_white_wins'] = (df_games['winner'] == '1-0').cumsum()
        df_games['cum_black_wins'] = (df_games['winner'] == '0-1').cumsum()
        df_games['cum_draws'] = (df_games['winner'] == '1/2-1/2').cumsum()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_games["timestamp_dt"], y=df_games["cum_white_wins"], mode="lines+markers", name="White Wins", line=dict(color="green")))
        fig.add_trace(go.Scatter(x=df_games["timestamp_dt"], y=df_games["cum_black_wins"], mode="lines+markers", name="Black Wins", line=dict(color="red")))
        fig.add_trace(go.Scatter(x=df_games["timestamp_dt"], y=df_games["cum_draws"], mode="lines+markers", name="Draws", line=dict(color="gray")))
        fig.update_layout(title="Cumulative Game Results Over Time", xaxis_title="Date/Time", yaxis_title="Count", height=300, margin=dict(t=40, b=0, l=0, r=0))
    else:
        fig = go.Figure()
        fig.update_layout(title="No Game Result Data", height=300, margin=dict(t=40, b=0, l=0, r=0))
    
    return html.Ul([
        html.Li(f"Total Games: {metrics['total_games']}"),
        html.Li(f"White Wins: {metrics['wins']}"),
        html.Li(f"Black Wins: {metrics['losses']}"),
        html.Li(f"Draws: {metrics['draws']}"),
    ]), fig

# Clean up when the app is closed
def cleanup():
    metrics_store.close()
    # Also ensure Stockfish processes are terminated if dashboard is closed
    # This assumes the main chess_game process might still be running or was run previously.
    # It's safer to have this cleanup here as well.
    print("Dashboard shutting down. Attempting to quit any active Stockfish handlers.")
    # This requires knowing if there are any active StockfishHandler instances.
    # A robust solution might involve the MetricsStore tracking active handlers,
    # or the main game loop being responsible for its own handlers' lifecycle.
    # For now, a manual check if we can get a reference to the engines from the ChessGame.
    # However, since the dashboard is a separate process, it cannot directly access
    # the ChessGame's engine instances unless they are shared via a multiprocessing Queue/Manager.
    # The clean shutdown logic in chess_game.py's `run` loop's `finally` block
    # is the primary place for this. This dashboard `cleanup` is for the dashboard's process.

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