# chess_game.py

import os
import sys
import pygame
import chess
import chess.pgn
from evaluation_engine import ImprovedEvaluationEngine as EvaluationEngine
import random
import yaml
import datetime

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
        
        # Only create screen and load images in visual mode
        if not (self.ai_vs_ai and not self.watch_mode):
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption('v7p3r Chess Bot - Pure Evaluation Engine')
            self.load_images()
        else:
            self.screen = None
            print("Running in headless mode - no visual display")
            self._init_headless_mode()

        self.clock = pygame.time.Clock()

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
            self.game.headers["Event"] = "AI vs. AI Testing (Pure Evaluation)"
        else:
            self.game.headers["Event"] = "Human vs. AI Testing (Pure Evaluation)"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = "Local Computer"
        self.game.headers["Round"] = "#"

        # Turn management
        self.last_ai_move = None # Track AI's last move

        # Pure evaluation engine setup
        self.evaluator = EvaluationEngine(self.board, depth=self.config['ai']['search_depth'])
        self.current_eval = None
        self.font = pygame.font.SysFont('Arial', 24)

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
            self.game.headers["White"] = "v7p3r_eval_bot"
            self.game.headers["Black"] = "v7p3r_eval_bot"
        else:
            self.game.headers["White"] = "v7p3r_eval_bot" if self.ai_color == chess.WHITE else "Human"
            self.game.headers["Black"] = "Human" if self.ai_color == chess.WHITE else "v7p3r_eval_bot"

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
        colors = [pygame.Color("#d8d9d8"), pygame.Color("#a8a9a8")]
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
                    dest_screen_x, dest_screen_y = self._chess_to_screen(move.to_square)

                    # Draw hint circle
                    center = (dest_screen_x + SQ_SIZE//2, dest_screen_y + SQ_SIZE//2)
                    pygame.draw.circle(
                        self.screen,
                        pygame.Color('green'),
                        center,
                        SQ_SIZE//5
                    )

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

    def _chess_to_screen(self, square):
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
            screen_x, screen_y = self._chess_to_screen(self.selected_square)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('blue'))
            self.screen.blit(s, (screen_x, screen_y))

    def highlight_last_move(self):
        if self.ai_vs_ai and not self.watch_mode:
            return  # Skip drawing in headless mode
        """Highlight AI's last move on the board"""
        if self.last_ai_move:
            screen_x, screen_y = self._chess_to_screen(self.last_ai_move)
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


    def _record_evaluation(self, score):
        """Record evaluation score in PGN comments"""
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
        if filename is None:
            # Create timestamp in format: YYYYMMDD_HHMMSS
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"games/eval_game_{timestamp}.pgn"
        
        try:
            with open(filename, "w") as f:
                exporter = chess.pgn.FileExporter(f)
                self.game.accept(exporter)
            print(f"Game saved to {filename}")
        except IOError as e:
            print(f"Error saving game: {e}")

    def quick_save_pgn(self, filename="active_game.pgn"):
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
    
    def _init_headless_mode(self):
        """Initialize pygame for headless mode - minimal setup"""
        print("Initializing headless AI vs AI mode...")
        print("No visual display will be shown.")
        print("Game progress will be shown in terminal.")
        print("Press Ctrl+C to stop the game early.")

    # =============================================
    # ============ MAIN GAME LOOP =================

    def run(self):
        running = True
        
        # Only create clock if we need visual display
        if not (self.ai_vs_ai and not self.watch_mode):
            clock = pygame.time.Clock()
        
        # Initialize AI move timer for AI vs AI mode
        if self.ai_vs_ai:
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
                
            # CASE 2C2: Invalid move - deselect and provide feedback
            else:
                print(f"Invalid move: {move} - deselecting piece")
                self.selected_square = None  # Clear selection on invalid move

    # =============================================
    # ================= AI PLAY ===================

    # Only use if UI starts to crash, especially during ai vs ai play, headless mode should reduce the need
    def ai_move_async(self):
        # Validate current board state
        if not self.board.is_valid():
            print("ERROR: Invalid board state detected!")
            self.board = chess.Board(self.board.fen())
            return None
        
        if not list(self.board.legal_moves):
            return None
            
        # Store the current player BEFORE making moves
        current_player = self.board.turn
        best_move = None
        best_score = -float('inf') if current_player == chess.WHITE else float('inf')
        
        # Get list of available moves
        legal_moves = list(self.board.legal_moves)
        
        # IMPROVEMENT: Process events periodically to prevent UI freezing
        start_time = pygame.time.get_ticks()
        moves_evaluated = 0
        
        # IMPROVEMENT: Iterative deepening - start with depth 1 and increase gradually
        max_search_depth = self.config['ai']['search_depth']
        current_depth = 1
        move_scores = {}  # Store move scores for reuse
        
        # Limit total calculation time
        max_calculation_time = 1000  # 1 second max for AI move
        
        # Main iterative deepening loop
        while current_depth <= max_search_depth and pygame.time.get_ticks() - start_time < max_calculation_time:
            print(f"Searching at depth {current_depth}...")
            
            # For each legal move
            for move_index, move in enumerate(legal_moves):
                # Process events every few moves to keep UI responsive
                if moves_evaluated % 5 == 0:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()
                
                # Make the move on the board
                self.board.push(move)
                
                # Reuse a single board object in the evaluator
                self.evaluator.board = self.board  # Direct reference, no copy
                
                # Use iterative deepening - only search to current_depth
                if self.config['ai']['use_lookahead']:
                    self.evaluator.search_depth = current_depth
                    current_eval = self.evaluator.evaluate_position_with_lookahead()
                else:
                    current_eval = self.evaluator.evaluate_position_from_perspective(current_player)
                
                # Store score for this move at this depth
                move_key = move.uci()
                move_scores[move_key] = current_eval
                
                # Undo the move
                self.board.pop()
                
                moves_evaluated += 1
                
                # Check if we're out of time
                if pygame.time.get_ticks() - start_time > max_calculation_time:
                    print(f"Time limit reached at depth {current_depth}")
                    break
            
            # Find best move at current depth
            temp_best_move = None
            temp_best_score = -float('inf') if current_player == chess.WHITE else float('inf')
            
            for move in legal_moves:
                move_key = move.uci()
                if move_key in move_scores:
                    score = move_scores[move_key]
                    if ((current_player == chess.WHITE and score > temp_best_score) or
                        (current_player == chess.BLACK and score < temp_best_score)):
                        temp_best_score = score
                        temp_best_move = move
            
            # Update best move if we completed this depth
            if temp_best_move is not None:
                best_move = temp_best_move
                best_score = temp_best_score
                
            # Move to next depth
            current_depth += 1
            
            # Force garbage collection between depths
            import gc
            gc.collect()
        
        # Store evaluation for display
        self.current_eval = best_score
        self._record_evaluation(best_score)
        
        return best_move.uci() if best_move else None

    def ai_move(self):
        """AI MOVE SELECTION - SYNCRONOUS"""
        # Validate current board state
        if not self.board.is_valid():
            print("ERROR: Invalid board state detected!")
            self.board = chess.Board(self.board.fen())
            return None

        if not list(self.board.legal_moves):
            return None

        # Store the current player BEFORE making moves
        current_player = self.board.turn

        best_move = None
        best_score = -float('inf') if current_player == chess.WHITE else float('inf')

        # Get list of available moves
        legal_moves = list(self.board.legal_moves)

        print(f"\n== AI MOVE EVALUATION (Player: {'White' if current_player == chess.WHITE else 'Black'} | Depth: {self.config['ai']['search_depth']} ==")

        for move in legal_moves:
            self.board.push(move)

            # CRITICAL FIX: Update evaluator's board before evaluation
            self.evaluator.board = self.board.copy()

            # Use the evaluation function
            if self.config['ai']['use_lookahead']:
                current_eval = self.evaluator.evaluate_position_with_lookahead()
            else:
                current_eval = self.evaluator.evaluate_position_from_perspective(current_player)

            self.board.pop()

            print(f"Considering move: {move} | Resulting eval: {current_eval:.3f}")

            # Select best move based on CURRENT PLAYER
            if (current_player == chess.WHITE and current_eval > best_score) or \
               (current_player == chess.BLACK and current_eval < best_score):
                best_score = current_eval
                best_move = move

        # Store evaluation for display
        self.current_eval = best_score
        self._record_evaluation(best_score)

        print(f"Selected move: {best_move} (Evaluation: {best_score:.3f})")
        self.quick_save_pgn()
        return best_move.uci() if best_move else None

    def process_ai_move(self):
        # Allow AI to play both sides in AI vs AI mode
        if not self.ai_vs_ai and self.board.turn != self.ai_color:
            return  # Only check AI color in human vs AI mode
        
        try:
            ai_move = self.ai_move()
            if ai_move and self.push_move(ai_move):
                current_player = "White" if self.board.turn == chess.BLACK else "Black"  # Turn has switched after move
                print(f"AI ({current_player}) plays: {ai_move} (Eval: {self.current_eval:.2f})")
                
                # Store the destination square
                move_obj = chess.Move.from_uci(ai_move)
                self.last_ai_move = move_obj.to_square
            else:
                # Fallback to random legal move
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves)
                    print(f"AI fallback: {fallback.uci()}")
                    self.push_move(fallback.uci())
        except Exception as e:
            print(f"AI move error: {e}")
            self.save_pgn("error_dump.pgn")

    def push_move(self, move_uci):
        try:
            move = chess.Move.from_uci(move_uci)
            if not self.board.is_legal(move): # Use is_legal instead of checking list
                print(f"Illegal move blocked: {move_uci}")
                return False

            self.game_node = self.game_node.add_variation(move)
            self.board.push(move)
            return True
        except ValueError:
            return False

if __name__ == "__main__":
    game = ChessGame()
    game.run()