# chess_game.py
# Simplified version - pure evaluation engine, no neural network

import os
import sys
import pygame
import chess
import chess.pgn
from evaluation_engine import EvaluationEngine
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
        # Initialize Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('v7p3r Chess Bot - Pure Evaluation Engine')
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
        
        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)
        
        # Set up game config
        self.ai_vs_ai = self.config['game']['ai_vs_ai']
        self.human_color_pref = self.config['game']['human_color']
        
        # Game recording
        self.game = chess.pgn.Game()
        self.ai_color = None  # Will be set in run()
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
        self.last_ai_move = None  # Track AI's last move
        
        # Pure evaluation engine setup
        self.evaluator = EvaluationEngine(self.board, depth=self.config['ai']['search_depth'])
        self.current_eval = None
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Set colors
        self._set_colors()

    def _set_colors(self):
        if self.ai_vs_ai:
            self.flip_board = False  # White on bottom for AI vs AI
            self.human_color = None
            self.ai_color = chess.WHITE
        else:
            # Convert human_color_pref to 'w'/'b' format
            if self.human_color_pref.lower() in ['white', 'w']:
                user_color = 'w'
            elif self.human_color_pref.lower() in ['black', 'b']:
                user_color = 'b'
            else:
                user_color = random.choice(['w', 'b'])  # Fallback to random
            
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

    def draw_eval(self):
        if self.current_eval is not None:
            # Display evaluation from current player's perspective
            display_eval = self.current_eval
            
            # Format with proper sign
            eval_str = f"{display_eval:+.2f}"
            
            # Color coding: green for positive, red for negative, black for neutral
            if abs(display_eval) < 0.5:
                color = (0, 0, 0)  # Black for neutral
            elif display_eval > 0:
                color = (0, 255, 0)  # Green for advantage
            else:
                color = (255, 0, 0)  # Red for disadvantage
            
            # Render text
            text = self.font.render(f"Eval: {eval_str}", True, color)
            self.screen.blit(text, (WIDTH-150, 10))
            
            # Also show depth
            depth_text = self.font.render(f"Depth: {self.config['ai']['search_depth']}", True, (0, 0, 0))
            self.screen.blit(depth_text, (WIDTH-150, 35))

    def ai_move(self):
        """Pure evaluation-based move selection with alpha-beta pruning"""
        # Validate current board state
        if not self.board.is_valid():
            print("ERROR: Invalid board state detected!")
            self.board = chess.Board(self.board.fen())  # Attempt to recover
            return None
        
        if not list(self.board.legal_moves):
            return None
        
        # Update evaluator with current board state
        self.evaluator.board = self.board.copy()
        
        best_move = None
        best_score = -float('inf') if self.board.turn == chess.WHITE else float('inf')
        
        # Prioritize captures and checks for move ordering
        legal_moves = list(self.board.legal_moves)
        ordered_moves = self._order_moves(legal_moves)
        
        for move in ordered_moves:
            self.board.push(move)
            
            if self.config['ai']['use_lookahead']:
                current_eval = self.evaluator.evaluate_position_with_lookahead()
            else:
                current_eval = self.evaluator.evaluate_position()
            
            self.board.pop()
            
            # Select best move based on turn
            if (self.board.turn == chess.WHITE and current_eval > best_score) or \
               (self.board.turn == chess.BLACK and current_eval < best_score):
                best_score = current_eval
                best_move = move
        
        # Store evaluation for display
        self.current_eval = best_score
        self._record_evaluation(best_score)
        
        return best_move.uci() if best_move else None

    def _order_moves(self, moves):
        """Much better move ordering for alpha-beta efficiency"""
        def move_priority(move):
            priority = 0
            
            # 1. Promotions first (highest priority)
            if move.promotion:
                priority += 10000
            
            # 2. Captures with MVV-LVA (Most Valuable Victim - Least Valuable Attacker)
            if self.board.is_capture(move):
                victim = self.board.piece_at(move.to_square)
                attacker = self.board.piece_at(move.from_square)
                if victim and attacker:
                    victim_value = self.piece_values.get(victim.piece_type, 0)
                    attacker_value = self.piece_values.get(attacker.piece_type, 0)
                    priority += victim_value * 100 - attacker_value  # MVV-LVA
            
            # 3. Checks
            self.board.push(move)
            if self.board.is_check():
                priority += 500
            self.board.pop()
            
            # 4. Castling
            if self.board.is_castling(move):
                priority += 300
            
            # 5. Center moves
            if move.to_square in {27, 28, 35, 36}:  # d4, e4, d5, e5
                priority += 100
            
            return priority
        
        return sorted(moves, key=move_priority, reverse=True)
    
    def static_exchange_evaluation(self, move):
        """Evaluate capture sequences"""
        return self.evaluator.static_exchange_evaluation(move)

    def highlight_last_move(self):
        """Highlight AI's last move on the board"""
        if self.last_ai_move:
            screen_x, screen_y = self._chess_to_screen(self.last_ai_move)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('yellow'))
            self.screen.blit(s, (screen_x, screen_y))

    def _record_evaluation(self, score):
        """Record evaluation score in PGN comments"""
        if self.game_node.move:
            self.game_node.comment = f"Eval: {score:.2f}"
        else:
            self.game.comment = f"Initial Eval: {score:.2f}"

    def draw_board(self):
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
        # Draw pieces
        for r in range(DIMENSION):
            for c in range(DIMENSION):
                # Calculate chess square based on perspective
                if self.flip_board:
                    file = 7 - c
                    rank = r  # Black's perspective
                else:
                    file = c
                    rank = 7 - r  # White's perspective
                
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

    def handle_mouse_click(self, pos):
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
        
        if self.selected_square is None:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn and self.board.turn == self.human_color:
                self.selected_square = square
        else:
            move = chess.Move(self.selected_square, square)
            
            # Check for pawn promotion
            if (self.board.piece_at(self.selected_square) and
                self.board.piece_at(self.selected_square).piece_type == chess.PAWN):
                target_rank = chess.square_rank(square)
                if (target_rank == 7 and self.board.turn == chess.WHITE) or \
                   (target_rank == 0 and self.board.turn == chess.BLACK):
                    move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)
            
            if move in self.board.legal_moves:
                # Update both game and PGN boards
                self.game_node = self.game_node.add_variation(move)
                self.board.push(move)
            
            self.selected_square = None

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

    def draw_move_hints(self):
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

    def highlight_selected_square(self):
        if self.selected_square:
            screen_x, screen_y = self._chess_to_screen(self.selected_square)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('blue'))
            self.screen.blit(s, (screen_x, screen_y))

    def run(self):
        running = True
        clock = pygame.time.Clock()
        
        # Initialize AI move timer if in AI vs AI mode
        if self.ai_vs_ai:
            pygame.time.set_timer(pygame.USEREVENT, 1000)
        
        while running:
            # Process all events first
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and not self.ai_vs_ai:
                    self.handle_mouse_click(pygame.mouse.get_pos())
                elif self.ai_vs_ai and event.type == pygame.USEREVENT:
                    if not self.board.is_game_over():
                        self.process_ai_move()
            
            # Handle AI moves in human vs AI mode
            if not self.ai_vs_ai and self.board.turn == self.ai_color and not self.board.is_game_over():
                self.process_ai_move()
            
            # Update display
            self.update_display()
            clock.tick(MAX_FPS)
            
            # Check game end conditions
            if self.handle_game_end():
                running = False
        
        pygame.quit()

    def process_ai_move(self):
        if self.board.turn != self.ai_color:  # Strict turn validation
            return
        try:
            ai_move = self.ai_move()
            if ai_move and self.push_move(ai_move):
                print(f"AI plays: {ai_move} (Eval: {self.current_eval:.2f})")
                # FIXED: Store the destination square, not the move object
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
            if not self.board.is_legal(move):  # Use is_legal instead of checking list
                print(f"Illegal move blocked: {move_uci}")
                return False
            self.board.push(move)
            return True
        except ValueError:
            return False

    def update_display(self):
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

    def handle_game_end(self):
        """Check and handle game termination"""
        if self.board.is_game_over():
            result = self.board.result()
            print(f"\nGame over: {result}")
            self.game.headers["Result"] = result
            self.save_pgn()
            return True
        return False

    def save_pgn(self, filename="eval_game.pgn"):
        try:
            # Validate all moves in the game
            board = self.game.board()
            move_count = 0
            
            for move in self.game.mainline_moves():
                if not board.is_legal(move):
                    raise ValueError(f"Illegal PGN move: {move.uci()}")
                board.push(move)
                move_count += 1

            # Proceed with saving
            with open(filename, "w") as f:
                exporter = chess.pgn.FileExporter(f)
                self.game.accept(exporter)
            print(f"Game saved to {filename}")
        except Exception as e:
            print(f"Critical PGN error: {e}")
            # Generate emergency FEN dump
            with open("crash_dump.fen", "w") as f:
                f.write(f"Final FEN: {self.board.fen()}\n")
                f.write(f"Legal moves: {list(self.board.legal_moves)}\n")


if __name__ == "__main__":
    game = ChessGame()
    game.run()