# improved_evaluation_engine.py

import chess
import yaml
from piece_square_tables import PieceSquareTables

class ImprovedEvaluationEngine:
    def __init__(self, board, depth):
        self.board = board.copy()
        self.depth = depth

        self.piece_values = {
            chess.KING: 0.0,
            chess.QUEEN: 9.0,
            chess.ROOK: 5.0,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3.0,
            chess.PAWN: 1.0
        }

        # Initialize piece-square tables
        self.pst = PieceSquareTables()

        # Cache for performance
        self._position_cache = {}

        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)

    def evaluate_position(self):
        """Calculate position evaluation from white's perspective (UNCHANGED)"""
        white_score = self._calculate_score(chess.WHITE)
        black_score = self._calculate_score(chess.BLACK)
        return white_score - black_score

    def evaluate_position_from_perspective(self, player_color):
        """NEW: Calculate position evaluation from specified player's perspective"""
        white_score = self._calculate_score(chess.WHITE)
        black_score = self._calculate_score(chess.BLACK)
        
        if player_color == chess.WHITE:
            return white_score - black_score
        else:
            return black_score - white_score

    def evaluate_position_with_lookahead(self):
        """Minimax with proper perspective handling"""
        return self._minimax(self.depth, -float('inf'), float('inf'), self.board.turn == chess.WHITE)

    
    def evaluate_move(self, move):
        """Quick evaluation of individual move"""
        self.board.push(move)
        score = self.evaluate_position()
        self.board.pop()
        return score


    def _minimax(self, depth, alpha, beta, maximizing_player):
        """Minimax that properly handles perspectives"""
        if depth == 0 or self.board.is_game_over():
            # Always return from White's perspective, then adjust in the calling function
            base_eval = self.evaluate_position()
            return base_eval

        if maximizing_player:
            max_eval = -float('inf')
            for move in self.board.legal_moves:
                self.board.push(move)
                eval = self._minimax(depth-1, alpha, beta, False)
                self.board.pop()
                max_eval = max(max_eval, eval)
                alpha = max(alpha, eval)
                if beta <= alpha:
                    break
            return max_eval
        else:
            min_eval = float('inf')
            for move in self.board.legal_moves:
                self.board.push(move)
                eval = self._minimax(depth-1, alpha, beta, True)
                self.board.pop()
                min_eval = min(min_eval, eval)
                beta = min(beta, eval)
                if beta <= alpha:
                    break
            return min_eval

    def _calculate_score(self, color):
        """IMPROVED scoring with piece-square tables (UNCHANGED)"""
        score = 0.0

        # EVALUATION FUNCTIONS
        score += 1.0 * (self._piece_square_table_evaluation(color) or 0.00)
        score += 1.0 * (self._improved_mobility(color) or 0.00)
        score += 1.0 * (self._tempo_bonus(color) or 0.00)
        score += 1.0 * (self._checkmate_threats() or 0.0)
        score += 1.0 * (self._repeating_positions() or 0.0)
        score += 1.0 * (self._material_score(color) or 0.0)
        score += 1.0 * (self._center_control() or 0.0)
        score += 1.0 * (self._piece_activity(color) or 0.0)
        score += 1.0 * (self._king_safety(color) or 0.0)
        score += 1.0 * (self._king_threat() or 0.0)
        score += 1.0 * (self._undeveloped_pieces(color) or 0.0)
        score += 1.0 * (self._special_moves() or 0.0)
        score += 1.0 * (self._tactical_evaluation() or 0.0)
        score += 1.0 * (self._castling_evaluation() or 0.0)
        score += 1.0 * (self._pawn_structure() or 0.0)
        score += 1.0 * (self._knight_pair() or 0.00)
        score += 1.0 * (self._bishiop_vision() or 0.00)

        return score

    def _piece_square_table_evaluation(self, color):
        pst_score = 0.0

        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == color:
                # Get piece-square table value for this piece on this square
                pst_value = self.pst.get_piece_value(piece.piece_type, square, color)
                pst_score += pst_value / 100.0  # Convert centipawns to pawn units

        # Weight the piece-square table evaluation
        weight = self.config['evaluation']['pst_weight']
        return pst_score * weight

    def _improved_mobility(self, color):
        """
        NEW FUNCTION: Better mobility calculation with safe squares
        """
        mobility_score = 0.0

        for square in self.board.pieces(chess.KNIGHT, color):
            # Count safe moves (not attacked by enemy pawns)
            safe_moves = 0
            for target in self.board.attacks(square):
                if not self._is_attacked_by_pawn(target, not color):
                    safe_moves += 1
            mobility_score += safe_moves * self.config['evaluation']['knight_activity_bonus']

        for square in self.board.pieces(chess.BISHOP, color):
            safe_moves = 0
            for target in self.board.attacks(square):
                if not self._is_attacked_by_pawn(target, not color):
                    safe_moves += 1
            mobility_score += safe_moves * self.config['evaluation']['bishop_activity_bonus']

        return mobility_score

    def _tempo_bonus(self, color):
        if self.board.turn == color:
            return self.config['evaluation']['tempo_bonus']  # Small tempo bonus
        return 0.0

    def _is_attacked_by_pawn(self, square, by_color):
        """Helper function to check if a square is attacked by enemy pawns"""
        if by_color == chess.WHITE:
            # White pawns attack diagonally upward
            pawn_attacks = [square - 7, square - 9]
        else:
            # Black pawns attack diagonally downward
            pawn_attacks = [square + 7, square + 9]

        for attack_square in pawn_attacks:
            if 0 <= attack_square < 64:
                piece = self.board.piece_at(attack_square)
                if piece and piece.piece_type == chess.PAWN and piece.color == by_color:
                    return True
        return False

    def _checkmate_threats(self):
        score = 0.0
        for move in self.board.legal_moves:
            self.board.push(move)
            if self.board.is_checkmate():
                score += self.config['evaluation']['checkmate_bonus'] if self.board.turn else -1.0 * self.config['evaluation']['checkmate_bonus']
            self.board.pop()
        return score

    def _repeating_positions(self):
        score = 0.0
        if self.board.is_repetition(count=2):
            score += self.config['evaluation']['repetition_penalty']
        return score

    def _material_score(self, color):
        """Simple material count for given color"""
        return sum(len(self.board.pieces(p, color)) * v for p, v in self.piece_values.items())

    def _center_control(self):
        """Simple center control"""
        score = 0.0
        center = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center:
            if self.board.piece_at(square) and self.board.piece_at(square).color == self.board.turn:
                score += self.config['evaluation']['center_control_bonus']
        return score

    def _piece_activity(self, color):
        """Mobility and attack patterns"""
        score = 0.0

        for square in self.board.pieces(chess.KNIGHT, color):
            score += len(self.board.attacks(square)) * self.config['evaluation']['knight_activity_bonus']

        for square in self.board.pieces(chess.BISHOP, color):
            score += len(self.board.attacks(square)) * self.config['evaluation']['bishop_activity_bonus']

        return score

    def _king_safety(self, color):
        score = 0.0
        king = self.board.king(color)
        if king is None:
            return score

        direction = 1 if color == chess.WHITE else -1
        shield_squares = [
            king + 8 * direction + delta
            for delta in [-1, 0, 1]
            if 0 <= king + 8 * direction + delta < 64
        ]

        for shield in shield_squares:
            if shield in chess.SQUARES:
                piece = self.board.piece_at(shield)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    score += self.config['evaluation']['king_safety_bonus']

        return score

    def _king_threat(self):
        score = 0.0
        temp_board = self.board.copy()
        temp_board.turn = not self.board.turn

        if temp_board.is_check():
            score += self.config['evaluation']['king_threat_penalty']

        return score

    def _undeveloped_pieces(self, color):
        score = 0.0
        undeveloped = 0.0

        starting_squares = {
            chess.WHITE: [chess.B1, chess.G1, chess.C1, chess.F1],
            chess.BLACK: [chess.B8, chess.G8, chess.C8, chess.F8]
        }

        for square in starting_squares[color]:
            piece = self.board.piece_at(square)
            if piece and piece.color == color and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                undeveloped += 1

        if undeveloped > 0 and self.board.has_castling_rights(color):
            score = undeveloped * self.config['evaluation']['undeveloped_penalty']

        return score

    def _special_moves(self):
        """Evaluate special moves and opportunities"""
        score = 0
        
        # En passant
        if self.board.ep_square:
            score += self.config['evaluation']['en_passant_bonus']
        
        # Promotion opportunities
        for move in self.board.legal_moves:
            if move.promotion:
                score += self.config['evaluation']['pawn_promotion_bonus']
        
        return score

    def _tactical_evaluation(self):
        """Evaluate tactical elements"""
        score = 0
        
        # Captures
        for move in self.board.legal_moves:
            if self.board.is_capture(move):
                score += self.config['evaluation']['capture_bonus']
        
        # Checks
        for move in self.board.legal_moves:
            self.board.push(move)
            if self.board.is_check():
                score += self.config['evaluation']['check_bonus']
            self.board.pop()
        
        return score

    def _castling_evaluation(self):
        """Evaluate castling rights and opportunities"""
        score = 0
        
        if self.board.has_castling_rights(chess.WHITE):
            score += self.config['evaluation']['castling_protection_bonus']
        if self.board.has_castling_rights(chess.BLACK):
            score -= self.config['evaluation']['castling_protection_bonus']
        
        return score

    def _pawn_structure(self):
        """Basic pawn structure evaluation"""
        score = 0
        
        # Check for passed pawns
        for color in [chess.WHITE, chess.BLACK]:
            for square in self.board.pieces(chess.PAWN, color):
                file = chess.square_file(square)
                rank = chess.square_rank(square)
                
                # Simple passed pawn detection
                is_passed = True
                direction = 1 if color == chess.WHITE else -1
                
                # Check if there are opponent pawns blocking or attacking
                for check_rank in range(rank + direction, 8 if color == chess.WHITE else -1, direction):
                    if 0 <= check_rank < 8:
                        for check_file in [file - 1, file, file + 1]:
                            if 0 <= check_file < 8:
                                check_square = chess.square(check_file, check_rank)
                                piece = self.board.piece_at(check_square)
                                if piece and piece.piece_type == chess.PAWN and piece.color != color:
                                    is_passed = False
                                    break
                    if not is_passed:
                        break
                
                if is_passed:
                    passed_bonus = self.config['evaluation']['passed_pawn_bonus']
                    if color == chess.WHITE:
                        score += passed_bonus
                    else:
                        score -= passed_bonus
        
        return score
    
    def _knight_pair(self):
        score = 0
        knights = []
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                if piece.piece_type == chess.KNIGHT:
                    knights.append(square)
                    
        if len(knights) >= 2:
            score += len(knights) * self.config['evaluation']['knight_pair_bonus']
        return score

    def _bishiop_vision(self):
        score = 0
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                if piece.piece_type == chess.BISHOP:
                    if len(self.board.attacks(square)) > 3:
                        score += self.config['evaluation']['bishop_vision_bonus']
        return score