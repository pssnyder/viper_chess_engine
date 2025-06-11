# engine_utilities/engine_db_manager.py
# This module manages the database of chess engine configurations and their metrics.
# It can be expanded as the engines db utility toolkit needs expand as well.
# TODO create a db manager is able to listen for incoming data and store it in the database, as well as handle incoming requests for configuration setups. the idea being is that eventually all this utility code can be run locally or on a server, so that anywhere I am running the chess_engine, its able to "phone home" with its game, engine, config, and log data. The data may come in per game or as a bulk upload at the end of a game simulation session. this will be the server side of the db manager. nothing else about the metrics needs has changed, I just want to be able to collect more data remotely from other machines without having to rely on git commits to merge all the data together. have this tool capable of

import os
import threading
import time
import json
import yaml
from http.server import BaseHTTPRequestHandler, HTTPServer
from metrics.metrics_store import MetricsStore

class EngineDBManager:
    """
    Manages the database of chess engine configurations and their metrics.
    Can run as a local or server-side service to receive and store data from remote engines.
    """
    def __init__(self, db_path="metrics/chess_metrics.db", config_path="engine_utilities/engine_utilities.yaml"):
        self.db_path = db_path
        self.metrics_store = MetricsStore(db_path=db_path)
        self.config = self._load_config(config_path)
        self.server_thread = None
        self.httpd = None
        self.running = False

    def _load_config(self, config_path):
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        return {}

    def start_server(self, host="0.0.0.0", port=8080):
        """Start an HTTP server to receive incoming data from remote engines."""
        self.running = True
        handler = self._make_handler()
        self.httpd = HTTPServer((host, port), handler)
        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()
        print(f"EngineDBManager server running at http://{host}:{port}")

    def stop_server(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.running = False
            print("EngineDBManager server stopped.")

    def _make_handler(self):
        manager = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    data = json.loads(post_data.decode('utf-8'))
                    # Accepts: { 'type': 'game', 'game_data': {...} } or { 'type': 'move', 'move_data': {...} }
                    if data.get('type') == 'game':
                        manager._handle_game_data(data['game_data'])
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'Game data stored')
                    elif data.get('type') == 'move':
                        manager._handle_move_data(data['move_data'])
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'Move data stored')
                    else:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b'Unknown data type')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f'Error: {e}'.encode('utf-8'))
        return Handler

    def _handle_game_data(self, game_data):
        # Store game result and config
        self.metrics_store.add_game_result(**game_data)

    def _handle_move_data(self, move_data):
        # Store move metrics
        self.metrics_store.add_move_metric(**move_data)

    def bulk_upload(self, data_list):
        """Accept a list of game/move data for bulk upload."""
        for item in data_list:
            if item.get('type') == 'game':
                self._handle_game_data(item['game_data'])
            elif item.get('type') == 'move':
                self._handle_move_data(item['move_data'])

    def listen_and_store(self):
        """Main loop for local/remote data collection (can be expanded for sockets, etc)."""
        # For now, just runs the HTTP server
        self.start_server()
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_server()

# Example usage (for local dev/testing):
if __name__ == "__main__":
    manager = EngineDBManager()
    manager.listen_and_store()