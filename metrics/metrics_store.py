import os
import sqlite3
import json
import re
import time
import pandas as pd
import yaml
from datetime import datetime
import glob
import threading
import chess.pgn
import io
import random

"""
Database Schema Documentation:

1. log_entries Table:
   - Stores log data from the chess engine.
   - Columns:
     - id: Primary key.
     - timestamp: Time of the log entry.
     - function_name: Name of the function generating the log.
     - log_file: Source log file.
     - message: Log message.
     - value: Numeric value associated with the log.
     - label: Label for the log entry.
     - side: Side (white/black) associated with the log.
     - fen: FEN string representing the board state.
     - raw_text: Raw log text (unique).
     - created_at: Timestamp of entry creation.

2. game_results Table:
   - Stores results of chess games.
   - Columns:
     - id: Primary key.
     - game_id: Unique identifier for the game.
     - timestamp: Time of the game.
     - winner: Winner of the game (1-0, 0-1, 1/2-1/2).
     - game_pgn: PGN of the game.
     - white_player: Name of the white player.
     - black_player: Name of the black player.
     - game_length: Number of moves in the game.
     - created_at: Timestamp of entry creation.

3. config_settings Table:
   - Stores AI configuration data.
   - Columns:
     - id: Primary key.
     - config_id: Unique identifier for the configuration.
     - timestamp: Time of the configuration.
     - game_id: Associated game ID.
     - config_data: JSON representation of the configuration.
     - white_engine: Engine used by white.
     - black_engine: Engine used by black.
     - white_depth: Search depth for white.
     - black_depth: Search depth for black.
     - white_ai_type: AI type for white.
     - black_ai_type: AI type for black.
     - created_at: Timestamp of entry creation.

4. metrics Table:
   - Stores computed metrics.
   - Columns:
     - id: Primary key.
     - metric_name: Name of the metric.
     - metric_value: Value of the metric.
     - side: Side (white/black) associated with the metric.
     - function_name: Function generating the metric.
     - timestamp: Time of the metric.
     - game_id: Associated game ID.
     - config_id: Associated configuration ID.
     - created_at: Timestamp of entry creation.
"""

