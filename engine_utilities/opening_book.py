# opening_book.py
# Simple opening book for better opening play

import chess
import random

class OpeningBook:
    def __init__(self):
        # Initialize the opening book
        self.book = {}
        self._populate_book()

    def _populate_book(self):
        """Populate the opening book with common openings"""
        # Format: position_fen -> [(move, weight)]
        # Higher weight means more likely to be chosen

        # Starting position
        start_pos = chess.Board().fen()
        self.book[start_pos] = [
            (chess.Move.from_uci("e2e4"), 40),  # King's Pawn
            (chess.Move.from_uci("d2d4"), 40),  # Queen's Pawn
            (chess.Move.from_uci("c2c4"), 20),  # English Opening
            (chess.Move.from_uci("g1f3"), 15),  # Reti Opening
        ]

        # After 1.e4
        e4_pos = chess.Board()
        e4_pos.push(chess.Move.from_uci("e2e4"))
        self.book[e4_pos.fen()] = [
            (chess.Move.from_uci("e7e5"), 40),   # Open Game
            (chess.Move.from_uci("c7c5"), 30),   # Sicilian Defense
            (chess.Move.from_uci("e7e6"), 20),   # French Defense
            (chess.Move.from_uci("c7c6"), 10),   # Caro-Kann Defense
        ]

        # After 1.d4
        d4_pos = chess.Board()
        d4_pos.push(chess.Move.from_uci("d2d4"))
        self.book[d4_pos.fen()] = [
            (chess.Move.from_uci("d7d5"), 40),   # Closed Game
            (chess.Move.from_uci("g8f6"), 30),   # Indian Defense
            (chess.Move.from_uci("f7f5"), 15),   # Dutch Defense
            (chess.Move.from_uci("e7e6"), 15),   # French-like setup
        ]

        # Add more common opening responses...

        # After 1.e4 e5
        open_game = chess.Board()
        open_game.push(chess.Move.from_uci("e2e4"))
        open_game.push(chess.Move.from_uci("e7e5"))
        self.book[open_game.fen()] = [
            (chess.Move.from_uci("g1f3"), 60),   # King's Knight
            (chess.Move.from_uci("f2f4"), 20),   # King's Gambit
            (chess.Move.from_uci("f1c4"), 20),   # Italian-like
        ]

        # After 1.e4 e5 2.Nf3
        ruy_lopez_pos = chess.Board()
        ruy_lopez_pos.push(chess.Move.from_uci("e2e4"))
        ruy_lopez_pos.push(chess.Move.from_uci("e7e5"))
        ruy_lopez_pos.push(chess.Move.from_uci("g1f3"))
        self.book[ruy_lopez_pos.fen()] = [
            (chess.Move.from_uci("b8c6"), 80),   # Knight defense
            (chess.Move.from_uci("d7d6"), 20),   # Philidor Defense
        ]

        # After 1.e4 e5 2.Nf3 Nc6
        ruy_main = chess.Board()
        ruy_main.push(chess.Move.from_uci("e2e4"))
        ruy_main.push(chess.Move.from_uci("e7e5"))
        ruy_main.push(chess.Move.from_uci("g1f3"))
        ruy_main.push(chess.Move.from_uci("b8c6"))
        self.book[ruy_main.fen()] = [
            (chess.Move.from_uci("f1b5"), 40),   # Ruy Lopez
            (chess.Move.from_uci("f1c4"), 30),   # Italian Game
            (chess.Move.from_uci("d2d4"), 20),   # Scotch Game
            (chess.Move.from_uci("b1c3"), 10),   # Four Knights
        ]

        # Add some common Sicilian lines...
        sicilian_pos = chess.Board()
        sicilian_pos.push(chess.Move.from_uci("e2e4"))
        sicilian_pos.push(chess.Move.from_uci("c7c5"))
        self.book[sicilian_pos.fen()] = [
            (chess.Move.from_uci("g1f3"), 50),   # Open Sicilian
            (chess.Move.from_uci("b1c3"), 25),   # Closed Sicilian
            (chess.Move.from_uci("c2c3"), 25),   # c3 Sicilian
        ]

        # Add more lines as needed...

    def get_book_move(self, board):
        """Get a move from the opening book if position is in the book"""
        # First try with the exact position
        fen = board.fen()
        if fen in self.book:
            moves = self.book[fen]
            # Choose a move based on weights
            total_weight = sum(weight for _, weight in moves)
            choice = random.randint(1, total_weight)
            current_weight = 0
            for move, weight in moves:
                current_weight += weight
                if choice <= current_weight:
                    return move

        # No book move found
        return None

    def add_position(self, board, move, weight=10):
        """Add a position-move pair to the opening book"""
        fen = board.fen()
        if fen not in self.book:
            self.book[fen] = []

        # Check if move already exists
        for i, (existing_move, existing_weight) in enumerate(self.book[fen]):
            if existing_move == move:
                # Update weight
                self.book[fen][i] = (move, existing_weight + weight)
                return

        # Add new move
        self.book[fen].append((move, weight))

    def save_to_file(self, filename='opening_book.txt'):
        """Save the opening book to a file"""
        with open(filename, 'w') as f:
            for fen, moves in self.book.items():
                for move, weight in moves:
                    f.write(f"{fen}|{move.uci()}|{weight}\n")

    def load_from_file(self, filename='opening_book.txt'):
        """Load the opening book from a file"""
        self.book = {}
        try:
            with open(filename, 'r') as f:
                for line in f:
                    if line.strip():
                        fen, move_uci, weight = line.strip().split('|')
                        if fen not in self.book:
                            self.book[fen] = []
                        self.book[fen].append((chess.Move.from_uci(move_uci), int(weight)))
            return True
        except FileNotFoundError:
            print(f"Opening book file {filename} not found.")
            return False

