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
    def __init__(self):
        
        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)
            
        # Initialize Pygame
        pygame.init()
        
        # Set up game config
        self.ai_vs_ai = self.config['game']['ai_vs_ai']
        self.human_color_pref = self.config['game']['human_color']
        self.watch_mode = self.config['game']['ai_watch_mode']
        self.show_eval = self.config['debug']['print_evaluation']
        self.white_bot_type = self.config['white_ai_config']['white_ai']
        self.black_bot_type = self.config['black_ai_config']['black_ai']
        self.white_engine = self.config['white_ai_config']['white_engine']
        self.black_engine = self.config['black_ai_config']['black_engine']
        
        
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Only create screen and load images in visual mode
        if not (self.ai_vs_ai and not self.watch_mode):
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
            self.game.headers["Event"] = "AIv.AI Pure Evaluation Engine"
        else:
            self.game.headers["Event"] = "Humanv.AI Pure Evaluation Engine"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = "Local Computer"
        self.game.headers["Round"] = "#"

        # Turn management
        self.current_player = None
        self.last_ai_move = None # Track AI's last move

        # Set up evaluation
        self.evaluator = EvaluationEngine(self.board)
        self.current_eval = None

        # Set colors
        self._set_colors()

    def _set_colors(self):
        if self.ai_vs_ai:
            self.flip_board = False # White on bottom for AI vs AI
            self.human_color = None
            self.ai_color = None
        else:
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
        if self.ai_vs_ai and not self.watch_mode:
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
        if self.ai_vs_ai and not self.watch_mode:
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
        if self.ai_vs_ai and not self.watch_mode:
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
        if self.ai_vs_ai and not self.watch_mode:
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
            depth_text = self.font.render(f"Depth: {self.config['ai']['search_depth']}", True, (0, 0, 0))
            self.screen.blit(depth_text, (WIDTH-150, 35))
            
            # Show current turn in AI vs AI mode
            if self.ai_vs_ai:
                turn_text = f"Turn: {'White' if self.board.turn == chess.WHITE else 'Black'}"
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
        if self.ai_vs_ai and not self.watch_mode:
            return  # Skip drawing in headless mode
        """Optimized display update"""
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

    def highlight_selected_square(self):
        if self.ai_vs_ai and not self.watch_mode:
            return  # Skip drawing in headless mode
        if self.selected_square:
            screen_x, screen_y = self.chess_to_screen(self.selected_square)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('blue'))
            self.screen.blit(s, (screen_x, screen_y))

    def highlight_last_move(self):
        if self.ai_vs_ai and not self.watch_mode:
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
        score = self.evaluator.evaluate_position()
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
            self.board = chess.Board(fen_string)
            if self.engine:
                self.engine.board = self.board.copy()
            self.selected_square = None
            self.legal_moves = []
            self.game_over = self.board.is_game_over()
            return True
        except ValueError:
            print("Error: Could not import FEN starting position!")
            return False
            
    def export_fen(self):
        """Export current position as FEN string"""
        return self.board.fen()

    # =============================================
    # ============ MAIN GAME LOOP =================

    def run(self):
        running = True
        # Only create clock if we need visual display
        if not (self.ai_vs_ai and not self.watch_mode):
            clock = pygame.time.Clock()
        # Initialize AI move timer for AI vs AI mode
        if self.ai_vs_ai:
            starting_position = input("Custom FEN starting position: [Press Enter to skip]")
            if starting_position:
                self.import_fen(starting_position)
            if not self.watch_mode:
                # Headless mode - use time-based control
                last_ai_move_time = pygame.time.get_ticks()
                ai_move_interval = 1000  # 1 second between moves
            else:
                # Visual mode - use timer events
                pygame.time.set_timer(pygame.USEREVENT, 2000)  # 2 second intervals
        while running:
            current_time = pygame.time.get_ticks()
            # Process events (even in headless mode for quit detection)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.ai_vs_ai:
                    self.handle_mouse_click(pygame.mouse.get_pos())
                elif self.ai_vs_ai and self.watch_mode and event.type == pygame.USEREVENT:
                    if not self.board.is_game_over():
                        self.process_ai_move()
            # Handle AI vs AI moves in headless mode
            if self.ai_vs_ai and not self.watch_mode:
                if not self.board.is_game_over():
                    if current_time - last_ai_move_time >= ai_move_interval:
                        self.process_ai_move()
                        last_ai_move_time = current_time
            # Handle AI moves in human vs AI mode
            if not self.ai_vs_ai and self.board.turn == self.ai_color and not self.board.is_game_over():
                self.process_ai_move()
            # Only update display if we have a screen
            if not (self.ai_vs_ai and not self.watch_mode):
                self.update_display()
                clock.tick(MAX_FPS)
            # Check game end conditions
            if self.handle_game_end():
                running = False
        # Only quit pygame if we initialized it with a screen
        if not (self.ai_vs_ai and not self.watch_mode):
            pygame.quit()
        else:
            print("\nHeadless AI vs AI game completed!")

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

    def push_move(self, move_uci):
        try:
            move = chess.Move.from_uci(move_uci)
            if not self.board.is_legal(move): # Use is_legal instead of checking list
                print(f"Illegal move blocked: {move_uci}")
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
        # Validate current board state
        if not self.board.is_valid():
            print("ERROR: Invalid board state detected!")
            self.board = chess.Board(self.board.fen())
            return None

        if not self.board.legal_moves: return None

        # Store the current player before making moves
        current_player = self.board.turn

        # Valid bot types:
        #  - simple_eval
        #  - deepsearch
        #  - lookahead
        #  - random
        # TODO - v7p3r_chess_model (not integrated, need to integrate)
        # TODO - openings_model (not integrated, need to integrate)
        
        if current_player == chess.WHITE:
            # Select search type based on white bot selection
            # create engine for white
            ai_type = self.config['white_ai_config']['white_ai']
            ai_config = self._get_white_ai_config()
        else:
            # create engine for black
            ai_type = self.config['black_ai_config']['black_ai']
            ai_config = self._get_black_ai_config()
        
        return self._execute_ai_brain(ai_type, ai_config, current_player)
    
    def _get_white_ai_config(self):
        """Extract White's AI configuration"""
        return {
            'ai_type': self.config['white_ai_config']['white_ai'],
            'depth': self.config['white_ai_config']['white_depth'],
            'move_ordering': self.config['white_ai_config']['white_move_ordering'],
            'quiescence': self.config['white_ai_config']['white_quiescence'],
            'time_limit': self.config['white_ai_config']['white_time_limit'],
            'pst_enabled': self.config['white_ai_config']['white_pst'],
            'pst_weight': self.config['white_ai_config']['white_pst_weight'],
            'engine': self.config['white_ai_config']['white_engine'],
            'ruleset': self.config['white_ai_config']['white_ruleset']
        }

    def _get_black_ai_config(self):
        """Extract Black's AI configuration"""
        return {
            'ai_type': self.config['black_ai_config']['black_ai'],
            'depth': self.config['black_ai_config']['black_depth'],
            'move_ordering': self.config['black_ai_config']['black_move_ordering'],
            'quiescence': self.config['black_ai_config']['black_quiescence'],
            'time_limit': self.config['black_ai_config']['black_time_limit'],
            'pst_enabled': self.config['black_ai_config']['black_pst'],
            'pst_weight': self.config['black_ai_config']['black_pst_weight'],
            'engine': self.config['black_ai_config']['black_engine'],
            'ruleset': self.config['black_ai_config']['black_ruleset']
        }

    def _execute_ai_brain(self, ai_type, ai_config, player):
        """Execute the appropriate AI brain with its specific configuration"""
        
        # Configure the evaluator with side-specific settings
        self.evaluator.configure_for_side(ai_config)
        
        # Route to the appropriate evaluation method
        if ai_type == 'deepsearch':
            return self.evaluator._deepsearch_move(player)
        elif ai_type == 'lookahead':
            return self.evaluator._lookahead_move(player)
        elif ai_type == 'simple_eval':
            return self.evaluator._simple_eval_move(player)
        elif ai_type == 'random':
            import random
            legal_moves = list(self.board.legal_moves)
            return random.choice(legal_moves).uci() if legal_moves else None
        else:
            print(f"Warning: Unknown AI type '{ai_type}', using simple_eval")
            return self.evaluator._simple_eval_move(player)
        
if __name__ == "__main__":
    game = ChessGame()
    game.run()