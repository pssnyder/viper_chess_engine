# chess_game.py
import sys
import os
from functools import lru_cache
from chess_core import ChessAI, ChessDataset
from evaluation_engine import EvaluationEngine
import chess
import chess.pgn
import torch
import numpy as np
import pygame
import random
import yaml
import datetime
import time
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

torch.set_float32_matmul_precision('high')  # Improve GPU performance

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
    def __init__(self, model_path, username="User"):
        
        # Initialize Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('v7p3r Chess AI')
        self.clock = pygame.time.Clock()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Initialize chess components
        self.board = chess.Board()
        self.selected_square = None
        self.player_clicks = []
        self.load_images()
        
        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)
            
         # Load move vocabulary
        import pickle
        with open("move_vocab.pkl", "rb") as f:
            self.move_to_index = pickle.load(f)
        
        # Initialize model
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        # Initialize model WITHOUT compilation first
        self.model = ChessAI(num_classes=len(self.move_to_index), config=self.config).to(self.device)
        # Load state_dict into base model
        self.load_model_weights(model_path)
        # Compile model AFTER loading weights
        # missing cl at the moment
        #self.model = torch.compile(self.model)
        
        # Add AI thread status
        self.ai_thinking = False
        self.current_ai_move = None
        
        # Set up game config
        self.ai_vs_ai = self.config['game']['ai_vs_ai']
        self.human_color_pref = self.config['game']['human_color']
        
        # Game recording
        self.game = chess.pgn.Game()
        self.username = username
        self.ai_color = None  # Will be set in run()
        self.human_color = None
        self.game_node = self.game
        
        # Initialize PGN headers
        self.game.headers["Event"] = "Human vs. AI Testing"
        self.game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        self.game.headers["Site"] = "Local Computer"
        self.game.headers["Round"] = "#"
        
        # Turn management
        self.last_ai_move = None  # Track AI's last move
        
        # Game eval config
        self.current_eval = None
        self.font = pygame.font.SysFont('Arial', 24)
        
        # Set colors
        self._set_colors()
    
    def load_model_weights(self, path):
        """Handle compiled/non-compiled weight loading"""
        try:
            # First try direct load
            self.model.load_state_dict(torch.load(path, map_location=self.device))
        except RuntimeError:
            # Fallback: Remove '_orig_mod.' prefix if present
            self.model.load_state_dict(
                {k.replace('_orig_mod.', ''): v 
                 for k, v in torch.load(path, map_location=self.device).items()}
            )
                
    def ai_move_async(self):
        self.ai_thinking = True
        try:
            self.current_ai_move = self.ai_move()
        finally:
            self.ai_thinking = False
            
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
            self.game.headers["White"] = "v7p3r_chess_ai"
            self.game.headers["Black"] = "v7p3r_chess_ai"
        else:
            self.game.headers["White"] = "v7p3r_chess_ai" if self.ai_color == chess.WHITE else self.username
            self.game.headers["Black"] = self.username if self.ai_color == chess.WHITE else "v7p3r_chess_ai"
        
    def load_images(self):
        pieces = ['wp', 'wN', 'wb', 'wr', 'wq', 'wk', 
                 'bp', 'bN', 'bb', 'br', 'bq', 'bk']
        for piece in pieces:
            IMAGES[piece] = pygame.transform.scale(
                pygame.image.load(resource_path(f"images/{piece}.png")), 
                (SQ_SIZE, SQ_SIZE)
            )

    def draw_eval(self):
        if self.current_eval is not None:
            # Get perspective-adjusted evaluation
            perspective = 1 if self.board.turn == chess.WHITE else -1
            display_eval = self.current_eval * perspective
            
            # Format with proper sign
            eval_str = f"{display_eval:+.2f}"
            color = (0,0,0) if abs(display_eval) < 0.5 else (0,255,0) if display_eval > 0 else (255,0,0)
            
            # Render text
            text = self.font.render(f"Eval: {eval_str}", True, color)
            self.screen.blit(text, (WIDTH-150, 10))

    @lru_cache(maxsize=128)
    def board_to_tensor(self, fen):
        board = chess.Board(fen)
        tensor = torch.zeros(13, 8, 8, dtype=torch.float32, device=self.device)  # Changed from 12 to 13
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                channel = piece.piece_type - 1 + (6 if piece.color == chess.BLACK else 0)
                tensor[channel][7 - square//8][square%8] = 1
        # Add promotion flag
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.piece_type == chess.PAWN:
                rank = chess.square_rank(square)
                if rank in [1, 6]:
                    tensor[12][7 - square//8][square%8] = 1
        return tensor.unsqueeze(0)
    
    def ai_move(self):
        """Enhanced AI move selection with capture prioritization"""
        legal_moves = list(self.board.legal_moves)
        if not legal_moves:
            return None
        
        # Step 1: Prioritize profitable captures
        profitable_captures = []
        for move in legal_moves:
            if self.board.is_capture(move):
                see_score = self.static_exchange_evaluation(move)
                if see_score >= 0:
                    profitable_captures.append((move, see_score + 100))
        
        # Step 2: If profitable captures exist, prefer them
        if profitable_captures:
            profitable_captures.sort(key=lambda x: -x[1])
            for move, score in profitable_captures[:3]:
                if move.uci() in self.move_to_index:
                    self.current_eval = score
                    self._record_evaluation(score)
                    return move.uci()
        
        # Step 3: Neural network + rule evaluation fallback
        vocab_moves = [m for m in legal_moves if m.uci() in self.move_to_index]
        non_vocab_moves = [m for m in legal_moves if m.uci() not in self.move_to_index]
        
        best_move = None
        best_score = -float('inf')
        
        # Get neural network suggestions
        nn_moves = self._get_top_nn_moves(vocab_moves, top_n=5)
        
        # Always include rule-based evaluation
        rule_based_moves = self._evaluate_with_rules(non_vocab_moves[:5])
        
        # Combine and select best
        all_candidates = nn_moves + rule_based_moves
        for move, score in all_candidates:
            if score > best_score:
                best_score = score
                best_move = move
        
        # Store and record evaluation
        self.current_eval = best_score
        self._record_evaluation(best_score)
        
        return best_move.uci() if best_move else None


    def _get_top_nn_moves(self, moves, top_n=3):
        """Get top moves using neural network predictions"""
        scores = []
        for move in moves:
            tensor = self.board_to_tensor(self.board.fen())
            with torch.no_grad():
                logits = self.model(tensor)
                idx = self.move_to_index[move.uci()]
                scores.append((move, logits[0][idx].item()))
        return sorted(scores, key=lambda x: -x[1])[:top_n]

    def _evaluate_with_rules(self, moves):
        """Evaluate moves using rule-based system"""
        evaluator = EvaluationEngine(self.board)
        return [(m, evaluator.evaluate_move(m)) for m in moves]

    def _are_moves_strong(self, moves, threshold=0.5):
        """Check if any NN move exceeds confidence threshold"""
        return any(score > threshold for _, score in moves)

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
                
                # Determine color based on chess square, not screen position
                color = colors[(file + rank) % 2]
                pygame.draw.rect(
                    self.screen, 
                    color, 
                    pygame.Rect(c*SQ_SIZE, r*SQ_SIZE, SQ_SIZE, SQ_SIZE)
                )


    def draw_pieces(self):
        # Highlight AI's last move (single correct implementation)
        if self.last_ai_move:
            screen_x, screen_y = self._chess_to_screen(self.last_ai_move)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('yellow'))
            self.screen.blit(s, (screen_x, screen_y))
        
        # Draw pieces
        for r in range(DIMENSION):
            for c in range(DIMENSION):
                # Calculate chess square based on perspective
                if self.flip_board:
                    file = 7 - c
                    rank = r  # Black's perspective: rank 0 at screen bottom
                else:
                    file = c
                    rank = 7 - r  # White's perspective: rank 0 at screen bottom
                
                square = chess.square(file, rank)
                piece = self.board.piece_at(square)
                
                if piece:
                    # Calculate screen position (uses grid coordinates, not chess coordinates)
                    screen_x = c * SQ_SIZE
                    screen_y = r * SQ_SIZE
                    self.screen.blit(IMAGES[self._piece_image_key(piece)], (screen_x, screen_y))

    def _piece_image_key(self, piece):
        color = 'w' if piece.color == chess.WHITE else 'b'
        symbol = piece.symbol().upper()
        return f"{color}N" if symbol == 'N' else f"{color}{symbol.lower()}"

    def handle_mouse_click(self, pos):
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
            if piece and piece.color == self.board.turn:
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
            screen_rank = rank  # For flipped board, rank 0 is at screen bottom
        else:
            screen_file = file
            screen_rank = 7 - rank  # For normal board, rank 0 is at screen bottom
        
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
            if not self.ai_vs_ai and self.board.turn == self.ai_color and not self.ai_thinking:
                self.ai_thinking = True
                try:
                    self.process_ai_move()
                finally:
                    self.ai_thinking = False

            # Update display
            self.update_display()
            clock.tick(MAX_FPS)

            # Check game end conditions
            if self.handle_game_end():
                running = False

        pygame.quit()

    def process_ai_move(self):
        """Process AI move with strict validation"""
        try:
            ai_move = self.ai_move()
            if ai_move and self.push_move(ai_move):
                print(f"AI plays: {ai_move}")
                self.last_ai_move = chess.Move.from_uci(ai_move).to_square
            else:  # Fallback to random legal move
                legal_moves = list(self.board.legal_moves)
                if legal_moves:
                    fallback = random.choice(legal_moves).uci()
                    self.board.push_uci(fallback)
        except Exception as e:
            print(f"AI move error: {e}")
            self.save_pgn("error_dump.pgn")


    def push_move(self, move_uci):
        """Validate and push move to board"""
        try:
            move = chess.Move.from_uci(move_uci)
            if self.board.is_legal(move):
                self.board.push(move)
                # Add move to PGN only if legal
                self.game_node = self.game_node.add_variation(move)
                return True
            return False
        except ValueError:
            return False



    def update_display(self):
        """Optimized display update with double buffering"""
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


    def save_pgn(self, filename="ai_game.pgn"):
        if self.board.result() == "1/2-1/2":
            self.game.headers["Result"] = "1/2-1/2"
        else:
            self.game.headers["Result"] = "1-0" if self.board.result() == "1-0" else "0-1"
        
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            exporter.emit_commentary = True # Add evaluation commentary
            self.game.accept(exporter)

if __name__ == "__main__":
    game = ChessGame("v7p3r_chess_ai_model.pth")
    game.run()