# Simple opening principles class for evaluation when out of book
class OpeningPrinciples:
    @staticmethod
    def evaluate_opening_principles(board):
        """Evaluate adherence to opening principles"""
        score = 0
        move_count = len(board.move_stack) // 2  # Full moves

        # Only apply in the first 10-12 moves
        if move_count > 12:
            return 0

        # 1. Control the center with pawns or pieces
        score += OpeningPrinciples._evaluate_center_control(board)

        # 2. Develop knights and bishops
        score += OpeningPrinciples._evaluate_piece_development(board)

        # 3. Castle early
        score += OpeningPrinciples._evaluate_castling(board)

        # 4. Don't move same piece twice
        score += OpeningPrinciples._evaluate_piece_efficiency(board)

        # 5. Don't bring queen out early
        score += OpeningPrinciples._evaluate_queen_development(board)

        # Return score from perspective of current player
        return score if board.turn == chess.WHITE else -score

    @staticmethod
    def _evaluate_center_control(board):
        """Evaluate center control"""
        score = 0
        center_squares = [chess.D4, chess.E4, chess.D5, chess.E5]

        # Bonus for pawns or pieces controlling center
        for square in center_squares:
            # Pawns on center squares
            piece = board.piece_at(square)
            if piece:
                if piece.piece_type == chess.PAWN:
                    score += 15 if piece.color == chess.WHITE else -15
                else:
                    score += 10 if piece.color == chess.WHITE else -10

            # Attacks on center squares
            if board.is_attacked_by(chess.WHITE, square):
                score += 5
            if board.is_attacked_by(chess.BLACK, square):
                score -= 5

        return score

    @staticmethod
    def _evaluate_piece_development(board):
        """Evaluate development of knights and bishops"""
        score = 0

        # Knight development
        for color in [chess.WHITE, chess.BLACK]:
            sign = 1 if color == chess.WHITE else -1
            knight_squares = [chess.B1, chess.G1] if color == chess.WHITE else [chess.B8, chess.G8]
            for square in knight_squares:
                piece = board.piece_at(square)
                if not piece or piece.piece_type != chess.KNIGHT or piece.color != color:
                    # Knight has moved from starting square
                    score += 10 * sign

            # Bishop development
            bishop_squares = [chess.C1, chess.F1] if color == chess.WHITE else [chess.C8, chess.F8]
            for square in bishop_squares:
                piece = board.piece_at(square)
                if not piece or piece.piece_type != chess.BISHOP or piece.color != color:
                    # Bishop has moved from starting square
                    score += 10 * sign

        return score

    @staticmethod
    def _evaluate_castling(board):
        """Evaluate castling"""
        score = 0

        # Check if castled
        for color in [chess.WHITE, chess.BLACK]:
            sign = 1 if color == chess.WHITE else -1
            king_square = board.king(color)

            # Castled kingside or queenside
            if (color == chess.WHITE and king_square in [chess.G1, chess.C1]) or (color == chess.BLACK and king_square in [chess.G8, chess.C8]):
                score += 30 * sign

            # Penalty for lost castling rights if not castled yet
            if not board.has_castling_rights(color) and ((color == chess.WHITE and king_square == chess.E1) or (color == chess.BLACK and king_square == chess.E8)):
                score -= 20 * sign

        return score

    @staticmethod
    def _evaluate_piece_efficiency(board):
        """Evaluate piece movement efficiency"""
        score = 0

        # This requires move history analysis
        # For simplicity, just check if minor pieces are on good squares

        # Knights are better in center
        for color in [chess.WHITE, chess.BLACK]:
            sign = 1 if color == chess.WHITE else -1
            for square in board.pieces(chess.KNIGHT, color):
                file = chess.square_file(square)
                rank = chess.square_rank(square)

                # Distance from center
                file_distance = abs(file - 3.5)
                rank_distance = abs(rank - 3.5)
                distance = file_distance + rank_distance

                # Closer to center is better
                score += (4 - distance) * 2 * sign

        # Bishops are better on long diagonals
        for color in [chess.WHITE, chess.BLACK]:
            sign = 1 if color == chess.WHITE else -1
            for square in board.pieces(chess.BISHOP, color):
                # Check if on major diagonal
                file = chess.square_file(square)
                rank = chess.square_rank(square)

                # Major diagonals
                if abs(file - rank) == 0 or abs(file - (7 - rank)) == 0:
                    score += 5 * sign

        return score

    @staticmethod
    def _evaluate_queen_development(board):
        """Evaluate queen development"""
        score = 0

        # Penalty for early queen development
        move_count = len(board.move_stack) // 2
        if move_count < 6:  # Early game
            for color in [chess.WHITE, chess.BLACK]:
                sign = 1 if color == chess.WHITE else -1
                queen_squares = [chess.D1] if color == chess.WHITE else [chess.D8]

                for square in board.pieces(chess.QUEEN, color):
                    if square not in queen_squares:
                        # Queen has moved from starting square
                        score -= 15 * sign

        return score
