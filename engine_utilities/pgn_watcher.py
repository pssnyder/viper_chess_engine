# pgn_watcher.py

import os
import time
import pygame
import chess
import chess.pgn
from chess_game import ChessGame, WIDTH, HEIGHT


class PGNWatcher:
    def __init__(self, pgn_path="logging/active_game.pgn"):
        self.pgn_path = pgn_path
        self.last_mtime = 0
        pygame.init()
        # instantiate ChessGame purely for its draw routines
        self.game = ChessGame()
        self.game.watch_mode = True
        # force a display surface
        self.game.screen = pygame.display.set_mode((WIDTH, WIDTH))
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
        # read the PGN and replay mainline
        with open(self.pgn_path, "r") as f:
            game = chess.pgn.read_game(f)
        board = chess.Board()
        if game:
            for mv in game.mainline_moves():
                board.push(mv)
        # update ChessGame state
        self.game.board = board
        self.game.selected_square = None
        self.game.last_ai_move = None
        self.game.mark_display_dirty()


if __name__ == "__main__":
    PGNWatcher().run()