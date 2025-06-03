# chess_game.py

import os
import sys
import pygame
import chess
import chess.pgn
import random
import yaml
import datetime
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
        
        # Set up game config
        self.puzzle_mode = self.config['game_config']['puzzle_mode']
        self.ai_vs_ai = self.config['game_config']['ai_vs_ai']
        self.human_color_pref = self.config['game_config']['human_color']
        self.watch_mode = self.config['game_config']['ai_watch_mode']
        self.show_eval = self.config['debug']['print_evaluation']
        self.white_bot_type = self.config['white_ai_config']['ai_type']
        self.black_bot_type = self.config['black_ai_config']['ai_type']
        self.white_engine = self.config['white_ai_config']['engine']
        self.black_engine = self.config['black_ai_config']['engine']
        self.ai_types = self.config['ai_types']
        self.white_ai_config = self.config['white_ai_config']
        self.black_ai_config = self.config['black_ai_config']
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Only create screen and load images in visual mode
        if self.watch_mode:
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('v7p3r Chess Bot - Pure Evaluation Engine')
            self.load_images()
        else:
            self.screen = None
            print("Running in headless mode - no visual display")
            self.headless_mode()
        
        # Initialize chess components
        self.board = chess.Board()
        self.selected_square = None
        self.player_clicks = []
        self.load_images()
        
        # Hard coded piece values for evaluation fallback
        self.piece_values = {
            chess.KING: 0,
            chess.QUEEN: 9,
            chess.ROOK: 5,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3,
            chess.PAWN: 1
        }

        # Game recording
        self.game = chess.pgn.Game()
        self.ai_color = None # Will be set in run()
        self.human_color = None
        self.game_node = self.game
        
        # Initialize PGN headers
        if self.ai_vs_ai:
            self.game.headers["Event"] = "AI v. AI Pure Evaluation Engine"
        elif self.puzzle_mode:
            self.game.headers["Event"] = "Puzzle Mode"
        else:
            self.game.headers["Event"] = "Human v. AI Pure Evaluation Engine"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = "Local Computer"
        self.game.headers["Round"] = "#"

        # Turn management
        self.current_player = None
        self.last_ai_move = None # Track AI's last move

        # Set up evaluation
        self.evaluator = EvaluationEngine(self.board, self.board.turn)
        self.current_eval = None

        # Set up puzzle mode if enabled
        if self.puzzle_mode:
            self.puzzles = ChessPuzzles()
            self.puzzles.puzzle_config = self.config.get('puzzle_config', {})
        
        # Set colors
        self._set_colors()

    def _set_colors(self):
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

        # Set PGN headers
        if self.ai_vs_ai:
            self.game.headers["White"] = f"AI: {self.white_engine} via {self.white_bot_type}"
            self.game.headers["Black"] = f"AI: {self.black_engine} via {self.black_bot_type}"
        elif self.puzzle_mode:
            self.game.headers["White"] = "Puzzle Solver"
            self.game.headers["Black"] = "Puzzle Solver"
        else:
            self.game.headers["White"] = f"AI: {self.white_engine} via {self.white_bot_type}" if self.ai_color == chess.WHITE else "Human"
            self.game.headers["Black"] = "Human" if self.ai_color == chess.WHITE else f"AI: {self.black_engine} via {self.black_bot_type}"

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
            depth_text = self.font.render(f"Depth: {self.evaluator.depth}", True, (0, 0, 0))
            self.screen.blit(depth_text, (WIDTH-150, 35))
            
            # Show current turn in AI vs AI mode
            if self.ai_vs_ai:
                turn_text = f"Turn: {'White' if self.board.turn == chess.WHITE else 'Black'}"
                turn_surface = self.font.render(turn_text, True, (0, 0, 0))
                self.screen.blit(turn_surface, (WIDTH-150, 60))
            elif self.puzzle_mode:
                turn_text = f"{'White' if self.board.turn == chess.WHITE else 'Black'} to move"
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
        score = self.evaluator.evaluate_position(self.board)
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
            
            # Update evaluator if it exists
            if self.evaluator:
                self.evaluator.board = self.board
            
            # Reset game state
            self.selected_square = None
            
            # Update PGN headers for custom position
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
        # Allow AI to play both sides in AI vs AI mode
        current_color = "White" if self.board.turn == chess.WHITE else "Black"
        if not self.ai_vs_ai and self.board.turn != self.ai_color:
            return  # Only check AI color in human vs AI mode
        try:
            ai_move = self.ai_move()
            if ai_move and self.push_move(ai_move):
                move_obj = chess.Move.from_uci(ai_move)
                self.last_ai_move = move_obj.to_square
            else:
                # Fallback to random legal move
                print(f"AI falling back on random legal move, {ai_move} invalid!")
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves)
                    ai_move = fallback
                    self.push_move(fallback.uci())            
            if self.show_eval:
                print(f"AI ({current_color}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
            else:
                print(f"AI ({current_color}) plays: {ai_move}")
        except Exception as e:
            print(f"AI move error: {e}")
            self.quick_save_pgn("logging/error_dump.pgn")

    def push_move(self, move):
        """ Test and push a move to the board and game node """
        if not self.board.is_valid():
            return False  # Skip if board is invalid
        try:
            # ensure move is in UCI format
            if isinstance(move, chess.Move):
                move = move.uci()
            
            if not self.board.is_legal(move):
                print(f"Illegal move blocked: {move}")
                return False

            self.game_node = self.game_node.add_variation(move)
            self.board.push(move)
            self.current_player = self.board.turn
            self.record_evaluation()
            self.quick_save_pgn("logging/active_game.pgn")
            return True
        except ValueError:
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
                
            # CASE 2C2: Invalid move - deselect and provide feedback
            else:
                print(f"Invalid move: {move} - deselecting piece")
                self.selected_square = None  # Clear selection on invalid move

    # =============================================
    # ================= AI PLAY ===================

    def ai_move(self):
        """AI MOVE SELECTION"""
        ai_config = {}
        chosen_move = None
        # Validate current board state
        if not self.board.is_valid():
            print(f"ERROR: Invalid board state detected! | FEN: {self.board.fen()}")
            return None
        if not self.board.legal_moves: return None
        # Store the current player before making moves
        self.current_player = self.board.turn
        current_player = self.current_player
        if current_player == chess.WHITE:
            # create engine for white
            ai_type = self.config['white_ai_config']['ai_type']
            ai_config = self.evaluator._get_ai_config('white')
        else:
            # create engine for black
            ai_type = self.config['black_ai_config']['ai_type']
            ai_config = self.evaluator._get_ai_config('black')
        
        # Route to the evaluator with correct settings
        if ai_type in self.ai_types:
            chosen_move = self.evaluator._search_for_move(self.board, current_player, ai_type, ai_config)
        else: # move is random
            legal_moves = list(self.board.legal_moves)
            chosen_move = random.choice(legal_moves) if legal_moves else None
        return chosen_move if chosen_move else None

    
    # =============================================
    # ============ MAIN GAME LOOP =================

    def run(self):
        running = True
        # Only create clock if we need visual display
        if self.watch_mode:
            clock = pygame.time.Clock()
        # Initialize game mode
        if self.puzzle_mode:
            # Load puzzle from FEN if provided
            if self.fen_position:
                try:
                    if self.fen_position and self.fen_position in self.puzzles.puzzle_config.get('puzzles', []):
                        self.puzzles.get_puzzle(self.fen_position)
                    else:
                        print(f"Invalid puzzle index: {self.fen_position}. Starting with default puzzle.")
                    self.import_fen(self.fen_position)
                except ValueError:
                    print("Invalid FEN position provided, starting with default board.")
        elif self.ai_vs_ai:
            starting_position = input("Custom FEN starting position: [Press Enter to skip]")
            if starting_position:
                self.import_fen(starting_position)
            if not self.watch_mode:
                # Headless mode - use time-based control
                pass  # No need for last_ai_move_time in headless mode
            else:
                # Visual mode - use timer events
                pygame.time.set_timer(pygame.USEREVENT, 2000)  # 2 second intervals
        
        last_ai_move_time = 0
        while running:
            move_start_time = pygame.time.get_ticks()

            # Process events (even in headless mode for quit detection)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.ai_vs_ai and not self.puzzle_mode:
                    # Handle mouse click for human interaction
                    self.handle_mouse_click(pygame.mouse.get_pos())
                elif event.type == pygame.USEREVENT and (self.ai_vs_ai or self.puzzle_mode) and self.watch_mode:
                    # Handle AI move forcing
                    if not self.board.is_game_over() and self.board.is_valid():
                        self.process_ai_move()
                        move_end_time = pygame.time.get_ticks()
                        move_duration = move_end_time - move_start_time
            # Check game end conditions
            if self.handle_game_end():
                running = False
            else:
                clock.tick(MAX_FPS)
            
        pygame.quit()
        print('Game complete, exiting...')

if __name__ == "__main__":
    game = ChessGame()
    game.run()