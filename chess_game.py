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
from evaluation_engine import EvaluationEngine
from chess_puzzles import ChessPuzzles

# Pygame constants
WIDTH, HEIGHT = 640, 640
DIMENSION = 8
SQ_SIZE = WIDTH // DIMENSION
MAX_FPS = 15
IMAGES = {}

# Resource path config for distro
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class ChessGame:
    def __init__(self, fen_position=None):
        self.fen_position = fen_position

        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)
            
        # Initialize Pygame
        pygame.init()
        self.clock = pygame.time.Clock()
        
        # Initialize game settings
        self.human_color_pref = self.config['game_config']['human_color']
        self.watch_mode = self.config['game_config']['watch_mode']
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Initialize display, if enabled
        if self.watch_mode:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('V7P3R\'s Chess Bot')
            self.load_images()
        else:
            self.screen = None
            print("Running in headless mode - no visual display")
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
        self.game_count = self.config['game_config']['ai_game_count']
        self.ai_vs_ai = self.config['game_config']['ai_vs_ai']
        self.ai_types = self.config['ai_types']
        self.white_bot_type = self.config['white_ai_config']['ai_type']
        self.black_bot_type = self.config['black_ai_config']['ai_type']
        self.white_eval_engine = self.config['white_ai_config']['engine']
        self.black_eval_engine = self.config['black_ai_config']['engine']
        self.white_ai_config = self.config['white_ai_config']
        self.black_ai_config = self.config['black_ai_config']
            
        # Initialize puzzle mode
        self.puzzle_mode = self.config['game_config']['puzzle_mode']
        self.puzzle_engine = ChessPuzzles()
        self.puzzle_engine.puzzle_config = self.config.get('puzzle_config', {})
        self.current_puzzle_data = {}
        self.current_puzzle_fen = None
        self.current_puzzle_solution = None
        self.current_puzzle_step = 0
        self.total_puzzle_steps = 0
        
        # Initialize debug settings
        self.show_eval = self.config['debug']['show_evaluation']
        self.logging_enabled = self.config['debug']['enable_logging']
        self.show_thoughts = self.config['debug']['show_thinking']
        self.logger = None
        if self.logging_enabled:
            self.setup_logger()
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
        self.game_node = self.game
        self.selected_square = None
        self.last_ai_move = None
        self.current_eval = None
        self.ai_color = None # Will be set in run()
        self.human_color = None
        self.current_player = self.board.turn
        self.last_ai_move = None # Track AI's last move
        self.last_move = None # Track last move made by any player
        self.current_puzzle_data = None

        # Reset AI engines if they exist
        if hasattr(self, 'white_engine') and self.white_engine:
            self.white_engine.reset(self.board)
        if hasattr(self, 'black_engine') and self.black_engine:
            self.black_engine.reset(self.board)

        # Set up a new puzzle if puzzles enabled
        if self.puzzle_mode:
            # Get a random puzzle from the puzzle engine and check configuration
            if not hasattr(self, 'puzzle_engine') or not self.puzzle_engine:
                self.puzzle_engine = ChessPuzzles()
                self.puzzle_engine.puzzle_config = self.config.get('puzzle_config', {})
            self.current_puzzle_data = self.puzzle_engine.get_random_puzzle()
            
            # Reset to step 1 of the current puzzle
            if not self.current_puzzle_data:
                print("No puzzles available, starting a new game without puzzles.")
                self.puzzle_mode = False
                self.current_puzzle_data = None
                self.ai_vs_ai = True  # Fallback to AI vs AI if no puzzles
                return self.new_game()
            else:
                self.current_puzzle_step = 1
            
            # Convert the puzzle text into an array
            if hasattr(self.current_puzzle_data, 'fen'):
                # Load the puzzle data
                self.current_puzzle_fen = self.current_puzzle_data['fen']
            if hasattr(self.current_puzzle_data, 'solution'):
                if isinstance(self.current_puzzle_data['solution'], str):
                    self.current_puzzle_solution = self.current_puzzle_data['solution'].split()
                    self.total_puzzle_steps = len(self.current_puzzle_solution)
            self.import_fen(self.current_puzzle_fen)
            print(f"Loaded puzzle: {self.current_puzzle_fen} | Required moves: {self.total_puzzle_steps}")
        
        # Reset PGN headers
        self.set_headers()
        
        # Reset move history
        self.move_history = []
        print("\nStarting new game...")
    
    def setup_logger(self):
        """Setup logger for debugging and evaluation"""
        if not os.path.exists('logging'):
            os.makedirs('logging', exist_ok=True)
            print("Created logging directory")
        
        # Create logger 
        self.logger = logging.getLogger('chess_ai')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        if self.show_thoughts:
            file_handler = logging.handlers.RotatingFileHandler(
                'logging/chess_game.log', 
                maxBytes=1000*1024*1024,  # 1GB max
                backupCount=3
            )
            
            formatter = logging.Formatter(
                '%(asctime)s | %(funcName)-15s | %(message)s',
                datefmt='%H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            self.logger.propagate = False
            
    def set_headers(self):
        # Set initial PGN headers
        if self.ai_vs_ai or self.puzzle_mode:
            if self.puzzle_mode:
                self.game.headers["Event"] = "AI Puzzle Mode"
            else:
                self.game.headers["Event"] = "AI vs. AI Game"
            self.game.headers["White"] = f"AI: {self.white_eval_engine} via {self.white_bot_type}"
            self.game.headers["Black"] = f"AI: {self.black_eval_engine} via {self.black_bot_type}"
        else:
            self.game.headers["Event"] = "Human vs. AI Game"
            self.game.headers["White"] = f"AI: {self.white_eval_engine} via {self.white_bot_type}" if self.ai_color == chess.WHITE else "Human"
            self.game.headers["Black"] = "Human" if self.ai_color == chess.WHITE else f"AI: {self.black_eval_engine} via {self.black_bot_type}"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = "Local Computer"
        self.game.headers["Round"] = "#"
        
    def set_colors(self):
        if self.ai_vs_ai:
            self.flip_board = False # White on bottom for AI vs AI
            self.human_color = None
            self.ai_color = None
        elif self.puzzle_mode:
            # Set up AI puzzle solving
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
                print(f"Warning: Could not load image for {piece}")

    def draw_board(self):
        if not self.watch_mode:
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
        if not self.watch_mode:
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
        if not self.watch_mode:
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
        history_x = self.width - 200
        history_y = 50
        
        history_surface = self.font.render("Move History", True, self.BLACK)
        self.screen.blit(history_surface, (history_x, history_y))
        
        for i, move in enumerate(self.move_history[-10:]):  # Show last 10 moves
            move_text = f"{i+1}. {move}"
            move_surface = self.small_font.render(move_text, True, self.BLACK)
            self.screen.blit(move_surface, (history_x, history_y + 40 + i*20))
            
    def draw_eval(self):
        if not self.watch_mode:
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
            elif self.puzzle_mode:
                turn_text = f"{'White' if self.current_player == chess.BLACK else 'Black'} to move"
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
        if not self.watch_mode:
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
        if not self.watch_mode:
            return  # Skip drawing in headless mode
        if self.selected_square:
            screen_x, screen_y = self.chess_to_screen(self.selected_square)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('blue'))
            self.screen.blit(s, (screen_x, screen_y))

    def highlight_last_move(self):
        if not self.watch_mode:
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
            self.save_pgn()
            print(f"\nGame over: {result}")
            return True
        
        # Check for threefold repetition and fifty-move rule (requires claim_draw=True)
        if self.board.is_game_over(claim_draw=True):
            result = self.board.result(claim_draw=True)
            
            # Determine the specific draw condition for better feedback
            if self.board.can_claim_threefold_repetition():
                print("\nGame drawn by threefold repetition!")
            elif self.board.can_claim_fifty_moves():
                print("\nGame drawn by fifty-move rule!")
            else:
                print("\nGame drawn!")
                
            self.game.headers["Result"] = result
            self.save_pgn()
            print(f"Game over: {result}")
            return True
        
        # Additional check for automatic fivefold repetition (since July 2014 rules)
        if self.board.is_fivefold_repetition():
            result = "1/2-1/2"
            print("\nGame automatically drawn by fivefold repetition!")
            self.game.headers["Result"] = result
            self.save_pgn()
            print(f"Game over: {result}")
            return True
        
        # Additional check for automatic 75-move rule (since July 2014 rules)
        if self.board.is_seventyfive_moves():
            result = "1/2-1/2"
            print("\nGame automatically drawn by seventy-five move rule!")
            self.game.headers["Result"] = result
            self.save_pgn()
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
              
    def save_pgn(self):
        # Create games directory if it doesn't exist
        games_dir = "games"
        
        if not os.path.exists(games_dir):
            os.makedirs(games_dir, exist_ok=True)
            print(f"Created directory: {games_dir}")
        
        # Generate filename with timestamp if not provided
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"games/eval_game_{timestamp}.pgn"
        
        try:
            with open(filename, "w") as f:
                exporter = chess.pgn.FileExporter(f)
                self.game.accept(exporter)
            print(f"Game saved to {filename}")
        except IOError as e:
            print(f"Error saving game: {e}")

    def quick_save_pgn(self, filename):
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
    
    def headless_mode(self):
        """Initialize pygame for headless mode - minimal setup"""
        print("Initializing headless AI vs AI mode...")
        print("No visual display will be shown.")
        print("Game progress will be shown in terminal.")
        print("Press Ctrl+C to stop the game early.")     
    
    def import_fen(self, fen_string):
        """Import a position from FEN notation"""
        try:
            # Create a new board from the FEN
            new_board = chess.Board(fen_string)
            
            # Validate the board is legal
            if not new_board.is_valid():
                print(f"Error: Invalid FEN position: {fen_string}")
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
            if self.puzzle_mode:
                self.game.headers["Event"] = "Puzzle Solving"
            else:
                self.game.headers["Event"] = "Custom Position Game"
            self.game.headers["SetUp"] = "1"
            self.game.headers["FEN"] = fen_string
            
            print(f"Successfully imported FEN: {fen_string}")
            return True
            
        except ValueError as e:
            print(f"Error: Could not import FEN starting position: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error importing FEN: {e}")
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
                print(f"AI falling back on random legal move, {ai_move} invalid!")
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves)
                    ai_move = fallback
                    self.push_move(fallback)
            if self.show_eval:
                print(f"AI ({current_color}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
            else:
                print(f"AI ({current_color}) plays: {ai_move}")
            if self.show_thoughts and self.logger:
                self.logger.info(f"AI ({current_color}) played: {ai_move} (Eval: {self.current_eval:.2f})")
        except Exception as e:
            print(f"AI move error: {e}")
            self.quick_save_pgn("logging/error_dump.pgn")

    def process_puzzle_move(self):
        """Process AI puzzle guess in puzzle mode"""
        self.puzzle_step = self.last_ai_move
        current_color = "white" if self.board.turn == chess.WHITE else "black"
        self.current_player = self.board.turn
        if not self.puzzle_mode:
            return
        if  self.current_player != self.ai_color:
            # Check the AI move in the move sequence
            self.puzzle_engine.puzzles

        try:
            ai_move = self.ai_move()
            if ai_move and self.push_move(ai_move):
                self.last_ai_move = ai_move if ai_move else None
            else:
                # Fallback to random legal move
                print(f"AI falling back on random legal move, {ai_move} invalid!")
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves)
                    ai_move = fallback
                    self.push_move(fallback)
            if self.show_eval:
                print(f"AI ({current_color}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
            else:
                print(f"AI ({current_color}) plays: {ai_move}")
            if self.show_thoughts and self.logger:
                self.logger.info(f"AI ({current_color}) played: {ai_move} (Eval: {self.current_eval:.2f})")
            if ai_move in self.current_puzzle_solution: 
                # If the AI move matches the current puzzle solution, increment step
                if self.ai_move not in self.current_puzzle_solution:
                    print(f"Puzzle step {self.current_puzzle_step + 1} incorrect: {ai_move}")
                    self.logger.error(f"Puzzle step {self.current_puzzle_step + 1} incorrect: {ai_move} | FEN: {self.board.fen()}")
                if self.ai_move in self.current_puzzle_solution and self.current_puzzle_step < self.total_puzzle_steps:
                    self.logger.info(f"Puzzle step {self.current_puzzle_step + 1} correct: {ai_move} | FEN: {self.board.fen()}")
                    self.current_puzzle_step += 1
                    # Push the next puzzle move to the game (for opposing player)
                    if self.current_puzzle_step < self.total_puzzle_steps:
                        next_move = self.current_puzzle_solution[self.current_puzzle_step - 1]
                        next_move = chess.Move.from_uci(next_move)
                        if self.push_move(next_move):
                            print(f"Puzzle step {self.current_puzzle_step + 1} move pushed: {next_move}")
                        else:
                            print(f"Failed to push puzzle step {self.current_puzzle_step + 1} move: {next_move}")
                
                if self.current_puzzle_step >= self.total_puzzle_steps:
                    if self.show_thoughts and self.logging_enabled:
                        self.logger.info(f"Puzzle solved! | Solution: {self.current_puzzle_solution} | FEN: {self.board.fen()}")
                    self.puzzle_engine.mark_puzzle_solved(self.current_puzzle_fen)
                    self.quick_save_pgn("logging/puzzle_solved.pgn")
            
        except Exception as e:
            print(f"AI move error: {e}")
            self.quick_save_pgn("logging/puzzle_error_dump.pgn")
    

    
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
                self.last_ai_move = move.to_square if isinstance(move, chess.Move) else chess.Move.from_uci(move).to_square
            self.move_end_time = pygame.time.get_ticks()
            self.move_duration = self.move_end_time - self.move_start_time
            if self.show_thoughts and self.logger:
                self.logger.info(f"AI move took {self.move_duration} ms")
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
                print(f"Illegal move blocked: {move}")
                return False

            self.game_node = self.game_node.add_variation(move)
            self.board.push(move)
            self.current_player = self.board.turn
            self.record_evaluation()
            self.quick_save_pgn("logging/active_game.pgn")
            if self.watch_mode:
                self.mark_display_dirty()
            return True
        except ValueError:
            self.quick_save_pgn("logging/game_error_dump.pgn")
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
                print(f"Selected piece at {chess.square_name(square)}")
            else:
                print(f"No valid piece to select at {chess.square_name(square)}")
                
        # CASE 2: A piece is already selected
        else:
            # CASE 2A: Clicking on the same square again - DESELECT
            if square == self.selected_square:
                self.selected_square = None
                print(f"Deselected piece at {chess.square_name(square)}")
                return
                
            # CASE 2B: Clicking on another piece of the same color - SWITCH SELECTION
            if piece and piece.color == self.human_color and self.board.turn == self.human_color:
                self.selected_square = square
                print(f"Switched selection to piece at {chess.square_name(square)}")
                return
                
            # CASE 2C: Attempting to make a move
            move = chess.Move(self.selected_square, square)
            
            # Check for pawn promotion
            if (self.board.piece_at(self.selected_square) and
                self.board.piece_at(self.selected_square).piece_type == chess.PAWN):
                target_rank = chess.square_rank(square)
                if (target_rank == 7 and self.board.turn == chess.WHITE) or \
                   (target_rank == 0 and self.board.turn == chess.BLACK):
                    move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)

            # CASE 2C1: Valid move - execute it
            if move in self.board.legal_moves:
                print(f"Human plays: {move}")
                self.game_node = self.game_node.add_variation(move)
                self.board.push(move)
                self.selected_square = None  # Clear selection after successful move
                self.record_evaluation()
                self.quick_save_pgn("logging/active_game.pgn")
                self.mark_display_dirty()  # <-- Ensure display updates after human move
                
            # CASE 2C2: Invalid move - deselect and provide feedback
            else:
                print(f"Invalid move: {move} - deselecting piece")
                self.selected_square = None  # Clear selection on invalid move

    # ==========================================
    # ============== AI CONFIG =================

    def ai_move(self):
        """AI MOVE SELECTION (supports separate engines for white and black)"""
        ai_config = {}
        chosen_move = None
        # Validate current board state
        if not self.board.is_valid():
            print(f"ERROR: Invalid board state detected! | FEN: {self.board.fen()}")
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
        if self.puzzle_mode:
            # Puzzle mode - load puzzles and start
            print("Starting puzzle mode...")
            self.puzzle_engine.load_puzzles()
            
        elif self.ai_vs_ai:
            # AI vs AI mode - no human interaction
            print("Starting AI vs AI mode...")
            if self.watch_mode:
                # Visual mode - use timer events
                pygame.time.set_timer(pygame.USEREVENT, 2000)  # 2 second visual updates to make it easier to watch the ai vs ai game
        
        # Configure AI engines per color
        self.white_engine = EvaluationEngine(self.board, chess.WHITE)
        self.black_engine = EvaluationEngine(self.board, chess.BLACK)

        while running and game_count >= 1:
            # print(f"Running game loop: {game_count}")
            # print(f"AI Busy: {self.ai_busy}, Screen Ready: {self.screen_ready}, Game Over: {self.board.is_game_over()}")
            move_start_time = pygame.time.get_ticks()
            move_end_time = 0
            move_duration = 0

            # Process events (even in headless mode for quit detection)
            for event in pygame.event.get():
                # Set the current player
                self.current_player = self.board.turn
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.ai_vs_ai and not self.puzzle_mode:
                    # Handle mouse click for human interaction
                    self.handle_mouse_click(pygame.mouse.get_pos())
                elif event.type == pygame.USEREVENT and self.ai_vs_ai and self.watch_mode:
                    # Only start AI move if not busy and screen is ready
                    if not self.ai_busy and self.screen_ready and not self.board.is_game_over() and self.board.is_valid():
                        self.process_ai_move_threaded()
                elif event.type == pygame.USEREVENT and self.puzzle_mode and self.watch_mode:
                    # In puzzle mode, process AI move if not busy and screen is ready
                    if not self.ai_busy and self.screen_ready and not self.board.is_game_over() and self.board.is_valid():
                        self.process_puzzle_move()

            # In headless AI vs AI mode, call process_ai_move() directly
            if self.ai_vs_ai and not self.watch_mode:
                if not self.board.is_game_over() and self.board.is_valid():
                    self.process_ai_move()
            if self.puzzle_mode and not self.watch_mode:
                if not self.board.is_game_over() and self.board.is_valid():
                    self.process_puzzle_move()
                    self.process_puzzle_result()

            # In watch mode, apply AI move result if ready (on main thread)
            if self.watch_mode and self.ai_move_result is not None and not self.ai_busy:
                self.apply_ai_move_result()
                move_end_time = pygame.time.get_ticks()
                move_duration = move_end_time - move_start_time
                if self.show_thoughts and self.logger:
                    self.logger.info(f"AI move took {move_duration} ms")

            if self.watch_mode:
                # Update the display if in watch mode
                self.update_display()

            # Check game end conditions
            if self.handle_game_end():
                game_count -= 1
                if game_count == 0:
                    running = False
                    pygame.quit()
                    if self.game_count > 1:
                        print(f'All {self.game_count} games complete, exiting...')
                    else:
                        print('Game complete, exiting...')
                else:
                    print(f'Game {self.game_count - game_count}/{self.game_count} complete...')
                    self.new_game()
            else:
                clock.tick(MAX_FPS)

if __name__ == "__main__":
    game = ChessGame()
    game.run()