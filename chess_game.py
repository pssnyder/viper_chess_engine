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
import logging.handlers
import threading
import time
import socket
from evaluation_engine import EvaluationEngine

# Pygame constants
WIDTH, HEIGHT = 640, 640
DIMENSION = 8
SQ_SIZE = WIDTH // DIMENSION
MAX_FPS = 15
IMAGES = {}

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
        backupCount=3
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
        self.fen_position = fen_position

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
        self.watch_mode = self.config['game_config']['watch_mode']
        self.font = pygame.font.SysFont('Arial', 24)
        self.small_font = pygame.font.SysFont('Arial', 16)
        self.width = WIDTH  # Ensure width attribute exists
        self.BLACK = (0, 0, 0)  # Ensure BLACK attribute exists
        
        # Initialize display, if enabled
        if self.watch_mode:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('V7P3R\'s Chess Bot')
            self.load_images()
        else:
            self.screen = None
            if self.logging_enabled and self.logger:
                self.logger.info("Running in headless mode - no visual display")
            self.headless_mode()

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
        self.white_bot_type = self.config.get('white_ai_config', {}).get('ai_type', 'default')
        self.black_bot_type = self.config.get('black_ai_config', {}).get('ai_type', 'default')
        self.white_eval_engine = self.config.get('white_ai_config', {}).get('engine', 'default')
        self.black_eval_engine = self.config.get('black_ai_config', {}).get('engine', 'default')
        self.white_ai_config = self.config.get('white_ai_config', {})
        self.black_ai_config = self.config.get('black_ai_config', {})

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
        self.new_game()
        
        # Set colors
        self.set_colors()
        
        # Set headers
        self.set_headers()

        self.screen_ready = False
        self.ai_busy = False
        self.ai_move_result = None
        self.ai_thread = None
        self.move_start_time = 0
        self.move_end_time = 0
        self.move_duration = 0

    # ================================
    # ====== GAME CONFIGURATION ======
    
    def new_game(self, fen_position=None):
        """Reset the game state for a new game"""
        self.board = chess.Board(fen=fen_position) if fen_position else chess.Board()
        self.game = chess.pgn.Game()
        self.game_node = self.game # Initialize new game node
        self.selected_square = None
        self.last_ai_move = None
        self.current_eval = None
        self.ai_color = None 
        self.human_color = None 
        self.current_player = self.board.turn
        self.last_ai_move = None # Reset AI's last move
        self.last_move = None # Reset last move made by any player
        self.move_history = []  # Reset move history for display
        # Reset AI engines if they exist
        if hasattr(self, 'white_engine') and self.white_engine:
            self.white_engine.reset(self.board)
        if hasattr(self, 'black_engine') and self.black_engine:
            self.black_engine.reset(self.board)

        # Reset PGN headers
        self.set_headers()
        
        # Reset move history
        self.move_history = []
        if self.logging_enabled and self.logger:
            self.logger.info(f"Starting new game.")
        if self.watch_mode:
            self.draw_board()
            self.draw_pieces()
            self.update_display()
            if self.game_count > 1:
                print(f"Starting new game, currently playing {self.game_count} game series")
            else:    
                print("Starting new game...")
    
    def set_headers(self):
        # Set initial PGN headers
        if self.ai_vs_ai:
            self.game.headers["Event"] = "AI vs. AI Game"
            self.game.headers["White"] = f"AI: {self.white_eval_engine} via {self.white_bot_type} ({self.white_ai_config['depth']/2} ply)"
            self.game.headers["Black"] = f"AI: {self.black_eval_engine} via {self.black_bot_type} ({self.black_ai_config['depth']/2} ply)"
        else:
            self.game.headers["Event"] = "Human vs. AI Game"
            self.game.headers["White"] = f"AI: {self.white_eval_engine} via {self.white_bot_type} ({self.white_ai_config['depth']/2} ply)" if self.ai_color == chess.WHITE else "Human"
            self.game.headers["Black"] = "Human" if self.ai_color == chess.WHITE else f"AI: {self.black_eval_engine} via {self.black_bot_type} ({self.black_ai_config['depth']/2} ply)"
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
            self.ai_color = not self.human_color

    def load_images(self):
        pieces = ['wp', 'wN', 'wb', 'wr', 'wq', 'wk',
                 'bp', 'bN', 'bb', 'br', 'bq', 'bk']
        for piece in pieces:
            try:
                IMAGES[piece] = pygame.transform.scale(
                    pygame.image.load(resource_path(f"images/{piece}.png")),
                    (SQ_SIZE, SQ_SIZE)
                )
            except pygame.error:
                if self.logging_enabled and self.logger:
                    self.logger.warning(f"Could not load image for {piece}")

    def draw_board(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        colors = [pygame.Color("#a8a9a8"),pygame.Color("#d8d9d8")]
        for r in range(DIMENSION):
            for c in range(DIMENSION):
                # Calculate chess square coordinates
                if self.flip_board:
                    file = 7 - c
                    rank = r
                else:
                    file = c
                    rank = 7 - r

                # Determine color based on chess square
                color = colors[(file + rank) % 2]
                pygame.draw.rect(
                    self.screen,
                    color,
                    pygame.Rect(c*SQ_SIZE, r*SQ_SIZE, SQ_SIZE, SQ_SIZE)
                )

    def draw_pieces(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        # Draw pieces
        for r in range(DIMENSION):
            for c in range(DIMENSION):
                # Calculate chess square based on perspective
                if self.flip_board:
                    file = 7 - c
                    rank = r # Black's perspective
                else:
                    file = c
                    rank = 7 - r # White's perspective

                square = chess.square(file, rank)
                piece = self.board.piece_at(square)

                if piece:
                    # Calculate screen position
                    screen_x = c * SQ_SIZE
                    screen_y = r * SQ_SIZE

                    piece_key = self._piece_image_key(piece)
                    if piece_key in IMAGES:
                        self.screen.blit(IMAGES[piece_key], (screen_x, screen_y))

    def _piece_image_key(self, piece):
        color = 'w' if piece.color == chess.WHITE else 'b'
        symbol = piece.symbol().upper()
        return f"{color}N" if symbol == 'N' else f"{color}{symbol.lower()}"

    def draw_move_hints(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        if self.selected_square:
            # Get all legal moves from selected square
            for move in self.board.legal_moves:
                if move.from_square == self.selected_square:
                    # Convert destination square to screen coordinates
                    dest_screen_x, dest_screen_y = self.chess_to_screen(move.to_square)

                    # Draw hint circle
                    center = (dest_screen_x + SQ_SIZE//2, dest_screen_y + SQ_SIZE//2)
                    pygame.draw.circle(
                        self.screen,
                        pygame.Color('green'),
                        center,
                        SQ_SIZE//5
                    )

    def draw_move_history(self):
        if not self.watch_mode or self.screen is None:
            return
        history_x = self.width - 200
        history_y = 50

        history_surface = self.font.render("Move History", True, self.BLACK)
        self.screen.blit(history_surface, (history_x, history_y))

        for i, move in enumerate(self.move_history[-10:]):  # Show last 10 moves
            move_text = f"{i+1}. {move}"
            move_surface = self.small_font.render(move_text, True, self.BLACK)
            self.screen.blit(move_surface, (history_x, history_y + 40 + i*20))

    def draw_eval(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        if self.current_eval is not None:
            # Display evaluation from current player's perspective
            display_eval = self.current_eval

            # Format with proper sign
            eval_str = f"{display_eval:+.2f}"

            # Color coding: green for positive, red for negative, black for neutral
            if abs(display_eval) < 0.5:
                color = (0, 0, 0) # Black for neutral
            elif display_eval > 0:
                color = (0, 255, 0) # Green for advantage
            else:
                color = (255, 0, 0) # Red for disadvantage

            # Render text
            text = self.font.render(f"Eval: {eval_str}", True, color)
            self.screen.blit(text, (WIDTH-150, 10))

            # Also show depth
            if self.board.turn == chess.WHITE:
                self.depth = self.white_engine.depth
            else:
                self.depth = self.black_engine.depth
            depth_text = self.font.render(f"Depth: {self.depth}", True, (0, 0, 0))
            self.screen.blit(depth_text, (WIDTH-150, 35))
            
            # Show current turn in AI vs AI mode (move has already changed sides so references are backwards)
            if self.ai_vs_ai:
                turn_text = f"Turn: {'White' if self.current_player == chess.BLACK else 'Black'}"
                turn_surface = self.font.render(turn_text, True, (0, 0, 0))
                self.screen.blit(turn_surface, (WIDTH-150, 60))

    def chess_to_screen(self, square):
        """Convert chess board square to screen coordinates"""
        file = chess.square_file(square)
        rank = chess.square_rank(square)

        if self.flip_board:
            screen_file = 7 - file
            screen_rank = rank
        else:
            screen_file = file
            screen_rank = 7 - rank

        return (screen_file * SQ_SIZE, screen_rank * SQ_SIZE)

    def update_display(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        """Optimized display update"""
        if not hasattr(self, 'display_needs_update'):
            self.display_needs_update = True  # Initialize flag

        if self.display_needs_update:
            self.draw_board()
            self.draw_pieces()

            # Highlighting
            if self.selected_square is not None:
                self.draw_move_hints()
                self.highlight_selected_square()

            if self.last_ai_move:
                self.highlight_last_move()

            # Draw the evaluation score
            self.draw_eval()

            pygame.display.flip()
            self.display_needs_update = False  # Reset flag
            self.screen_ready = True  # Mark screen as ready after first draw

    def mark_display_dirty(self):
        """Mark the display as needing an update."""
        self.display_needs_update = True

    def highlight_selected_square(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        if self.selected_square:
            screen_x, screen_y = self.chess_to_screen(self.selected_square)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('blue'))
            self.screen.blit(s, (screen_x, screen_y))

    def highlight_last_move(self):
        if not self.watch_mode or self.screen is None:
            return  # Skip drawing in headless mode
        """Highlight AI's last move on the board"""
        if self.last_ai_move:
            screen_x, screen_y = self.chess_to_screen(self.last_ai_move)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('yellow'))
            self.screen.blit(s, (screen_x, screen_y))

    def handle_game_end(self):
        """Check and handle game termination with automatic threefold repetition detection"""
        
        # Check for automatic game ending conditions first (these don't require claims)
        if self.board.is_game_over():
            # Update the game node so the saved game is the most up to date record
            self.game_node = self.game.end()
            result = self.board.result()
            self.game.headers["Result"] = result
            self.save_game_data()
            print(f"\nGame over: {result}")
            return True
        
        # Check for threefold repetition and fifty-move rule (requires claim_draw=True)
        if self.board.is_game_over(claim_draw=True):
            result = self.board.result(claim_draw=True)
            
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
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
    
    def headless_mode(self):
        """Initialize pygame for headless mode - minimal setup"""
        print("Initializing headless AI vs AI mode. No chess GUI will be shown.")
        print("Press Ctrl+C in the terminal to stop the game early.")
    
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
            
            # CRITICAL FIX: Reset PGN game with custom starting position
            self.game = chess.pgn.Game()
            self.game.setup(new_board)  # This line fixes everything!
            
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

        except ValueError as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Could not import FEN starting position: {e}")
            return False
        except Exception as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Unexpected problem importing FEN: {e}")
            return False

    # ===================================
    # ========= MOVE HANDLERS ===========
    
    def process_ai_move(self):
        """Process AI move in AI vs AI mode or human vs AI mode"""
        # Allow AI to play both sides in AI vs AI mode
        current_color = "white" if self.board.turn == chess.WHITE else "black"
        self.current_player = self.board.turn
        if not self.ai_vs_ai and self.board.turn != self.ai_color:
            return  # Only check AI color in human vs AI mode
        try:
            ai_move = self.ai_move()
            if ai_move and self.push_move(ai_move):
                self.last_ai_move = ai_move if ai_move else None
            else:
                # Fallback to random legal move
                if self.logging_enabled and self.logger:
                    self.logger.warning(f"Could not process AI move, falling back on random legal move: {ai_move} invalid for {current_color}. | FEN: {self.board.fen()}")
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves)
                    ai_move = fallback
                    self.push_move(fallback)
            if self.show_eval:
                print(f"AI ({current_color}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
            else:
                print(f"AI ({current_color}) plays: {ai_move}")
            if self.logging_enabled and self.logger:
                self.logger.info("AI (%s) played: %s (Eval: %.2f)", current_color, ai_move, self.current_eval)
        except Exception as e:
            print(f"AI move error: {e}")
            if self.logging_enabled and self.logger:
                self.logger.error(f"AI move error: {e}")
            #self.quick_save_pgn("games/game_error_dump.pgn")

    def process_ai_move_threaded(self):
        """Start AI move calculation in a background thread (watch_mode only)."""
        self.current_player = self.board.turn
        if self.ai_busy or self.board.is_game_over() or not self.screen_ready:
            return
        self.ai_busy = True
        self.ai_move_result = None
        self.move_start_time = pygame.time.get_ticks()

        def ai_task():
            try:
                ai_move = self.ai_move()
                self.ai_move_result = ai_move
            except Exception as e:
                print(f"AI move error (thread): {e}")
                if self.logging_enabled and self.logger:
                    self.logger.error(f"AI move error (thread): {e}")
                self.ai_move_result = None
            finally:
                self.ai_busy = False

        self.ai_thread = threading.Thread(target=ai_task, daemon=True)
        self.ai_thread.start()

    def apply_ai_move_result(self):
        """Apply the AI move result if available and not busy, and log timing."""
        if self.ai_move_result is not None and not self.ai_busy:
            move = self.ai_move_result
            if move and self.push_move(move):
                # Only assign last_ai_move if move is a chess.Move
                if isinstance(move, chess.Move):
                    self.last_ai_move = move.to_square
                else:
                    try:
                        self.last_ai_move = chess.Move.from_uci(move).to_square
                    except Exception:
                        self.last_ai_move = None
            self.move_end_time = pygame.time.get_ticks()
            self.move_duration = self.move_end_time - self.move_start_time
            if self.logging_enabled and self.logger:
                self.logger.info("AI move took %d ms", self.move_duration)
            self.ai_move_result = None

    def push_move(self, move):
        """ Test and push a move to the board and game node """
        if not self.board.is_valid():
            return False  # Skip if board is invalid
        try:
            # Ensure move is a chess.Move object
            if isinstance(move, str):
                move = chess.Move.from_uci(move)
            if not self.board.is_legal(move):
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Illegal move blocked: {move}")
                return False

            self.game_node = self.game_node.add_variation(move)
            self.board.push(move)
            self.current_player = self.board.turn
            self.record_evaluation()
            self.quick_save_pgn("games/active_game.pgn")
            if self.watch_mode:
                self.mark_display_dirty()
            return True
        except ValueError:
            #self.quick_save_pgn("games/game_error_dump.pgn")
            return False
        
    # =============================================
    # ============= HUMAN INTERACTION =============

    def handle_mouse_click(self, pos):
        """Click handling with highlighting state management"""
        if self.ai_vs_ai:
            return  # No human interaction in AI vs AI mode

        col = pos[0] // SQ_SIZE
        row = pos[1] // SQ_SIZE

        # Convert to chess coordinates
        if self.flip_board:
            file = 7 - col
            rank = row
        else:
            file = col
            rank = 7 - row

        square = chess.square(file, rank)
        piece = self.board.piece_at(square)

        # CASE 1: No piece currently selected
        if self.selected_square is None:
            # Only select if there's a piece and it belongs to the current human player
            if piece and piece.color == self.board.turn and self.board.turn == self.human_color:
                self.selected_square = square
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Selected piece at {chess.square_name(square)}")
            else:
                if self.logging_enabled and self.logger:
                    self.logger.info(f"No valid piece to select at {chess.square_name(square)}")

        # CASE 2: A piece is already selected
        else:
            # CASE 2A: Clicking on the same square again - DESELECT
            if square == self.selected_square:
                self.selected_square = None
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Deselected piece at {chess.square_name(square)}")
                return

            # CASE 2B: Clicking on another piece of the same color - SWITCH SELECTION
            if piece and hasattr(piece, "color") and piece.color == self.human_color and self.board.turn == self.human_color:
                self.selected_square = square
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Switched selection to piece at {chess.square_name(square)}")
                return

            # CASE 2C: Attempting to make a move
            move = chess.Move(self.selected_square, square)
            
            # Check for pawn promotion
            piece_at_selected = self.board.piece_at(self.selected_square)
            if (piece_at_selected is not None and
                hasattr(piece_at_selected, "piece_type") and
                piece_at_selected.piece_type == chess.PAWN):
                target_rank = chess.square_rank(square)
                if (target_rank == 7 and self.board.turn == chess.WHITE) or \
                   (target_rank == 0 and self.board.turn == chess.BLACK):
                    move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)

            # CASE 2C1: Valid move - execute it
            if move in self.board.legal_moves:
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Human plays: {move}")
                self.game_node = self.game_node.add_variation(move)
                self.board.push(move)
                self.selected_square = None  # Clear selection after successful move
                self.record_evaluation()
                self.quick_save_pgn("games/active_game.pgn")
                self.mark_display_dirty()  # <-- Ensure display updates after human move
                
            # CASE 2C2: Invalid move - deselect and provide feedback
            else:
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Invalid move: {move} - deselecting piece")
                self.selected_square = None  # Clear selection on invalid move

    # ==========================================
    # ============== AI CONFIG =================

    def ai_move(self):
        """AI MOVE SELECTION (supports separate engines for white and black)"""
        ai_config = {}
        chosen_move = None
        # Validate current board state
        if not self.board.is_valid():
            if self.logging_enabled and self.logger:
                self.logger.error(f"Invalid board state detected! | FEN: {self.board.fen()}")
            return None
        if not self.board.legal_moves:
            return None
        # Store the current player before making moves
        current_player = self.current_player

        # Select engine and config based on side to move
        if current_player == chess.WHITE:
            ai_config = self.white_engine._get_ai_config('white')
        else:
            ai_config = self.black_engine._get_ai_config('black')

        # Route to the engine with correct settings
        if self.board.turn == chess.WHITE:
            chosen_move = self.white_engine.search(self.board, current_player, ai_config)
        elif self.board.turn == chess.BLACK:
            chosen_move = self.black_engine.search(self.board, current_player, ai_config)
        else:  # Invalid turn
            self.logger.error(f"Invalid turn detected: {self.board.turn}")
        
        # Store the last AI move
        self.last_ai_move = chosen_move if chosen_move else None
        return chosen_move if chosen_move else None

    # =============================================
    # ============ MAIN GAME LOOP =================

    def run(self):
        running = True
        clock = pygame.time.Clock()
        game_count = self.game_count
        # Initialize game mode
        if self.ai_vs_ai:
            # AI vs AI mode - no human interaction
            if self.logging_enabled and self.logger:
                self.logger.info("Starting AI vs AI mode...")
                print(f"White AI: {self.white_eval_engine} via {self.white_bot_type} vs Black AI: {self.black_eval_engine} via {self.black_bot_type}")
            if self.watch_mode:
                # Visual mode - use timer events
                pygame.time.set_timer(pygame.USEREVENT, 2000)  # 2 second visual updates to make it easier to watch the ai vs ai game
        
        # Configure AI engines per color
        self.white_engine = EvaluationEngine(self.board, chess.WHITE)
        self.black_engine = EvaluationEngine(self.board, chess.BLACK)
        self.engine = EvaluationEngine(self.board, self.board.turn) # Dummy engine for general function calls

        while running and ((self.ai_vs_ai and game_count >= 1)):
            if self.logging_enabled and self.logger:
                self.logger.info(f"Running chess game loop: {self.game_count - game_count} remaining")
                self.engine.logger.info(f"Running chess game loop: {self.game_count - game_count} remaining")
                #self.logger.info(f"AI Busy: {self.ai_busy}, Screen Ready: {self.screen_ready}, Game Over: {self.board.is_game_over()}")
            move_start_time = pygame.time.get_ticks()
            move_end_time = 0
            move_duration = 0

            # Process events (even in headless mode for quit detection)
            for event in pygame.event.get():
                # Set the current player
                self.current_player = self.board.turn
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.ai_vs_ai:
                    # Handle mouse click for human interaction
                    self.handle_mouse_click(pygame.mouse.get_pos())
                elif event.type == pygame.USEREVENT and self.ai_vs_ai and self.watch_mode:
                    # Only start AI move if not busy and screen is ready
                    if not self.ai_busy and self.screen_ready and not self.board.is_game_over() and self.board.is_valid():
                        self.process_ai_move_threaded()

            # In headless AI vs AI mode, call process_ai_move() directly
            if self.ai_vs_ai and not self.watch_mode:
                if not self.board.is_game_over() and self.board.is_valid():
                    self.process_ai_move()

            # In watch mode, apply AI move result if ready (on main thread)
            if self.watch_mode and self.ai_move_result is not None and not self.ai_busy:
                self.apply_ai_move_result()
                move_end_time = pygame.time.get_ticks()
                move_duration = move_end_time - move_start_time
                if self.logging_enabled and self.logger:
                    self.logger.info("AI move took %d ms", move_duration)
                    self.engine.logger.info("AI move took %d ms", move_duration)

            if self.watch_mode:
                # Update the display if in watch mode
                self.update_display()

            # Check game end conditions
            if self.handle_game_end():
                game_count -= 1
                if game_count == 0:
                    running = False
                    pygame.quit()
                    self.record_evaluation()
                    self.save_game_data()
                    if self.ai_vs_ai and self.game_count > 1 and self.game_count != game_count:
                        if self.logging_enabled and self.logger:
                            self.logger.info(f'All {self.game_count} games complete, exiting...')
                    elif self.ai_vs_ai and self.game_count != game_count:
                        if self.logging_enabled and self.logger:
                            self.logger.info('Game complete')
                elif self.ai_vs_ai and self.game_count != game_count:
                    if self.logging_enabled and self.logger:
                        self.logger.info(f'Game {self.game_count - game_count}/{self.game_count} complete...')
                    self.new_game()
            else:
                clock.tick(MAX_FPS)

if __name__ == "__main__":
    game = ChessGame()
    game.run()