class MetricsStore:
    """
    A persistent storage solution for chess engine metrics.
    Uses SQLite to store parsed logs, game results, and configuration data.
    """
    
    def __init__(self, db_path="metrics/chess_metrics.db"):
        """Initialize the metrics store with the given database path."""
        # Ensure metrics directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self.lock = threading.RLock()  # Use a reentrant lock for thread safety
        self.local = threading.local()  # Thread-local storage for connections
        
        # Create tables if they don't exist
        self._initialize_database()
        
        # Set up background collection thread
        self.collection_active = False
        self.collection_thread = None
    
    def _get_connection(self):
        """Get a thread-local database connection."""
        if not hasattr(self.local, 'connection') or self.local.connection is None:
            # Set a higher timeout (30 seconds) to handle contention
            self.local.connection = sqlite3.connect(
                self.db_path, 
                timeout=30.0, 
                check_same_thread=False
            )
            # Enable WAL mode for better concurrency
            self.local.connection.execute('PRAGMA journal_mode=WAL')
            # Defer transactions until commit
            self.local.connection.execute('PRAGMA synchronous=NORMAL')
        return self.local.connection
    
    def _initialize_database(self):
        """Create the database schema if it doesn't exist."""
        connection = self._get_connection()
        with connection:
            cursor = connection.cursor()
            
            # Create log_entries table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                function_name TEXT,
                log_file TEXT,
                message TEXT,
                value REAL,
                label TEXT,
                side TEXT,
                fen TEXT,
                raw_text TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create game_results table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT UNIQUE,
                timestamp TEXT,
                winner TEXT,
                game_pgn TEXT,
                white_player TEXT,
                black_player TEXT,
                game_length INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create config_settings table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS config_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_id TEXT UNIQUE,
                timestamp TEXT,
                game_id TEXT,
                config_data TEXT,
                white_engine TEXT,
                black_engine TEXT,
                white_depth INTEGER,
                black_depth INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create metrics table for computed metrics
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT,
                metric_value REAL,
                side TEXT,
                function_name TEXT,
                timestamp TEXT,
                game_id TEXT,
                config_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(metric_name, timestamp, game_id, side)
            )
            ''')
            
            # Create indices for faster queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log_entries(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_log_function ON log_entries(function_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_log_side ON log_entries(side)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_side ON metrics(side)')
            
            connection.commit()
    
    def start_collection(self, interval=60):
        """Start periodic data collection with the specified interval in seconds."""
        if self.collection_active:
            return  # Already running
            
        self.collection_active = True
        
        def collection_worker():
            while self.collection_active:
                try:
                    self.collect_all_data()
                except Exception as e:
                    print(f"Error during data collection: {e}")
                # Sleep for the specified interval
                for _ in range(interval):
                    if not self.collection_active:
                        break
                    time.sleep(1)
        
        self.collection_thread = threading.Thread(target=collection_worker, daemon=True)
        self.collection_thread.start()
    
    def stop_collection(self):
        """Stop the periodic data collection."""
        self.collection_active = False
        if self.collection_thread and self.collection_thread.is_alive():
            self.collection_thread.join(timeout=5.0)
    
    def collect_all_data(self):
        """Collect all available data from logs, games, and config files."""
        self.collect_log_data()
        self.collect_game_data()
        self.collect_config_data()
        self.compute_metrics()
    
    def collect_log_data(self, log_dir="logging"):
        """Parse and store log data from the logging directory."""
        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        for log_file in log_files:
            self._process_log_file(log_file)
    
    def _execute_with_retry(self, cursor, query, params=(), max_retries=5):
        """Execute a query with retry logic for handling locked database."""
        retries = 0
        while retries < max_retries:
            try:
                return cursor.execute(query, params)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "database is locked" in str(e):
                    retries += 1
                    time.sleep(0.1)
                else:
                    raise
        raise sqlite3.OperationalError("Max retries reached for query execution.")
    
    def _process_log_file(self, log_file):
        """Process a single log file."""
        pass  # Placeholder for actual implementation

    def _parse_log_line(self, line, log_file):
        """Parse a single line from a log file."""
        pass  # Placeholder for actual implementation
    
    def collect_game_data(self, games_dir="games"):
        """Parse and store game data from PGN files, respecting exclude_from_metrics flag."""
        pgn_files = glob.glob(os.path.join(games_dir, "eval_game_*.pgn"))
        for pgn_file in pgn_files:
            self._process_pgn_file(pgn_file)
    
    def _process_pgn_file(self, pgn_file):
        """Process a single PGN file and store its data in the database."""
        try:
            game_id = os.path.basename(pgn_file)
            connection = self._get_connection()
            with connection:
                cursor = connection.cursor()
                self._execute_with_retry(cursor, "SELECT COUNT(*) FROM game_results WHERE game_id = ?", (game_id,))
                if cursor.fetchone()[0] > 0:
                    return

            with open(pgn_file, 'r', encoding='utf-8', errors='ignore') as f:
                pgn_text = f.read()
                pgn_io = io.StringIO(pgn_text)
                game = chess.pgn.read_game(pgn_io)

                if game is None:
                    return

                headers = game.headers
                winner = headers.get("Result", "*")
                white_player = headers.get("White", "Unknown")
                black_player = headers.get("Black", "Unknown")

                # Check exclude_from_metrics flag
                exclude_white = self._get_ai_config("white").get("exclude_from_metrics", False)
                exclude_black = self._get_ai_config("black").get("exclude_from_metrics", False)

                if (exclude_white and winner == "1-0") or (exclude_black and winner == "0-1"):
                    return

                game_length = 0
                board = game.board()
                for move in game.mainline_moves():
                    board.push(move)
                    game_length += 1

                timestamp = None
                match = re.search(r'eval_game_(\d{8}_\d{6})\.pgn', game_id)
                if match:
                    timestamp = match.group(1)

                with connection:
                    cursor = connection.cursor()
                    self._execute_with_retry(cursor, '''
                    INSERT OR IGNORE INTO game_results
                    (game_id, timestamp, winner, game_pgn, white_player, black_player, game_length)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        game_id,
                        timestamp,
                        winner,
                        pgn_text,
                        white_player,
                        black_player,
                        game_length
                    ))
                    connection.commit()

        except Exception as e:
            print(f"Error processing PGN file {pgn_file}: {e}")

    def collect_config_data(self, games_dir="games"):
        """Parse and store configuration data from YAML files."""
        yaml_files = glob.glob(os.path.join(games_dir, "eval_game_*.yaml"))
        for yaml_file in yaml_files:
            self._process_config_file(yaml_file)
    
    def _process_config_file(self, yaml_file):
        """Process a single config file and store its data in the database."""
        try:
            # Create a config ID from the filename
            config_id = os.path.basename(yaml_file)
            
            # Check if this config is already in the database
            connection = self._get_connection()
            with connection:
                cursor = connection.cursor()
                self._execute_with_retry(cursor, "SELECT COUNT(*) FROM config_settings WHERE config_id = ?", (config_id,))
                if cursor.fetchone()[0] > 0:
                    return  # Already processed
            
            # Parse the YAML file
            with open(yaml_file, 'r') as f:
                config_data = yaml.safe_load(f)
                
            # Extract key configuration details
            white_engine = config_data.get('white_ai_config', {}).get('engine', 'unknown')
            black_engine = config_data.get('black_ai_config', {}).get('engine', 'unknown')
            white_depth = config_data.get('white_ai_config', {}).get('depth', 0)
            black_depth = config_data.get('black_ai_config', {}).get('depth', 0)
            white_ai_type = config_data.get('white_ai_config', {}).get('ai_type', 'unknown')
            black_ai_type = config_data.get('black_ai_config', {}).get('ai_type', 'unknown')
            
            # Match with corresponding game
            game_id = config_id.replace('.yaml', '.pgn')
            
            # Extract timestamp from filename
            timestamp = None
            match = re.search(r'eval_game_(\d{8}_\d{6})\.yaml', config_id)
            if match:
                timestamp = match.group(1)
            
            # Store config data
            with connection:
                cursor = connection.cursor()
                self._execute_with_retry(cursor, '''
                INSERT OR IGNORE INTO config_settings
                (config_id, timestamp, game_id, config_data, white_engine, black_engine, white_depth, black_depth, white_ai_type, black_ai_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    config_id,
                    timestamp,
                    game_id,
                    json.dumps(config_data),
                    white_engine,
                    black_engine,
                    white_depth,
                    black_depth,
                    white_ai_type,
                    black_ai_type
                ))
                connection.commit()
        
        except Exception as e:
            print(f"Error processing config file {yaml_file}: {e}")
    
    def compute_metrics(self):
        """Compute derived metrics from the raw data and store them."""
        connection = self._get_connection()
        with connection:
            cursor = connection.cursor()
            
            # 1. Compute average metrics by function and side
            self._execute_with_retry(cursor, '''
            SELECT function_name, label, side, AVG(value) as avg_value, COUNT(*) as count,
                   MIN(value) as min_value, MAX(value) as max_value, MAX(timestamp) as latest_timestamp
            FROM log_entries
            WHERE value IS NOT NULL AND side IS NOT NULL
            GROUP BY function_name, label, side
            ''')
            
            metrics_to_store = []
            for row in cursor.fetchall():
                function_name, label, side, avg_value, count, min_value, max_value, latest_timestamp = row
                
                # Collect metrics for batch insert
                metrics_to_store.append((f"avg_{label}", avg_value, side, function_name, latest_timestamp))
                metrics_to_store.append((f"min_{label}", min_value, side, function_name, latest_timestamp))
                metrics_to_store.append((f"max_{label}", max_value, side, function_name, latest_timestamp))
                metrics_to_store.append((f"count_{label}", count, side, function_name, latest_timestamp))
            
            # Batch insert all metrics
            for metric in metrics_to_store:
                metric_name, metric_value, side, function_name, timestamp = metric
            
                def _store_metric(metric_name, metric_value, side, function_name, timestamp):
                    """Store a computed metric in the database."""
                    connection = self._get_connection()
                    with connection:
                        cursor = connection.cursor()
                        try:
                            self._execute_with_retry(cursor, '''
                            INSERT OR IGNORE INTO metrics
                            (metric_name, metric_value, side, function_name, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                            ''', (
                                metric_name,
                                metric_value,
                                side,
                                function_name,
                                timestamp
                            ))
                            connection.commit()
                        except sqlite3.Error as e:
                            print(f"Error storing metric {metric_name}: {e}")
                _store_metric(metric_name, metric_value, side, function_name, timestamp)
    
    def get_game_statistics(self):
        """
        Retrieve game statistics such as total games, wins, losses, and draws.
        This is a placeholder implementation. Replace with actual logic.
        """
        return {
            "total_games": 0,
            "white_wins": 0,
            "black_wins": 0,
            "draws": 0,
        }
    
    def get_side_performance_metrics(self, side):
        """
        Retrieve performance metrics for a specific side ('w' for white, 'b' for black).
        """
        if side not in ('w', 'b'):
            raise ValueError("Invalid side. Use 'w' for white or 'b' for black.")

        connection = self._get_connection()
        metrics = []
        with connection:
            cursor = connection.cursor()
            self._execute_with_retry(cursor, '''
            SELECT metric_name, AVG(metric_value) as avg_value, COUNT(*) as count
            FROM metrics
            WHERE side = ?
            GROUP BY metric_name
            ''', (side,))
            
            for row in cursor.fetchall():
                metric_name, avg_value, count = row
                metrics.append({'label': metric_name, 'avg_value': avg_value, 'count': count})
        
        return metrics
    
    def get_errors_and_warnings(self, limit=100):
        """
        Retrieve recent error and warning log entries from the log_entries table.
        Returns a list of dicts with timestamp, function_name, message, and log_file.
        """
        connection = self._get_connection()
        results = []
        with connection:
            cursor = connection.cursor()
            self._execute_with_retry(
                cursor,
                '''
                SELECT timestamp, function_name, message, log_file
                FROM log_entries
                WHERE message LIKE '%error%' OR message LIKE '%warning%' OR message LIKE '%exception%'
                ORDER BY id DESC
                LIMIT ?
                ''',
                (limit,)
            )
            for row in cursor.fetchall():
                results.append({
                    "timestamp": row[0],
                    "function_name": row[1],
                    "message": row[2],
                    "log_file": row[3]
                })
        return results
    
    def get_metrics_trend_data(self, metric_name, side=None, limit=100):
        """Retrieve trend data for a specific metric."""
        connection = self._get_connection()
        query = '''
        SELECT timestamp, metric_value
        FROM metrics
        WHERE metric_name = ?
        '''
        params = [metric_name]

        if side:
            query += ' AND side = ?'
            params.append(side)

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        with connection:
            cursor = connection.cursor()
            self._execute_with_retry(cursor, query, params)
            return [
                {"timestamp": row[0], "metric_value": row[1]}
                for row in cursor.fetchall()
            ]

    def close(self):
        """Close the database connection."""
        if hasattr(self.local, 'connection') and self.local.connection:
            self.local.connection.close()
            self.local.connection = None

    def _get_ai_config(self, color):
        """Retrieve AI configuration for the given color."""
        if color == "white":
            return {
                "exclude_from_metrics": False,  # Replace with actual config retrieval logic
            }
        elif color == "black":
            return {
                "exclude_from_metrics": True,  # Replace with actual config retrieval logic
            }
        return {}