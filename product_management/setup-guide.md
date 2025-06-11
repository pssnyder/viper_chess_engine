# Chess Engine GUI Setup Guide

This guide will help you set up and run the local chess GUI interface to test your evaluation engine.

## Quick Start

### 1. Install Required Packages

Create a `requirements.txt` file:

```
pygame>=2.1.0
python-chess>=1.999
numpy>=1.21.0
```

Then install:
```bash
pip install -r requirements.txt
```

### 2. Setup Script (setup.py)

```python
#!/usr/bin/env python3
"""
Setup script for Chess Engine GUI Testing Interface
Installs dependencies and verifies the setup
"""

import subprocess
import sys
import os

def install_package(package):
    """Install a package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        return False

def check_import(module_name):
    """Check if a module can be imported"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def main():
    print("Chess Engine GUI Setup")
    print("=" * 40)
    
    # Required packages
    packages = {
        'pygame': 'pygame>=2.1.0',
        'chess': 'python-chess>=1.999',
        'numpy': 'numpy>=1.21.0'
    }
    
    print("\n1. Checking and installing dependencies...")
    
    all_good = True
    for module, package in packages.items():
        print(f"   Checking {module}...", end=" ")
        
        if check_import(module):
            print("✓ Already installed")
        else:
            print("✗ Missing, installing...")
            if install_package(package):
                print(f"   ✓ {module} installed successfully")
            else:
                print(f"   ✗ Failed to install {module}")
                all_good = False
    
    print("\n2. Checking project files...")
    
    required_files = ['evaluation_engine.py']
    for file in required_files:
        if os.path.exists(file):
            print(f"   ✓ {file} found")
        else:
            print(f"   ✗ {file} missing - make sure it's in the same directory")
            all_good = False
    
    print("\n3. Creating chess_gui.py...")
    
    # Create the chess GUI file if it doesn't exist
    if not os.path.exists('chess_gui.py'):
        with open('chess_gui.py', 'w') as f:
            f.write(get_chess_gui_code())
        print("   ✓ chess_gui.py created")
    else:
        print("   ✓ chess_gui.py already exists")
    
    print("\n" + "=" * 40)
    
    if all_good:
        print("✓ Setup completed successfully!")
        print("\nTo run the chess GUI:")
        print("   python chess_gui.py")
        print("\nControls:")
        print("   - Left click: Select pieces and make moves")
        print("   - R: Reset game")
        print("   - ESC: Quit")
    else:
        print("✗ Setup encountered some issues.")
        print("Please resolve the missing dependencies or files.")
    
    print("\n" + "=" * 40)

def get_chess_gui_code():
    """Return the chess GUI code as a string"""
    return '''import pygame
import chess
import sys
import os
from evaluation_engine import EvaluationEngine

class ChessGUI:
    def __init__(self, width=800, height=800):
        pygame.init()
        self.width = width
        self.height = height
        self.board_size = min(width, height) - 100
        self.square_size = self.board_size // 8
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Chess Engine Testing Interface")
        
        # Colors
        self.LIGHT_BROWN = (240, 217, 181)
        self.DARK_BROWN = (181, 136, 99)
        self.HIGHLIGHT_COLOR = (255, 255, 0, 128)
        self.LEGAL_MOVE_COLOR = (0, 255, 0, 100)
        self.CHECK_COLOR = (255, 0, 0, 128)
        self.WHITE = (255, 255, 255)
        self.BLACK = (0, 0, 0)
        self.GRAY = (128, 128, 128)
        
        # Game state
        self.board = chess.Board()
        self.selected_square = None
        self.legal_moves = []
        self.engine = None
        self.engine_depth = 3
        self.human_color = chess.WHITE
        self.game_over = False
        
        # UI elements
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.piece_images = self._load_piece_images()
        self.clock = pygame.time.Clock()
        
    def _load_piece_images(self):
        pieces = {}
        unicode_pieces = {
            'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
            'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
        }
        
        piece_font = pygame.font.Font(None, self.square_size - 10)
        for symbol, unicode_char in unicode_pieces.items():
            color = self.WHITE if symbol.isupper() else self.BLACK
            text_surface = piece_font.render(unicode_char, True, color)
            pieces[symbol] = text_surface
        return pieces
    
    def setup_engine(self, engine_class=None, depth=3):
        self.engine_depth = depth
        if engine_class:
            self.engine = engine_class(self.board, depth)
        else:
            self.engine = EvaluationEngine(self.board, depth)
    
    def coord_to_square(self, pos):
        x, y = pos
        if x < 50 or x > 50 + self.board_size or y < 50 or y > 50 + self.board_size:
            return None
        file = (x - 50) // self.square_size
        rank = 7 - ((y - 50) // self.square_size)
        if 0 <= file <= 7 and 0 <= rank <= 7:
            return chess.square(file, rank)
        return None
    
    def square_to_coord(self, square):
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        x = 50 + file * self.square_size
        y = 50 + (7 - rank) * self.square_size
        return (x, y)
    
    def draw_board(self):
        self.screen.fill(self.WHITE)
        for rank in range(8):
            for file in range(8):
                color = self.LIGHT_BROWN if (rank + file) % 2 == 0 else self.DARK_BROWN
                rect = pygame.Rect(50 + file * self.square_size, 50 + rank * self.square_size,
                                 self.square_size, self.square_size)
                pygame.draw.rect(self.screen, color, rect)
        
        border_rect = pygame.Rect(50, 50, self.board_size, self.board_size)
        pygame.draw.rect(self.screen, self.BLACK, border_rect, 3)
        
        for i in range(8):
            file_label = chr(ord('a') + i)
            text = self.small_font.render(file_label, True, self.BLACK)
            text_rect = text.get_rect(center=(50 + i * self.square_size + self.square_size // 2, 35))
            self.screen.blit(text, text_rect)
            
            rank_label = str(8 - i)
            text = self.small_font.render(rank_label, True, self.BLACK)
            text_rect = text.get_rect(center=(25, 50 + i * self.square_size + self.square_size // 2))
            self.screen.blit(text, text_rect)
    
    def draw_highlights(self):
        if self.selected_square is not None:
            x, y = self.square_to_coord(self.selected_square)
            highlight_surface = pygame.Surface((self.square_size, self.square_size), pygame.SRCALPHA)
            highlight_surface.fill(self.HIGHLIGHT_COLOR)
            self.screen.blit(highlight_surface, (x, y))
        
        for move in self.legal_moves:
            x, y = self.square_to_coord(move.to_square)
            move_surface = pygame.Surface((self.square_size, self.square_size), pygame.SRCALPHA)
            move_surface.fill(self.LEGAL_MOVE_COLOR)
            self.screen.blit(move_surface, (x, y))
            center_x = x + self.square_size // 2
            center_y = y + self.square_size // 2
            pygame.draw.circle(self.screen, (0, 200, 0), (center_x, center_y), 8)
        
        if self.board.is_check():
            king_square = self.board.king(self.board.turn)
            if king_square is not None:
                x, y = self.square_to_coord(king_square)
                check_surface = pygame.Surface((self.square_size, self.square_size), pygame.SRCALPHA)
                check_surface.fill(self.CHECK_COLOR)
                self.screen.blit(check_surface, (x, y))
    
    def draw_pieces(self):
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece:
                piece_symbol = piece.symbol()
                if piece_symbol in self.piece_images:
                    piece_surface = self.piece_images[piece_symbol]
                    x, y = self.square_to_coord(square)
                    piece_rect = piece_surface.get_rect()
                    piece_rect.center = (x + self.square_size // 2, y + self.square_size // 2)
                    self.screen.blit(piece_surface, piece_rect)
    
    def draw_ui(self):
        status_y = self.board_size + 80
        
        if self.game_over:
            if self.board.is_checkmate():
                winner = "Black" if self.board.turn else "White"
                status_text = f"Checkmate! {winner} wins!"
            elif self.board.is_stalemate():
                status_text = "Stalemate - Draw!"
            elif self.board.is_insufficient_material():
                status_text = "Draw - Insufficient material"
            else:
                status_text = "Game Over"
        else:
            turn_text = "White" if self.board.turn else "Black"
            status_text = f"{turn_text} to move"
            if self.board.is_check():
                status_text += " - Check!"
        
        status_surface = self.font.render(status_text, True, self.BLACK)
        self.screen.blit(status_surface, (50, status_y))
        
        if self.engine and not self.game_over:
            try:
                eval_score = self.engine.evaluate_position()
                eval_text = f"Evaluation: {eval_score:.2f}"
                eval_surface = self.small_font.render(eval_text, True, self.BLACK)
                self.screen.blit(eval_surface, (300, status_y))
            except:
                pass
        
        controls = ["Left click: Select piece/move", "R: Reset game", "ESC: Quit"]
        for i, control in enumerate(controls):
            control_surface = self.small_font.render(control, True, self.GRAY)
            self.screen.blit(control_surface, (50, status_y + 40 + i * 25))
    
    def get_legal_moves_from_square(self, square):
        return [move for move in self.board.legal_moves if move.from_square == square]
    
    def make_move(self, move):
        if move in self.board.legal_moves:
            self.board.push(move)
            if self.engine:
                self.engine.board = self.board.copy()
            if self.board.is_game_over():
                self.game_over = True
            self.selected_square = None
            self.legal_moves = []
            return True
        return False
    
    def get_engine_move(self):
        if not self.engine or self.game_over:
            return None
        try:
            self.engine.board = self.board.copy()
            best_score = float('-inf')
            best_move = None
            for move in self.board.legal_moves:
                score = self.engine.evaluate_move(move)
                if score > best_score:
                    best_score = score
                    best_move = move
            return best_move
        except Exception as e:
            print(f"Engine error: {e}")
            return None
    
    def handle_click(self, pos):
        square = self.coord_to_square(pos)
        if square is None:
            return
        
        if self.selected_square is None:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                self.selected_square = square
                self.legal_moves = self.get_legal_moves_from_square(square)
        else:
            move = None
            for legal_move in self.legal_moves:
                if legal_move.to_square == square:
                    move = legal_move
                    break
            
            if move:
                self.make_move(move)
            else:
                piece = self.board.piece_at(square)
                if piece and piece.color == self.board.turn:
                    self.selected_square = square
                    self.legal_moves = self.get_legal_moves_from_square(square)
                else:
                    self.selected_square = None
                    self.legal_moves = []
    
    def reset_game(self):
        self.board = chess.Board()
        self.selected_square = None
        self.legal_moves = []
        self.game_over = False
        if self.engine:
            self.engine.board = self.board.copy()
    
    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self.reset_game()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.board.turn == self.human_color or not self.engine:
                            self.handle_click(event.pos)
            
            if (not self.game_over and self.engine and 
                self.board.turn != self.human_color and self.selected_square is None):
                engine_move = self.get_engine_move()
                if engine_move:
                    self.make_move(engine_move)
            
            self.draw_board()
            self.draw_highlights()
            self.draw_pieces()
            self.draw_ui()
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()

def main():
    print("Chess Engine Testing Interface")
    print("=" * 40)
    gui = ChessGUI()
    
    try:
        gui.setup_engine(depth=3)
        print("✓ Evaluation engine loaded successfully")
        print(f"✓ Engine depth set to {gui.engine_depth}")
        print("✓ Human plays White, Engine plays Black")
    except Exception as e:
        print(f"⚠ Warning: Could not load engine: {e}")
        print("✓ Running in human vs human mode")
    
    print("\\nControls:")
    print("- Left click to select pieces and make moves")
    print("- R to reset the game")
    print("- ESC to quit")
    print("\\nStarting game...")
    gui.run()

if __name__ == "__main__":
    main()
'''

if __name__ == "__main__":
    main()