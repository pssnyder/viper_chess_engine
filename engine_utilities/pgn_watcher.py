# pgn_watcher.py

import os
import time
import pygame
import chess
import chess.pgn
import sys

# Define constants locally instead of importing from chess_game
WIDTH, HEIGHT = 640, 640
DIMENSION = 8
SQ_SIZE = WIDTH // DIMENSION
MAX_FPS = 15
IMAGES = {}

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base = getattr(sys, '_MEIPASS', None)
    if base:
        return os.path.join(base, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class StandaloneChessRenderer:
    """Simplified standalone renderer for chess positions"""
    
    def __init__(self):
        self.board = chess.Board()
        self.watch_mode = True
        self.screen: pygame.Surface | None = None
        self.selected_square = None
        self.last_ai_move = None
        self.flip_board = False
        self.display_needs_update = True
        self.screen_ready = False
        
    def load_images(self):
        """Load chess piece images"""
        pieces = ['wp', 'wN', 'wb', 'wr', 'wq', 'wk',
                 'bp', 'bN', 'bb', 'br', 'bq', 'bk']
        for piece in pieces:
            try:
                IMAGES[piece] = pygame.transform.scale(
                    pygame.image.load(resource_path(f"images/{piece}.png")),
                    (SQ_SIZE, SQ_SIZE)
                )
            except pygame.error:
                print(f"Could not load image for {piece}")
                
    def draw_board(self):
        """Draw the chess board"""
        if not self.watch_mode or self.screen is None:
            return
        colors = [pygame.Color("#a8a9a8"), pygame.Color("#d8d9d8")]
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
                
    def _piece_image_key(self, piece):
        """Convert chess piece to image key"""
        color = 'w' if piece.color == chess.WHITE else 'b'
        symbol = piece.symbol().upper()
        return f"{color}N" if symbol == 'N' else f"{color}{symbol.lower()}"
    
    def draw_pieces(self):
        """Draw pieces on the board"""
        if not self.watch_mode or self.screen is None:
            return
        for r in range(DIMENSION):
            for c in range(DIMENSION):
                # Calculate chess square based on perspective
                if self.flip_board:
                    file = 7 - c
                    rank = r
                else:
                    file = c
                    rank = 7 - r

                square = chess.square(file, rank)
                piece = self.board.piece_at(square)

                if piece:
                    # Calculate screen position
                    screen_x = c * SQ_SIZE
                    screen_y = r * SQ_SIZE

                    piece_key = self._piece_image_key(piece)
                    if piece_key in IMAGES:
                        self.screen.blit(IMAGES[piece_key], (screen_x, screen_y))
    
    def highlight_last_move(self):
        """Highlight the last move on the board"""
        if not self.watch_mode or self.screen is None or not self.board.move_stack:
            return
        
        last_move = self.board.move_stack[-1]
        for square in [last_move.from_square, last_move.to_square]:
            screen_x, screen_y = self.chess_to_screen(square)
            s = pygame.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(100)
            s.fill(pygame.Color('yellow'))
            self.screen.blit(s, (screen_x, screen_y))
    
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
    
    def mark_display_dirty(self):
        """Mark the display as needing an update"""
        self.display_needs_update = True
    
    def update_display(self):
        """Update the display"""
        if not self.watch_mode or self.screen is None:
            return
            
        if self.display_needs_update:
            self.draw_board()
            self.draw_pieces()
            
            if self.board.move_stack:
                self.highlight_last_move()
                
            pygame.display.flip()
            self.display_needs_update = False
            self.screen_ready = True


class PGNWatcher:
    def __init__(self, pgn_path="logging/active_game.pgn"):
        self.pgn_path = pgn_path
        self.last_mtime = 0
        pygame.init()
        
        # Use standalone renderer instead of ChessGame
        self.game = StandaloneChessRenderer()
        self.game.watch_mode = True
        self.game.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("PGN Watcher")
        self.game.load_images()
        self.clock = pygame.time.Clock()

    def run(self):
        running = True
        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
            # poll file modification
            try:
                mtime = os.path.getmtime(self.pgn_path)
                if mtime != self.last_mtime:
                    self.last_mtime = mtime
                    self._reload_pgn()
            except FileNotFoundError:
                pass
                
            # redraw if needed
            if self.game.screen:
                self.game.update_display()
            self.clock.tick(10)
        pygame.quit()

    def _reload_pgn(self):
        try:
            # read the PGN and replay mainline
            with open(self.pgn_path, "r") as f:
                game = chess.pgn.read_game(f)
            
            if game:
                board = game.board()
                for mv in game.mainline_moves():
                    board.push(mv)
                
                # update renderer state
                self.game.board = board
                self.game.selected_square = None
                self.game.mark_display_dirty()
                
                # Print some info about the game
                print(f"Loaded game: {game.headers.get('White', 'Unknown')} vs {game.headers.get('Black', 'Unknown')}")
                print(f"Current position: {board.fen()}")
        except Exception as e:
            print(f"Error reloading PGN: {e}")


if __name__ == "__main__":
    # Create logging directory if it doesn't exist
    os.makedirs("logging", exist_ok=True)
    
    # Default path to watch
    pgn_path = "logging/active_game.pgn"
    
    # Allow command-line override
    if len(sys.argv) > 1:
        pgn_path = sys.argv[1]
    
    print(f"Watching PGN file: {pgn_path}")
    PGNWatcher(pgn_path).run()