# chess_game.py

import os
import sys
import pygame
import chess
import chess.pgn
import random
import yaml
import datetime
import logging
import math
import socket
import time # Import time for measuring move duration

# Define the maximum frames per second for the game loop
MAX_FPS = 60
from viper import ViperEvaluationEngine
from engine_utilities.stockfish_handler import StockfishHandler # Corrected import path and name
from metrics.metrics_store import MetricsStore # Import MetricsStore

# Resource path config for distro
def resource_path(relative_path):
    # Use getattr to avoid attribute error
    base = getattr(sys, '_MEIPASS', None)
    if base:
        return os.path.join(base, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# At module level, define a single logger for this file
def get_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def get_log_file_path():
    # Use a timestamped log file for each game session
    timestamp = get_timestamp()
    log_dir = "logging"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"chess_game.log")

chess_game_logger = logging.getLogger("chess_game")
chess_game_logger.setLevel(logging.DEBUG)
_init_status = globals().get("_init_status", {})
if not _init_status.get("initialized", False):
    log_file_path = get_log_file_path()
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10*1024*1024,
        backupCount=3,
        delay=True
    )
    formatter = logging.Formatter(
        '%(asctime)s | %(funcName)-15s | %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    chess_game_logger.addHandler(file_handler)
    chess_game_logger.propagate = False
    _init_status["initialized"] = True
    # Store the log file path for later use (e.g., to match with PGN/config)
    _init_status["log_file_path"] = log_file_path

class ChessGame:
    def __init__(self, fen_position=None):
        if fen_position:
            if not isinstance(fen_position, str):
                raise ValueError("FEN position must be a string")
            # Validate FEN position
            try:
                chess.Board(fen_position)  # This will raise ValueError if invalid
                self.starting_position = fen_position
            except ValueError as e:
                raise ValueError(f"Invalid FEN position: {e}")
        else:
            self.starting_position = None

        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)
            
        # Initialize Pygame (even in headless mode, for internal timing)
        pygame.init()
        self.clock = pygame.time.Clock()
        # Enable logging
        self.logging_enabled = self.config['debug']['enable_logging']
        self.show_thoughts = self.config['debug']['show_thinking']
        self.logger = chess_game_logger  # Use the module-level logger
        if self.logging_enabled:
            self.logger.debug("Logging enabled for ChessGame")
        else:
            self.show_thoughts = False
    

        # Initialize game settings
        self.human_color_pref = self.config['game_config']['human_color']
        if self.starting_position == None:
            self.starting_position = self.config.get('game_config', {}).get('starting_position', 'default')
        print("Initializing headless AI vs AI mode. No chess GUI will be shown.")
        print("Press Ctrl+C in the terminal to stop the game early.")

        # Initialize piece fallback values (primarily for Viper's evaluation)
        self.piece_values = {
            chess.KING: 0,
            chess.QUEEN: 9,
            chess.ROOK: 5,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3,
            chess.PAWN: 1
        }
 
        # Initialize AI configurations
        self.game_count = self.config.get('game_config', {}).get('ai_game_count', 0)
        self.ai_vs_ai = self.config.get('game_config', {}).get('ai_vs_ai', False)
        self.ai_types = self.config.get('ai_types', [])

        self.white_ai_config = self.config.get('white_ai_config', {})
        self.black_ai_config = self.config.get('black_ai_config', {})
        
        # Ensure 'ai_type' and 'engine' keys exist in AI configs
        self.white_ai_config['ai_type'] = self.white_ai_config.get('ai_type', 'random')
        self.white_ai_config['engine'] = self.white_ai_config.get('engine', 'Viper')
        self.black_ai_config['ai_type'] = self.black_ai_config.get('ai_type', 'random')
        self.black_ai_config['engine'] = self.black_ai_config.get('engine', 'Viper')

        self.white_ai_type = self.white_ai_config['ai_type']
        self.black_ai_type = self.black_ai_config['ai_type']
        self.white_eval_engine = self.white_ai_config['engine']
        self.black_eval_engine = self.black_ai_config['engine']

        self.exclude_white_performance = self.white_ai_config.get('exclude_from_metrics', False)
        self.exclude_black_performance = self.black_ai_config.get('exclude_from_metrics', False)
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Initializing ChessGame with {self.starting_position} position")
            self.logger.debug(f"White AI Type: {self.white_ai_type}, Engine: {self.white_eval_engine}")
            self.logger.debug(f"Black AI Type: {self.black_ai_type}, Engine: {self.black_eval_engine}")
        
        # Debug settings
        self.show_eval = self.config.get('debug', {}).get('show_evaluation', False)
        
        # Initialize MetricsStore
        self.metrics_store = MetricsStore() # Initialize the MetricsStore here
        self.game_start_timestamp = get_timestamp() # Unique timestamp for this game session
        self.current_game_db_id = f"eval_game_{self.game_start_timestamp}.pgn" # Matches filename format

        # Initialize board and new game
        self.new_game(self.starting_position)
        
        # Set colors
        self.set_colors()
        
        # Set headers
        self.set_headers()

        # Add rated flag from config
        self.rated = self.config.get('game_config', {}).get('rated', True)

    # ================================
    # ====== GAME CONFIGURATION ======
    
    def new_game(self, fen_position=None):
        """Reset the game state for a new game"""
        fen_to_use = fen_position
        if fen_position and not fen_position.count('/') == 7:
            fen_to_use = self.config.get('starting_positions', {}).get(fen_position, None)
            if fen_to_use is None:
                # fallback to standard chess starting position
                fen_to_use = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
        self.board = chess.Board(fen=fen_to_use) if fen_to_use else chess.Board()
        self.game = chess.pgn.Game()
        self.game_node = self.game # Initialize new game node
        self.selected_square = chess.SQUARES[0]
        self.last_ai_move = chess.Move.null()
        self.current_eval = 0.0 # Stores last calculated eval of the board
        self.current_player = chess.WHITE if self.board.turn else chess.BLACK
        self.last_move = chess.Move.null() # Reset last move made by any player
        self.move_history = []  # Reset move history
        
        # Initialize/Reset AI engines based on config
        self._initialize_ai_engines()

        # Reset PGN headers and file
        self.set_headers()
        self.quick_save_pgn("logging/active_game.pgn")
        
        if self.logging_enabled and self.logger:
            self.logger.info(f"Starting new game: {self.current_game_db_id}.")

    def _initialize_ai_engines(self):
        """Initializes or re-initializes AI engines based on config."""
        stockfish_path = self.config.get('stockfish_config', {}).get('path')
        stockfish_elo = self.config.get('stockfish_config', {}).get('elo_rating')
        stockfish_skill = self.config.get('stockfish_config', {}).get('skill_level')
        debug_stockfish = self.config.get('stockfish_config', {}).get('debug_stockfish', False)

        # White Engine
        if self.white_ai_config['engine'].lower() == 'stockfish':
            if not stockfish_path or not os.path.exists(stockfish_path):
                self.logger.error(f"Stockfish executable not found at: {stockfish_path}. White AI defaulting to Viper.")
                self.white_engine = EvaluationEngine(self.board, chess.WHITE, ai_config=self.white_ai_config)
                self.white_ai_config['engine'] = 'Viper' # Force engine name change
                self.white_ai_config['ai_type'] = 'random' # Force type change as Stockfish type invalid
            else:
                self.white_engine = StockfishHandler( # Renamed class
                    stockfish_path=stockfish_path,
                    elo_rating=stockfish_elo,
                    skill_level=stockfish_skill,
                    debug_mode=debug_stockfish
                )
        else:
            self.white_engine = EvaluationEngine(self.board, chess.WHITE, ai_config=self.white_ai_config)
        
        # Black Engine
        if self.black_ai_config['engine'].lower() == 'stockfish':
            if not stockfish_path or not os.path.exists(stockfish_path):
                self.logger.error(f"Stockfish executable not found at: {stockfish_path}. Black AI defaulting to Viper.")
                self.black_engine = EvaluationEngine(self.board, chess.BLACK, ai_config=self.black_ai_config)
                self.black_ai_config['engine'] = 'Viper' # Force engine name change
                self.black_ai_config['ai_type'] = 'random' # Force type change as Stockfish type invalid
            else:
                self.black_engine = StockfishHandler( # Renamed class
                    stockfish_path=stockfish_path,
                    elo_rating=stockfish_elo,
                    skill_level=stockfish_skill,
                    debug_mode=debug_stockfish
                )
        else:
            self.black_engine = EvaluationEngine(self.board, chess.BLACK, ai_config=self.black_ai_config)

        # Reset and configure engines for the new game board
        # Call reset on both, regardless of type, the reset method is implemented for both.
        self.white_engine.reset(self.board)
        self.black_engine.reset(self.board)

    def set_headers(self):
        # Set initial PGN headers
        white_depth = self.white_ai_config.get('depth', '#')
        black_depth = self.black_ai_config.get('depth', '#')
        
        # Get AI types for headers, defaulting to random if not set
        white_ai_type_header = self.white_ai_config.get('ai_type', 'random')
        black_ai_type_header = self.black_ai_config.get('ai_type', 'random')

        # Use configured engine name (e.g., 'Viper', 'Stockfish')
        white_engine_name = self.white_ai_config.get('engine', 'Unknown')
        black_engine_name = self.black_ai_config.get('engine', 'Unknown')

        if self.ai_vs_ai:
            self.game.headers["Event"] = "AI vs. AI Game"
            # Adjust header format to show engine type if Stockfish
            if white_engine_name.lower() == 'stockfish':
                self.game.headers["White"] = f"AI: {white_engine_name} (Elo {self.config.get('stockfish_config', {}).get('elo_rating', 'Max')})"
            else:
                self.game.headers["White"] = f"AI: {white_engine_name} via {white_ai_type_header} (Depth {white_depth})"
            
            if black_engine_name.lower() == 'stockfish':
                self.game.headers["Black"] = f"AI: {black_engine_name} (Elo {self.config.get('stockfish_config', {}).get('elo_rating', 'Max')})"
            else:
                self.game.headers["Black"] = f"AI: {black_engine_name} via {black_ai_type_header} (Depth {black_depth})"
        elif not self.ai_vs_ai and self.human_color_pref:
            # Human vs AI: One side is Human, the other is AI
            if self.human_color == chess.WHITE:
                self.game.headers["White"] = "Human"
                if black_engine_name.lower() == 'stockfish':
                    self.game.headers["Black"] = f"AI: {black_engine_name} (Elo {self.config.get('stockfish_config', {}).get('elo_rating', 'Max')})"
                else:
                    self.game.headers["Black"] = f"AI: {black_engine_name} via {black_ai_type_header} (Depth {black_depth})"
            else: # Human plays black
                if white_engine_name.lower() == 'stockfish':
                    self.game.headers["White"] = f"AI: {white_engine_name} (Elo {self.config.get('stockfish_config', {}).get('elo_rating', 'Max')})"
                else:
                    self.game.headers["White"] = f"AI: {white_engine_name} via {white_ai_type_header} (Depth {white_depth})"
                self.game.headers["Black"] = "Human"
            self.game.headers["Event"] = "Human vs. AI Game"

        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = socket.gethostbyname(socket.gethostname())
        self.game.headers["Round"] = "#"
        self.game.headers["Rated"] = str(self.rated)
        
    def set_colors(self):
        if self.ai_vs_ai:
            self.flip_board = False # White on bottom for AI vs AI
            self.human_color = None
            self.ai_color = None # No specific AI color in AI vs AI
        else: # Human vs AI mode
            # Convert human_color_pref to 'w'/'b' format
            if self.human_color_pref.lower() in ['white', 'w']:
                user_color = 'w'
            elif self.human_color_pref.lower() in ['black', 'b']:
                user_color = 'b'
            else:
                user_color = random.choice(['w', 'b']) # Fallback to random

            # Flip board if human plays black
            self.flip_board = (user_color == 'b')

            # Assign colors
            self.human_color = chess.WHITE if user_color == 'w' else chess.BLACK
            self.ai_color = chess.WHITE if self.human_color == chess.BLACK else chess.BLACK

    def _is_draw_condition(self, board):
        """Check if the current board position is a draw condition"""
        # Check for threefold repetition
        if board.can_claim_threefold_repetition():
            return True
        # Check for fifty-move rule
        if board.can_claim_fifty_moves():
            return True
        # Check for seventy-five move rule (since July 2014 rules)
        if board.is_seventyfive_moves():
            return True
        return False
    
    def handle_game_end(self):
        """Check and handle game termination with automatic threefold repetition detection"""
        
        # Check for automatic game ending conditions first (these don't require claims)
        # Note: _is_draw_condition should be passed for claim_draw=True logic
        if self.board.is_game_over(claim_draw=self._is_draw_condition(self.board)):
            # Update the game node so the saved game is the most up to date record
            self.game_node = self.game.end()
            result = self.board.result()
            self.game.headers["Result"] = result
            self.save_game_data() # This will save PGN and config, and trigger game result storage
            print(f"\nGame over: {result}")
            return True
        
        # Additional check for automatic 75-move rule (since July 2014 rules)
        if self.board.is_seventyfive_moves():
            result = "1/2-1/2"
            if self.logging_enabled and self.logger:
                self.logger.info("\nGame automatically drawn by seventy-five move rule!")
            self.game.headers["Result"] = result
            self.save_game_data()
            print(f"Game over: {result}")
            return True
        return False
    
    def record_evaluation(self):
        """Record evaluation score in PGN comments"""
        # Ensure correct engine is used for evaluation
        current_player_color = chess.WHITE if self.board.turn else chess.BLACK
        engine_for_eval = self.white_engine if current_player_color == chess.WHITE else self.black_engine
        
        # Evaluate from the perspective of the player whose turn it is
        # Note: The evaluation might be from the opponent's perspective if the previous move was AI's
        # and it changed the board. So, we ask for current player's perspective on the new board state.
        score = engine_for_eval.evaluate_position_from_perspective(self.board, current_player_color)
        self.current_eval = score
        
        if self.game_node.move:
            self.game_node.comment = f"Eval: {score:.2f}"
        else:
            self.game.comment = f"Initial Eval: {score:.2f}"

    def save_game_data(self):
        """Save the game data to files in the 'games' directory and to MetricsStore"""
        games_dir = "games"
        os.makedirs(games_dir, exist_ok=True)

        timestamp = self.game_start_timestamp # Use the fixed timestamp for this game
        
        # Save PGN file
        pgn_filepath = f"games/eval_game_{timestamp}.pgn"
        with open(pgn_filepath, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
        if self.logging_enabled and self.logger:
            self.logger.info(f"Game PGN saved to {pgn_filepath}")

        # Save configuration to YAML file
        config_filepath = f"games/eval_game_{timestamp}.yaml"
        with open(config_filepath, "w") as f:
            yaml.dump(self.config, f)
        if self.logging_enabled and self.logger:
            self.logger.info(f"Configuration saved to {config_filepath}")

        # Export log files
        log_filepath = f"games/eval_game_{timestamp}.log"
        eval_log_dir = "logging"
        
        # Collect all relevant log files, including those from StockfishHandler
        log_files_to_copy = []
        for f_name in os.listdir(eval_log_dir):
            if f_name.startswith("evaluation_engine.log") or \
               f_name.startswith("chess_game.log") or \
               f_name.startswith("stockfish_handler.log"): # Renamed log file
                log_files_to_copy.append(os.path.join(eval_log_dir, f_name))
        log_files_to_copy.sort() # Ensure consistent order
        
        with open(log_filepath, "w") as outfile:
            for log_file in log_files_to_copy:
                try:
                    with open(log_file, "r") as infile:
                        outfile.write(f"\n--- {os.path.basename(log_file)} ---\n")
                        outfile.write(infile.read())
                except Exception as e:
                    if self.logging_enabled and self.logger:
                        self.logger.warning(f"Could not read {log_file}: {e}")
        if self.logging_enabled and self.logger:
            self.logger.info(f"Combined logs saved to {log_filepath}")

        # Store game results in MetricsStore (if rated)
        if self.rated:
            game_id = self.current_game_db_id # Use the ID generated at new_game
            winner = self.board.result()
            white_player = self.game.headers.get("White", "Unknown")
            black_player = self.game.headers.get("Black", "Unknown")
            game_length = self.board.fullmove_number # Number of full moves

            self.metrics_store.add_game_result(
                game_id=game_id,
                timestamp=timestamp,
                winner=winner,
                game_pgn=str(self.game), # Convert PGN object to string
                white_player=white_player,
                black_player=black_player,
                game_length=game_length,
                # Pass AI configs for direct storage in game_results
                white_ai_config=self.white_ai_config,
                black_ai_config=self.black_ai_config
            )
            if self.logging_enabled and self.logger:
                self.logger.info(f"Game result for {game_id} stored in MetricsStore.")

    def quick_save_pgn(self, filename):
        """Quick save the current game to a PGN file"""
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
    
    def import_fen(self, fen_string):
        """Import a position from FEN notation"""
        try:
            # Create a new board from the FEN
            new_board = chess.Board(fen_string)
            
            # Validate the board is legal
            if not new_board.is_valid():
                if self.logging_enabled and self.logger:
                    self.logger.error(f"Invalid FEN position: {fen_string}")
                return False

            # Update the main board
            self.board = new_board
            self.game = chess.pgn.Game()
            self.game.setup(new_board)
            
            # Reset the game node pointer
            self.game_node = self.game

            # Re-initialize engines with the new board
            self._initialize_ai_engines()
            
            # Reset game state
            self.selected_square = None
            
            # Update PGN headers for custom position
            self.game.headers["Event"] = "Custom Position Game"
            self.game.headers["SetUp"] = "1"
            self.game.headers["FEN"] = fen_string

            if self.logging_enabled and self.logger:
                self.logger.info(f"Successfully imported FEN: {fen_string}")
            return True

        except Exception as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Unexpected problem importing FEN: {e}")
            return False

    # ===================================
    # ========= MOVE HANDLERS ===========
    
    def process_ai_move(self):
        """Process AI move for the current player"""

        ai_move = chess.Move.null()
        self.current_eval = 0.0  # Reset current evaluation before AI move
        
        # Determine current player, their AI config, and their engine instance
        current_player_color = chess.WHITE if self.board.turn else chess.BLACK
        current_ai_config = self.white_ai_config if current_player_color == chess.WHITE else self.black_ai_config
        current_ai_engine = self.white_engine if current_player_color == chess.WHITE else self.black_engine
        
        if self.logging_enabled and self.logger:
            self.logger.info(f"Processing AI move for {'White' if current_player_color == chess.WHITE else 'Black'} using {current_ai_config.get('engine', 'Unknown')} engine.")
        
        if self.show_thoughts:
            print(f"AI ({'White' if current_player_color == chess.WHITE else 'Black'}) is thinking...")

        move_start_time = time.perf_counter() # Start timing for the current AI move
        
        # Capture nodes_searched only for EvaluationEngine (Viper)
        nodes_before_search = 0
        if isinstance(current_ai_engine, EvaluationEngine):
            nodes_before_search = current_ai_engine.nodes_searched

        try:
            # The search function now returns the best move directly
            # For StockfishHandler, it handles its own internal timing/nodes and provides last_search_info
            ai_move = current_ai_engine.search(self.board, current_player_color, ai_config=current_ai_config)
            
            move_end_time = time.perf_counter()
            self.move_duration = move_end_time - move_start_time
            
            nodes_this_move = 0
            pv_line_info = ""
            
            # Retrieve nodes searched and PV line specifically from engine if available
            if isinstance(current_ai_engine, EvaluationEngine):
                nodes_after_search = current_ai_engine.nodes_searched
                nodes_this_move = nodes_after_search - nodes_before_search
                # For Viper, you would need to add PV tracking in search methods for this
                # pv_line_info = current_ai_engine.get_pv_line() # if implemented
            elif isinstance(current_ai_engine, StockfishHandler): # Renamed class
                stockfish_info = current_ai_engine.get_last_search_info()
                nodes_this_move = stockfish_info.get('nodes', 0)
                pv_line_info = stockfish_info.get('pv', '')
                # Overwrite current_eval with Stockfish's evaluation if it's Stockfish
                # Stockfish's score is from White's perspective.
                self.current_eval = stockfish_info.get('score', 0.0)
                if current_player_color == chess.BLACK:
                    self.current_eval = -self.current_eval # Negate for Black's perspective
            
            if isinstance(ai_move, chess.Move) and self.board.is_legal(ai_move):
                # Before pushing, capture FEN for move_metrics
                fen_before_move = self.board.fen()
                move_number = self.board.fullmove_number

                self.push_move(ai_move) # This also updates game_node and records PGN eval
                
                # After move, if it was Stockfish, self.current_eval is already set from Stockfish's info.
                # If it was Viper, self.current_eval is set by push_move's record_evaluation call.
                
                if self.logging_enabled and self.logger:
                    self.logger.info(f"AI ({current_player_color}) played: {ai_move} (Eval: {self.current_eval:.2f})")
                self.last_ai_move = ai_move

                # Store detailed move metrics if rated
                if self.rated:
                    self.metrics_store.add_move_metric(
                        game_id=self.current_game_db_id,
                        move_number=move_number,
                        player_color='w' if current_player_color == chess.WHITE else 'b',
                        move_uci=ai_move.uci(),
                        fen_before=fen_before_move,
                        evaluation=self.current_eval, # Eval after the move, from new player's perspective
                        ai_type=current_ai_config.get('ai_type', 'unknown'),
                        depth=current_ai_config.get('depth', 0),
                        nodes_searched=nodes_this_move,
                        time_taken=self.move_duration,
                        pv_line=pv_line_info
                    )
                    if self.logging_enabled and self.logger:
                        self.logger.debug(f"Move metrics for {ai_move.uci()} added to MetricsStore.")

            elif ai_move == chess.Move.null():
                # This could happen if _simple_search returns null move because no legal moves
                if self.board.is_game_over(): # If game is over, null move is expected
                    if self.logging_enabled and self.logger:
                        self.logger.info(f"AI ({current_player_color}) received null move, game likely over.")
                else: # Should not happen if game is not over and there are legal moves
                    if self.logging_enabled and self.logger:
                        self.logger.error(f"AI ({current_player_color}) returned null move unexpectedly. | FEN: {self.board.fen()}")
                    # Force exclude from metrics if AI failed to produce a move
                    if current_player_color == chess.WHITE:
                        self.white_ai_config['exclude_from_metrics'] = True
                    else:
                        self.black_ai_config['exclude_from_metrics'] = True
            else:
                # If the move is not a legal chess.Move object
                if self.logging_enabled and self.logger:
                    self.logger.error(f"AI ({current_player_color}) returned an invalid object type or illegal move: {ai_move}. Forcing random move. | FEN: {self.board.fen()}")
                
                # Force a random move as last resort fallback
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback_move = random.choice(legal_moves)
                    fen_before_move = self.board.fen()
                    move_number = self.board.fullmove_number
                    self.push_move(fallback_move)
                    if self.logging_enabled and self.logger:
                        self.logger.info(f"AI ({current_player_color}) played fallback move: {fallback_move} (Eval: {self.current_eval:.2f})")
                    self.last_ai_move = fallback_move

                    # Exclude this AI from metrics due to invalid move
                    if current_player_color == chess.WHITE:
                        self.white_ai_config['exclude_from_metrics'] = True
                    else:
                        self.black_ai_config['exclude_from_metrics'] = True
                    color_str = 'White' if current_player_color == chess.WHITE else 'Black'
                    if self.logger:
                        self.logger.info(f"{color_str} AI excluded from metrics this game due to invalid move.")
                    
                    # Store fallback move metrics, marking it as a fallback
                    if self.rated:
                        self.metrics_store.add_move_metric(
                            game_id=self.current_game_db_id,
                            move_number=move_number,
                            player_color='w' if current_player_color == chess.WHITE else 'b',
                            move_uci=fallback_move.uci(),
                            fen_before=fen_before_move,
                            evaluation=self.current_eval,
                            ai_type=current_ai_config.get('ai_type', 'unknown') + "_FALLBACK", # Indicate fallback
                            depth=0, # Fallback depth is 0
                            nodes_searched=0, # No nodes searched for fallback
                            time_taken=0.0, # Instant fallback
                            pv_line="FALLBACK: AI returned invalid move"
                        )
                else:
                    if self.logging_enabled and self.logger:
                        self.logger.warning(f"No legal moves for fallback. Game might be over or stalled. | FEN: {self.board.fen()}")

        except Exception as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"-- Hardstop Error -- Cannot process any AI moves: {e}. Forcing random move. | FEN: {self.board.fen()}")
            print(f"-- Hardstop Error -- Cannot process any AI moves: {e}")
            
            # Critical fallback: if an exception occurs during AI search
            legal_moves = list(self.board.legal_moves)
            if legal_moves:
                fallback_move = random.choice(legal_moves)
                fen_before_move = self.board.fen()
                move_number = self.board.fullmove_number
                self.push_move(fallback_move)
                if self.logging_enabled and self.logger:
                    self.logger.info(f"AI ({current_player_color}) played emergency fallback move: {fallback_move} (Eval: {self.current_eval:.2f})")
                self.last_ai_move = fallback_move
                
                # Exclude this AI from metrics due to critical error
                if current_player_color == chess.WHITE:
                    self.white_ai_config['exclude_from_metrics'] = True
                else:
                    self.black_ai_config['exclude_from_metrics'] = True
                color_str = 'White' if current_player_color == chess.WHITE else 'Black'
                if self.logger:
                    self.logger.info(f"{color_str} AI excluded from metrics this game due to critical error.")
                
                # Store fallback move metrics
                if self.rated:
                    self.metrics_store.add_move_metric(
                        game_id=self.current_game_db_id,
                        move_number=move_number,
                        player_color='w' if current_player_color == chess.WHITE else 'b',
                        move_uci=fallback_move.uci(),
                        fen_before=fen_before_move,
                        evaluation=self.current_eval,
                        ai_type=current_ai_config.get('ai_type', 'unknown') + "_CRITICAL_FALLBACK",
                        depth=0,
                        nodes_searched=0,
                        time_taken=0.0,
                        pv_line=f"CRITICAL FALLBACK: {e}"
                    )
            else:
                if self.logging_enabled and self.logger:
                    self.logger.warning(f"No legal moves for emergency fallback. Game might be over or stalled. | FEN: {self.board.fen()}")

        # Print AI move and evaluation to console (as in original)
        if self.show_eval:
            print(f"AI ({'White' if current_player_color == chess.WHITE else 'Black'}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
        else:
            print(f"AI ({'White' if current_player_color == chess.WHITE else 'Black'}) plays: {ai_move}")
        if self.logging_enabled and self.logger:
            self.logger.info(f"AI ({current_player_color}) played: {ai_move} (Eval: {self.current_eval:.2f}) | Time: {self.move_duration:.4f}s | Nodes: {nodes_this_move}")

    def push_move(self, move):
        """ Test and push a move to the board and game node """
        if not self.board.is_valid():
            if self.logging_enabled and self.logger:
                self.logger.error(f"Invalid board state detected! | FEN: {self.board.fen()}")
            return False
        
        # Prepare the move for pushing
        if self.logging_enabled and self.logger:
            self.logger.info(f"Attempting to push move from {'White AI' if self.board.turn == chess.WHITE else 'Black AI'}: {move} | FEN: {self.board.fen()}")
        
        if isinstance(move, str): # Ensure move is a chess.Move object
            try:
                move = chess.Move.from_uci(move)
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Converted to chess.Move move from UCI string before push: {move}")
            except ValueError:
                if self.logging_enabled and self.logger:
                    self.logger.error(f"Invalid UCI string received: {move}")
                return False
        
        if not self.board.is_legal(move):
            if self.logging_enabled and self.logger:
                self.logger.info(f"Illegal move blocked from being pushed: {move}")
            return False
        
        try:
            # Push the move to the board and game node
            if self.logging_enabled and self.logger:
                self.logger.info(f"No remaining checks, pushing move: {move} | FEN: {self.board.fen()}")
            
            self.board.push(move)
            self.game_node = self.game_node.add_variation(move)
            self.last_move = move  # Update last move made by any player
            if self.logging_enabled and self.logger:
                self.logger.info(f"Move pushed successfully: {move} | FEN: {self.board.fen()}")
            
            # Player has changed since move occurred, so update current player
            self.current_player = chess.WHITE if self.board.turn else chess.BLACK
            
            # Only record evaluation for PGN comment if current engine is Viper
            # Stockfish's evaluation is captured directly in process_ai_move
            current_engine_name = self.white_ai_config['engine'] if self.current_player == chess.BLACK else self.black_ai_config['engine'] # This looks at NEXT player's engine name
            if current_engine_name.lower() != 'stockfish':
                self.record_evaluation() # Record the evaluation to the game node comments
            
            self.quick_save_pgn("logging/active_game.pgn") # Update the in progress game file
            
            return True
        except ValueError as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"ValueError pushing move {move}: {e}. Dumping PGN to error_dump.pgn")
            self.quick_save_pgn("games/game_error_dump.pgn")
            return False

    # =============================================
    # ============ MAIN GAME LOOP =================

    def run(self):
        running = True
        game_count_remaining = self.game_count
        
        print(f"White AI: {self.white_eval_engine} via {self.white_ai_type} vs Black AI: {self.black_eval_engine} via {self.black_ai_type}")
        if self.logging_enabled and self.logger:
            self.logger.info(f"White AI: {self.white_eval_engine} via {self.white_ai_type} vs Black AI: {self.black_eval_engine} via {self.black_ai_type}")
        
        # Initialize engines here before the loop, so they are ready for first game
        # They will be reset at the start of each new game
        self._initialize_ai_engines()


        while running and ((self.ai_vs_ai and game_count_remaining >= 1)):
            if self.logging_enabled and self.logger:
                self.logger.info(f"Running chess game loop: {self.game_count - game_count_remaining}/{self.game_count} completed.")
            
            # Process events (even in headless mode for quit detection)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            # Main game logic for AI vs AI
            if not self.board.is_game_over(claim_draw=self._is_draw_condition(self.board)) and self.board.is_valid():
                self.process_ai_move()
            else:
                # Game is over, handle it
                if self.handle_game_end():
                    game_count_remaining -= 1
                    if game_count_remaining == 0:
                        running = False
                        if self.logging_enabled and self.logger:
                            self.logger.info(f'All {self.game_count} games complete, exiting...')
                    else:
                        if self.logging_enabled and self.logger:
                            self.logger.info(f'Game {self.game_count - game_count_remaining}/{self.game_count} complete, starting next...')
                        # Start a new game with original settings and a new unique ID
                        self.game_start_timestamp = get_timestamp()
                        self.current_game_db_id = f"eval_game_{self.game_start_timestamp}.pgn"
                        self.new_game(self.starting_position)

            self.clock.tick(MAX_FPS) # Control loop speed, even if headless
            
        # Ensure pygame is quit and engines are closed on exit
        if pygame.get_init():
            pygame.quit()
        # Ensure Stockfish processes are terminated
        if hasattr(self, 'white_engine') and self.white_engine:
            if isinstance(self.white_engine, StockfishHandler): # Renamed class
                self.white_engine.quit()
        if hasattr(self, 'black_engine') and self.black_engine:
            if isinstance(self.black_engine, StockfishHandler): # Renamed class
                self.black_engine.quit()

if __name__ == "__main__":
    game = ChessGame()
    game.run()
    # Ensure the metrics store is closed properly when the application exits
    game.metrics_store.close()