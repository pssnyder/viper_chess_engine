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
from evaluation_engine import EvaluationEngine

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
            
        # Initialize Pygame
        pygame.init()
        self.clock = pygame.time.Clock()
        # Enable logging
        self.logging_enabled = self.config['debug']['enable_logging']
        self.show_thoughts = self.config['debug']['show_thinking']
        self.logger = chess_game_logger  # Use the module-level logger
        if self.logging_enabled:
            self.logger.debug("Logging enabled for Evaluation Engine")
        else:
            self.show_thoughts = False
    

        # Initialize game settings
        self.human_color_pref = self.config['game_config']['human_color']
        if self.starting_position == None:
            self.starting_position = self.config.get('game_config', {}).get('starting_position', 'default')
        print("Initializing headless AI vs AI mode. No chess GUI will be shown.")
        print("Press Ctrl+C in the terminal to stop the game early.")

        # Initialize piece fallback values
        self.piece_values = {
            chess.KING: 0,
            chess.QUEEN: 9,
            chess.ROOK: 5,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3,
            chess.PAWN: 1
        }
 
        # Initialize AI
        self.game_count = self.config.get('game_config', {}).get('ai_game_count', 0)
        self.ai_vs_ai = self.config.get('game_config', {}).get('ai_vs_ai', False)
        self.ai_types = self.config.get('ai_types', [])
        self.white_ai_type = self.config.get('white_ai_config', {}).get('ai_type', 'random')
        self.black_ai_type = self.config.get('black_ai_config', {}).get('ai_type', 'random')
        self.white_eval_engine = self.config.get('white_ai_config', {}).get('engine', 'default')
        self.black_eval_engine = self.config.get('black_ai_config', {}).get('engine', 'default')
        self.white_ai_config = self.config.get('white_ai_config', {})
        self.black_ai_config = self.config.get('black_ai_config', {})
        self.exclude_white_performance = self.white_ai_config.get('exclude_from_metrics', False)
        self.exclude_black_performance = self.black_ai_config.get('exclude_from_metrics', False)
        # Ensure ai_config always has required keys
        if 'ai_type' not in self.white_ai_config:
            self.white_ai_config['ai_type'] = 'random'
        if 'ai_type' not in self.black_ai_config:
            self.black_ai_config['ai_type'] = 'random'
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Initializing ChessGame with {self.starting_position} position")

            # Log AI types and engines
            self.logger.debug(f"White AI Type: {self.white_ai_type}, Engine: {self.white_eval_engine}")
            self.logger.debug(f"Black AI Type: {self.black_ai_type}, Engine: {self.black_eval_engine}")
        # Initialize debug settings
        self.show_eval = self.config.get('debug', {}).get('show_evaluation', False)
        self.logging_enabled = self.config.get('debug', {}).get('enable_logging', False)
        self.show_thoughts = self.config.get('debug', {}).get('show_thinking', False)
        self.logger = chess_game_logger  # Use the module-level logger
        if self.logging_enabled:
            self.logger.info("Chess game logger initialized")
        else:
            self.show_thoughts = False
        
        # Initialize board and new game
        self.new_game(self.starting_position)
        
        # Set colors
        self.set_colors()
        
        # Set headers
        self.set_headers()

        # Initialize move timing
        self.move_start_time = 0
        self.move_end_time = 0
        self.move_duration = 0

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
        self.current_eval = 0.0
        self.ai_color = chess.WHITE
        self.human_color = chess.BLACK
        self.current_player = chess.WHITE if self.board.turn else chess.BLACK
        self.last_ai_move = chess.Move.null() # Reset AI's last move
        self.last_move = chess.Move.null() # Reset last move made by any player
        self.move_history = []  # Reset move history
        
        # Reset AI engines if they exist
        if hasattr(self, 'white_engine') and self.white_engine:
            self.white_engine.reset(self.board)
        if hasattr(self, 'black_engine') and self.black_engine:
            self.black_engine.reset(self.board)

        # Reset PGN headers and file
        self.set_headers()
        self.quick_save_pgn("logging/active_game.pgn")
        
        # Reset move history
        self.move_history = []
        if self.logging_enabled and self.logger:
            self.logger.info(f"Starting new game.")
    
    def set_headers(self):
        # Set initial PGN headers
        white_depth = math.floor(self.white_ai_config['depth']/2) if self.white_ai_config['depth'] else 0
        black_depth = math.floor(self.black_ai_config['depth']/2) if self.black_ai_config['depth'] else 0

        if self.ai_vs_ai:
            self.game.headers["Event"] = "AI vs. AI Game"
            self.game.headers["White"] = f"AI: {self.white_eval_engine} via {self.white_ai_type} ({white_depth} ply)"
            self.game.headers["Black"] = f"AI: {self.black_eval_engine} via {self.black_ai_type} ({black_depth} ply)"
        elif self.ai_vs_ai is False and self.human_color_pref:
            self.game.headers["Event"] = "Human vs. AI Game"
            self.game.headers["Black"] = "Human" if self.ai_color == chess.WHITE else f"AI: {self.black_eval_engine} via {self.black_ai_type} ({black_depth} ply)"
            self.game.headers["White"] = "Human" if self.ai_color == chess.BLACK else f"AI: {self.white_eval_engine} via {self.white_ai_type} ({white_depth} ply)"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = socket.gethostbyname(socket.gethostname())
        self.game.headers["Round"] = "#"
        
    def set_colors(self):
        if self.ai_vs_ai:
            self.flip_board = False # White on bottom for AI vs AI
            self.human_color = None
            self.ai_color = None
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
        if self.board.is_game_over(claim_draw=self._is_draw_condition(self.board)):
            # Update the game node so the saved game is the most up to date record
            self.game_node = self.game.end()
            result = self.board.result()
            self.game.headers["Result"] = result
            self.save_game_data()
            print(f"\nGame over: {result}")
            return True
        
        # Check for threefold repetition and fifty-move rule (requires claim_draw=True)
        if self.board.is_game_over(claim_draw=self.white_engine._is_draw_condition(self.board)):
            result = self.board.result(claim_draw=self.white_engine._is_draw_condition(self.board))

            # Determine the specific draw condition for better feedback
            if self.board.can_claim_threefold_repetition():
                if self.logging_enabled and self.logger:
                    self.logger.info("\nGame drawn by threefold repetition!")
            elif self.board.can_claim_fifty_moves():
                if self.logging_enabled and self.logger:
                    self.logger.info("\nGame drawn by fifty-move rule!")
            else:
                if self.logging_enabled and self.logger:
                    self.logger.info("\nGame drawn!")
            self.game.headers["Result"] = result
            self.save_game_data()
            print(f"Game over: {result}")
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
        score = self.white_engine.evaluate_position(self.board)
        self.current_eval = score
        if self.game_node.move:
            self.game_node.comment = f"Eval: {score:.2f}"
        else:
            self.game.comment = f"Initial Eval: {score:.2f}"

    def save_game_data(self):
        """Save the game data to files in the 'games' directory"""
        # Create games directory if it doesn't exist
        games_dir = "games"
        
        if not os.path.exists(games_dir):
            os.makedirs(games_dir, exist_ok=True)
            if self.logging_enabled and self.logger:
                self.logger.info(f"Created directory: {games_dir}")

        # Generate filename with timestamp if not provided
        timestamp = get_timestamp()
        
        # export all game data to files
        try:
            # Save the game to PGN file
            pgn_filepath = f"games/eval_game_{timestamp}.pgn"
            with open(pgn_filepath, "w") as f:
                exporter = chess.pgn.FileExporter(f)
                self.game.accept(exporter)
            if self.logging_enabled and self.logger:
                self.logger.info(f"Game saved to {pgn_filepath}")
        except IOError as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Unexpected problem saving game: {e}")
        try:
            # Save the configuration to YAML file
            config_filepath = f"games/eval_game_{timestamp}.yaml"
            with open(config_filepath, "w") as f:
                yaml.dump(self.config, f)
            if self.logging_enabled and self.logger:
                self.logger.info(f"Configuration saved to {config_filepath}")
        except IOError as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Unexpected problem saving configuration: {e}")
        try:
            # Export all evaluation_engine.log files (including rotated logs)
            log_filepath = f"games/eval_game_{timestamp}.log"
            eval_log_dir = "logging"
            eval_log_base = "evaluation_engine.log"
            eval_log_files = [os.path.join(eval_log_dir, f) for f in os.listdir(eval_log_dir)
                      if f.startswith(eval_log_base)]
            # Sort to maintain order: .log, .log.1, .log.2, etc.
            eval_log_files.sort()
            with open(log_filepath, "w") as outfile:
                for log_file in eval_log_files:
                    try:
                        with open(log_file, "r") as infile:
                            outfile.write(f"\n--- {os.path.basename(log_file)} ---\n")
                            outfile.write(infile.read())
                    except Exception as e:
                        if self.logging_enabled and self.logger:
                            self.logger.warning(f"Could not read {log_file}: {e}")
            if self.logging_enabled and self.logger:
                self.logger.info(f"Log saved to {log_filepath}")
        except IOError as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Unexpected problem saving log: {e}")

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

            # Update engine if it exists
            if self.white_engine:
                self.white_engine.board = self.board
            if self.black_engine:
                self.black_engine.board = self.board

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

        # Synchronize AI engines with the current game board before selecting a move
        if self.board is not self.white_engine.board:
            # Synchronize white evaluation engine with the current game board
            if not self.white_engine.sync_with_game_board(self.board) and self.logger:
                self.logger.error("Failed to synchronize white evaluation engine with game board.")
            return
        if self.board is not self.black_engine.board:
            # Synchronize black evaluation engine with the current game board
            if not self.black_engine.sync_with_game_board(self.board) and self.logger:
                self.logger.error("Failed to synchronize black evaluation engine with game board.")
            return
        
        # Initialize AI move
        ai_move = chess.Move.null()
        self.current_eval = 0.0  # Reset current evaluation before AI move
        if self.logging_enabled and self.logger:
            self.logger.info("Processing AI move for %s", "White" if self.board.turn else "Black")
        
        # Attempt to find a move using the AI engine
        if self.show_thoughts:
            print(f"AI ({'White' if self.board.turn else 'Black'}) is thinking...")
        try:
            self.current_player = chess.WHITE if self.board.turn else chess.BLACK
            # Use the appropriate engine based on the current player
            if self.current_player == chess.WHITE:
                self.white_engine.board = self.board.copy()  # Ensure the board is copied to avoid modifying the original
                self.current_eval = self.white_engine.evaluate_position(self.board)
                ai_move = self.white_engine.search(self.board, self.current_player)
            else:
                self.black_engine.board = self.board.copy()  # Ensure the board is copied to avoid modifying the original
                self.current_eval = self.black_engine.evaluate_position(self.board)
                ai_move = self.black_engine.search(self.board, self.current_player)
            
            # Validate the move returned by the AI against the current game board
            if isinstance(ai_move, chess.Move) and self.board.is_legal(ai_move):
                # If the move is a valid chess move and is legal for this board, push it to the board and game node
                self.push_move(ai_move)
                self.game_node = self.game_node.add_variation(ai_move)
                if self.logging_enabled and self.logger:
                    self.logger.info("AI (%s) played: %s (Eval: %.2f)", self.current_player, ai_move, self.current_eval)
                self.last_ai_move = ai_move
            elif isinstance(ai_move, chess.Move) and not self.board.is_legal(ai_move):
                # If the move is a valid chess move but not legal for this board, log the issue, and attempt to call for a random move
                if self.logging_enabled and self.logger:
                    self.logger.warning(f"AI ({self.current_player}) played an illegal move: {ai_move}. | FEN: {self.board.fen()}")
                if self.current_player == chess.WHITE:
                    self.white_ai_config['exclude_from_metrics'] = True
                    self.white_engine._random_search(self.board, self.current_player)
                else:
                    self.black_ai_config['exclude_from_metrics'] = True
                    self.black_engine._random_search(self.board, self.current_player)

            elif isinstance(ai_move, str):
                # If the move is a string, log the issue and attempt to convert it to a chess.Move object
                if self.logging_enabled and self.logger:
                    self.logger.error(f"AI ({self.current_player}) returned a string move: {ai_move}. Attempting to convert to chess.Move.")
                try:
                    ai_move = chess.Move.from_uci(ai_move)
                    if self.board.is_legal(ai_move):
                        self.push_move(ai_move)
                        self.game_node = self.game_node.add_variation(ai_move)
                        if self.logging_enabled and self.logger:
                            self.logger.info("AI (%s) played: %s (Eval: %.2f)", self.current_player, ai_move, self.current_eval)
                        self.last_ai_move = ai_move
                    else:
                        # If the converted move is not legal, attempt to call for a random move
                        if self.logging_enabled and self.logger:
                            self.logger.warning(f"Converted move is illegal: {ai_move}. | FEN: {self.board.fen()}")
                        if self.current_player == chess.WHITE:
                            self.white_ai_config['exclude_from_metrics'] = True
                            self.white_engine._random_search(self.board, self.current_player)
                        else:
                            self.black_ai_config['exclude_from_metrics'] = True
                            self.black_engine._random_search(self.board, self.current_player)
                except ValueError as e:
                    if self.logging_enabled and self.logger:
                        self.logger.error(f"Failed to convert AI move from string: {e}")
            elif not isinstance(ai_move, chess.Move) or ai_move is None:
                # Emergency fallback: If the move is not valid, not a chess.Move object, or is None, log the issue and manually select a random legal move
                if self.logging_enabled and self.logger:
                    self.logger.error(f"Could not process any AI move, falling back on manually selected random legal move: {ai_move} invalid for {self.current_player}. | FEN: {self.board.fen()}")
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves)
                    ai_move = fallback
                    self.push_move(fallback)
                # Exclude this AI config from metrics due to invalid move
                if self.current_player == chess.WHITE:
                    self.white_ai_config['exclude_from_metrics'] = True
                else:
                    self.black_ai_config['exclude_from_metrics'] = True
                color_str = 'White' if self.current_player == chess.WHITE else 'Black'
                if self.logger:
                    self.logger.info(f"{color_str} AI excluded from metrics this game due to invalid move.")
            
            # If the user has enabled evaluation display, print the current board evaluation in the terminal after the move
            if self.show_eval:
                print(f"AI ({self.current_player}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
            else:
                print(f"AI ({self.current_player}) plays: {ai_move}")
            if self.logging_enabled and self.logger:
                self.logger.info("AI (%s) played: %s (Eval: %.2f)", self.current_player, ai_move, self.current_eval)
        except Exception as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"-- Hardstop Error -- Cannot process any AI moves: {e}")
            print(f"-- Hardstop Error -- Cannot process any AI moves: {e}")

    def push_move(self, move):
        """ Test and push a move to the board and game node """
        if not self.board.is_valid():
            if self.logging_enabled and self.logger:
                self.logger.error(f"Invalid board state detected! | FEN: {self.board.fen()}")
            return False
        # Prepare the move for pushing
        if self.logging_enabled and self.logger:
            self.logger.info(f"Attempting to push move from {'White AI' if self.current_player == chess.WHITE else 'Black AI'}: {move} | FEN: {self.board.fen()}")
        if isinstance(move, str) or hasattr(move, 'uci'):
            move = chess.Move.from_uci(move)
            if self.logging_enabled and self.logger:
                self.logger.info(f"Converted to chess.Move move from UCI string before push: {move}")
        else:
            if self.logging_enabled and self.logger:
                self.logger.info(f"No conversion needed, using move object to push: {move}")
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
            # Player has changed since move occured, so update current player
            self.current_player = chess.WHITE if self.board.turn else chess.BLACK
            self.record_evaluation() # Record the evaluation to the game node comments
            self.quick_save_pgn("logging/active_game.pgn") # Update the in progress game file
            return True
        except ValueError:
            self.quick_save_pgn("games/game_error_dump.pgn")
            return False

    # ==========================================
    # ============== AI CONFIG =================

    def ai_move(self):
        # Determine current player and config
        current_player = self.board.turn  # expects a chess.Board object
        ai_config = self.white_ai_config if current_player else self.black_ai_config

        # Defensive: ensure ai_config is a dict
        if not isinstance(ai_config, dict):
            if self.logger:
                self.logger.error("AI config is not a dictionary.")
            return None

        engine = getattr(self, 'white_engine', None) if current_player else getattr(self, 'black_engine', None)

        # Defensive: ensure engine exists
        if engine is None:
            if self.logger:
                self.logger.error("No engine instance found for current player.")
            return None

        # Route to the engine with correct settings
        try:
            chosen_move = engine.search(self.board, current_player, ai_config)
        except KeyError as e:
            if self.logger:
                self.logger.error(f"AI config missing key: {e}. ai_config={ai_config}")
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"AI move error: {e}")
            return None

        # Store the last AI move
        self.last_ai_move = chosen_move if chosen_move else None
        return chosen_move if chosen_move else None

    # =============================================
    # ============ MAIN GAME LOOP =================

    def run(self):
        running = True
        game_count = self.game_count
        print(f"White AI: {self.white_eval_engine} via {self.white_ai_type} vs Black AI: {self.black_eval_engine} via {self.black_ai_type}")
        if self.logging_enabled and self.logger:
            self.logger.info(f"White AI: {self.white_eval_engine} via {self.white_ai_type} vs Black AI: {self.black_eval_engine} via {self.black_ai_type}")
        # Configure AI engines per color, always pass ai_config
        self.white_engine = EvaluationEngine(self.board, chess.WHITE, ai_config=self.white_ai_config)
        self.black_engine = EvaluationEngine(self.board, chess.BLACK, ai_config=self.black_ai_config)

        while running and ((self.ai_vs_ai and game_count >= 1)):
            if self.logging_enabled and self.logger:
                self.logger.info(f"Running chess game loop: {self.game_count - game_count}/{self.game_count} remaining")
                self.white_engine.logger.info(f"Running chess game loop: {self.game_count - game_count}/{self.game_count} remaining")
            move_start_time = pygame.time.get_ticks()
            move_end_time = 0
            move_duration = 0

            # Process events (even in headless mode for quit detection)
            for event in pygame.event.get():
                # Set the current player
                self.current_player = chess.WHITE if self.board.turn else chess.BLACK
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN or self.ai_vs_ai:
                    if not self.board.is_game_over(claim_draw=self._is_draw_condition(self.board)) and self.board.is_valid():
                        self.process_ai_move()

            # Check game end conditions
            if self.handle_game_end():
                game_count -= 1
                if game_count == 0:
                    running = False
                    pygame.quit()
                    self.record_evaluation()
                    self.save_game_data()
                    self.quick_save_pgn("logging/active_game.pgn")
                    if self.ai_vs_ai and self.game_count > 1 and self.game_count != game_count:
                        if self.logging_enabled and self.logger:
                            self.logger.info(f'All {self.game_count} games complete, exiting...')
                    elif self.ai_vs_ai and self.game_count != game_count:
                        if self.logging_enabled and self.logger:
                            self.logger.info('Game complete')
                elif self.ai_vs_ai and self.game_count != game_count:
                    if self.logging_enabled and self.logger:
                        self.logger.info(f'Game {self.game_count - game_count}/{self.game_count} complete...')
                    self.new_game(self.starting_position)
    # if a pygame instance is still running then stop it
    if pygame.get_init():
        pygame.quit()
if __name__ == "__main__":
    game = ChessGame()
    game.run()