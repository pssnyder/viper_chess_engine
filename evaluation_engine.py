# evaluation_engine.py
# Pure rule-based chess evaluation engine with minimax and alpha-beta pruning

import chess
import yaml

class PieceSquareTables:
    PST_KNIGHT = [
        -50,-40,-30,-30,-30,-30,-40,-50,
        -40,-20,  0,  0,  0,  0,-20,-40,
        -30,  0, 10, 15, 15, 10,  0,-30,
        -30,  5, 15, 20, 20, 15,  5,-30,
        -30,  0, 15, 20, 20, 15,  0,-30,
        -30,  5, 10, 15, 15, 10,  5,-30,
        -40,-20,  0,  5,  5,  0,-20,-40,
        -50,-40,-30,-30,-30,-30,-40,-50
    ]
    
    def get_value(self, piece_type, square, color):
        if piece_type == chess.KNIGHT:
            table = self.PST_KNIGHT
            return table[square] if color == chess.WHITE else -table[square^56]
        # Add tables for other pieces
        return 0
    
class EvaluationEngine:
    def __init__(self, board, depth=3):
        self.board = board.copy()  # Always work with a copy
        self.depth = depth
        self.piece_values = {
            chess.KING: 0,      # King has no material value (handled in king safety)
            chess.QUEEN: 9,
            chess.ROOK: 5,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3,
            chess.PAWN: 1
        }
        
        # Cache for performance
        self._position_cache = {}
        
        # Load configuration
        with open("config.yaml") as f:
            self.config = yaml.safe_load(f)
            
    def evaluate_position(self):
        """Calculate position evaluation from white's perspective"""
        white_score = self._calculate_score(chess.WHITE)
        black_score = self._calculate_score(chess.BLACK)
        return white_score - black_score

    def evaluate_move(self, move):
        """Quick evaluation of individual move"""
        self.board.push(move)
        score = self.evaluate_position()
        self.board.pop()
        return score

    def evaluate_position_with_lookahead(self):
        """Optimized search with reduced depth and transposition table"""
        # Use dynamic depth based on config
        return self._minimax_optimized(self.config['ai']['search_depth'], -float('inf'), float('inf'), self.board.turn == chess.WHITE)

    def _minimax_optimized(self, depth, alpha, beta, maximizing_player):
        """Optimized minimax with better move ordering"""
        # Check transposition table first
        position_key = hash(self.board.fen())
        if position_key in self._position_cache and depth <= 2:
            return self._position_cache[position_key]
        
        # Terminal conditions
        if depth == 0 or self.board.is_game_over():
            score = self._calculate_score(chess.WHITE) - self._calculate_score(chess.BLACK)
            self._position_cache[position_key] = score
            return score
        
        # Get moves and order them better
        moves = list(self.board.legal_moves)
        ordered_moves = self._order_moves(moves)  # Improved ordering
        
        if maximizing_player:
            max_eval = -float('inf')
            for move in ordered_moves:
                self.board.push(move)
                eval_score = self._minimax_optimized(depth - 1, alpha, beta, False)
                self.board.pop()
                
                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break  # Alpha-beta pruning
            return max_eval
        else:
            min_eval = float('inf')
            for move in moves:
                self.board.push(move)
                eval_score = self._minimax_optimized(depth - 1, alpha, beta, True)
                self.board.pop()
                
                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval

    def quiescence_search(self, alpha, beta):
        stand_pat = self.evaluate_position()
        if stand_pat >= beta: return beta
        alpha = max(alpha, stand_pat)
        
        for move in self._order_moves([m for m in self.board.legal_moves 
                                    if self.board.is_capture(m)]):
            self.board.push(move)
            score = -self.quiescence_search(-beta, -alpha)
            self.board.pop()
            
            if score >= beta: return beta
            if score > alpha: alpha = score
        return alpha

    def _order_moves(self, moves):
        """Order moves for better alpha-beta pruning performance"""
        captures = []
        checks = []
        others = []
        
        for move in moves:
            if self.board.is_capture(move):
                captures.append(move)
            else:
                self.board.push(move)
                if self.board.is_check():
                    checks.append(move)
                else:
                    others.append(move)
                self.board.pop()
        
        # Order: captures first, then checks, then other moves
        return captures + checks + others

    def _calculate_score(self, color):
        """SIMPLIFIED scoring - only 5 core components"""
        score = 0
        
        # 1. Material (60% of evaluation)
        score += 1.0 * self._material_score(color)
        
        # 2. Opening principles (30% of evaluation) - FIXES Nh6/Rg1
        score += 1.5 * self._opening_principles_strict(color)
        
        # 3. Castling protection (20% of evaluation) - FIXES castling loss
        score += 1.0 * self._castling_protection(color)
        
        # 4. Center control (10% of evaluation)
        score += 0.5 * self._center_control(color)
        
        # 5. Piece activity (10% of evaluation)
        score += 0.3 * self._piece_activity(color)
        
        return score

    def _positional_evaluation(self, color):
        """Calculate positional factors"""
        score = 0
        score += self._center_control(color)
        score += self._castling_rights(color)
        score += self._king_safety(color)
        score += self._piece_development(color)
        score += self._rook_development(color)
        score += self._piece_activity(color)
        score += self._pawn_advancement(color)
        return score

    def _tactical_evaluation(self, color):
        """Calculate tactical factors"""
        score = 0
        score += self._checkmate_threats()
        score += self._king_attack()
        score += self._king_threat()
        score += self._king_in_check()
        score += self._winning_material()
        score += self._hanging_pieces()
        score += self._losing_material()
        score += self._trapped_pieces()
        score += self._en_passant()
        score += self._pawn_promotion()
        score += self._knight_pair()
        score += self._bishop_vision()
        score += self._knight_vision(color)
        score += self._passed_pawns()
        score += self._repeating_positions()
        return score
    # ==================== OPENING PRINCIPLES ====================
    
    def _opening_principles_strict(self, color):
        """STRONG opening principles - prevents Nh6, Rg1, etc."""
        if self.board.fullmove_number > 15:  # Only in opening
            return 0
            
        score = 0
        
        # CRITICAL: Heavy penalty for knights on rim
        rim_squares = {0, 1, 6, 7, 8, 15, 48, 55, 56, 57, 62, 63}
        for square in self.board.pieces(chess.KNIGHT, color):
            if square in rim_squares:
                score -= 5.0  # INCREASED from -1.5 to -5.0
        
        # CRITICAL: Heavy penalty for early rook moves
        if color == chess.WHITE:
            starting_rooks = {0, 7}  # a1, h1
            for square in starting_rooks:
                piece = self.board.piece_at(square)
                if not (piece and piece.piece_type == chess.ROOK and piece.color == chess.WHITE):
                    if self.board.fullmove_number < 8:  # Very early
                        score -= 4.0  # Heavy penalty for early rook development
        
        # Bonus for proper development
        proper_knight_squares = {42, 43, 44, 45}  # f3, g3, f6, g6 area
        for square in self.board.pieces(chess.KNIGHT, color):
            if square in proper_knight_squares:
                score += 2.0
        
        return score

    # ==================== MATERIAL EVALUATION ====================

    def _material_score(self, color):
        """Simple material count for given color"""
        return sum(len(self.board.pieces(p, color)) * v for p, v in self.piece_values.items())

    def _material_evaluation(self):
        """Enhanced material evaluation with game phase awareness"""
        phase = self._game_phase()
        score = 0.0
        
        # Phase-based piece values (opening, endgame)
        PIECE_VALUES = {
            chess.PAWN: (1.0, 1.2),
            chess.KNIGHT: (3.0, 3.2),
            chess.BISHOP: (3.2, 3.3),
            chess.ROOK: (5.0, 5.5),
            chess.QUEEN: (9.0, 9.5),
            chess.KING: (0, 4.0)  # King becomes more active in endgame
        }
        
        for piece_type in PIECE_VALUES:
            opening_val, endgame_val = PIECE_VALUES[piece_type]
            piece_value = opening_val * (1 - phase) + endgame_val * phase
            
            white_count = len(self.board.pieces(piece_type, chess.WHITE))
            black_count = len(self.board.pieces(piece_type, chess.BLACK))
            score += (white_count - black_count) * piece_value
        
        return score if self.board.turn == chess.WHITE else -score

    def _game_phase(self):
        """Calculate game phase (0 = opening, 1 = endgame)"""
        non_pawn_material = 0
        for piece in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            non_pawn_material += len(self.board.pieces(piece, chess.WHITE))
            non_pawn_material += len(self.board.pieces(piece, chess.BLACK))
        
        # Normalize to 0-1 range (max 14 non-pawn pieces per side = 28 total)
        return 1.0 - min(non_pawn_material / 28, 1.0)

    # ==================== STATIC EXCHANGE EVALUATION ====================

    def static_exchange_evaluation(self, move):
        """Evaluate capture sequences using SEE - FIXED with null checks"""
        if not self.board.is_capture(move):
            return 0

        # Null checks for attacker and victim
        victim = self.board.piece_at(move.to_square)
        attacker = self.board.piece_at(move.from_square)
        if victim is None or attacker is None:
            return 0

        gain = [self.piece_values[victim.piece_type]]
        board_copy = self.board.copy()
        color = board_copy.turn
        board_copy.push(move)

        while True:
            attackers = board_copy.attackers(not color, move.to_square)
            if not attackers:
                break

            # Find least valuable attacker
            least_valuable = min(attackers,
                            key=lambda sq: self.piece_values.get(
                                board_copy.piece_at(sq).piece_type if board_copy.piece_at(sq) else chess.KING, 0))

            captured_piece = board_copy.piece_at(move.to_square)
            if captured_piece:
                gain.append(self.piece_values[captured_piece.piece_type])

            recapture = chess.Move(least_valuable, move.to_square)
            if recapture in board_copy.legal_moves:
                board_copy.push(recapture)
                color = not color
            else:
                break

        # Calculate final score using minimax
        while len(gain) > 1:
            gain[-2] = max(0, gain[-1] - gain[-2])
            gain.pop()

        return gain[0] if gain else 0


    # ==================== TACTICAL RULES ====================

    def _checkmate_threats(self):
        """Detect checkmate in 1 moves"""
        score = 0
        for move in self.board.legal_moves:
            self.board.push(move)
            if self.board.is_checkmate():
                score += self.config['evaluation']['checkmate_bonus'] if self.board.turn == chess.BLACK else -self.config['evaluation']['checkmate_bonus']
            self.board.pop()
        return score

    def _king_attack(self):
        """Bonus for giving check"""
        score = 0
        for move in self.board.legal_moves:
            self.board.push(move)
            if self.board.is_check():
                score += self.config['evaluation']['check_bonus']
            self.board.pop()
        return score

    def _king_threat(self):
        """Penalty for being under check threat"""
        score = 0
        # Switch turns to check opponent's threats
        temp_board = self.board.copy()
        temp_board.turn = not self.board.turn
        for move in temp_board.legal_moves:
            temp_board.push(move)
            if temp_board.is_check():
                score += self.config['evaluation']['king_threat_penalty']
                break
            temp_board.pop()
        return score

    def _king_in_check(self):
        """Penalty for being in check"""
        return self.config['evaluation']['in_check_penalty'] if self.board.is_check() else 0

    def _winning_material(self):
        """Bonus for capturing higher-value pieces"""
        score = 0
        for move in self.board.legal_moves:
            if self.board.is_capture(move):
                attacker = self.board.piece_at(move.from_square)
                victim = self.board.piece_at(move.to_square)
                if victim and self.piece_values[victim.piece_type] > self.piece_values[attacker.piece_type]:
                    score += (self.piece_values[victim.piece_type] - self.piece_values[attacker.piece_type])
        return score

    def _hanging_pieces(self):
        """Bonus for attacking undefended pieces"""
        score = 0
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color != self.board.turn:
                attackers = self.board.attackers(self.board.turn, square)
                defenders = self.board.attackers(not self.board.turn, square)
                if attackers and not defenders:
                    score += self.config['evaluation']['hanging_piece_bonus']
        return score

    def _losing_material(self):
        """Penalty for bad trades"""
        score = 0
        for move in self.board.legal_moves:
            if self.board.is_capture(move):
                see_score = self.static_exchange_evaluation(move)
                if see_score < 0:
                    score += see_score  # Negative penalty
        return score

    def _trapped_pieces(self):
        """Penalty for pieces with no good moves"""
        score = 0
        legal_moves = list(self.board.legal_moves)
        
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn and piece.piece_type != chess.KING:
                piece_moves = [m for m in legal_moves if m.from_square == square]
                if not piece_moves or all(self.board.is_capture(m) for m in piece_moves):
                    score -= self.config['evaluation']['trapped_piece_penalty']
        return score

    # ==================== POSITIONAL RULES ====================

    def _center_control(self, color):
        """Simple center control evaluation"""
        score = 0
        center_squares = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center_squares:
            piece = self.board.piece_at(square)
            if piece and piece.color == color:
                score += self.config['evaluation']['center_control_bonus']
        return score

    def _castling_rights(self, color):
        """Bonus for having castling rights"""
        return self.config['evaluation']['castling_bonus'] if self.board.has_castling_rights(color) else 0

    def _king_safety(self, color):
        """Evaluate king safety with pawn shield"""
        score = 0
        king_square = self.board.king(color)
        
        if king_square is None:
            return score
        
        # Pawn shield evaluation
        direction = 1 if color == chess.WHITE else -1
        king_file = chess.square_file(king_square)
        king_rank = chess.square_rank(king_square)
        
        # Check for pawn shield
        for file_offset in [-1, 0, 1]:
            shield_file = king_file + file_offset
            if 0 <= shield_file <= 7:
                shield_rank = king_rank + direction
                if 0 <= shield_rank <= 7:
                    shield_square = chess.square(shield_file, shield_rank)
                    piece = self.board.piece_at(shield_square)
                    if piece and piece.piece_type == chess.PAWN and piece.color == color:
                        score += self.config['evaluation']['king_safety_bonus']
        
        return score

    def _piece_development(self, color):
        score = 0
        # Penalize knights on rim
        rim_squares = [0,1,6,7,8,15,48,55,56,57,62,63]
        for sq in self.board.pieces(chess.KNIGHT, color):
            score += self.config['evaluation']['piece_development_penalty'] if sq in rim_squares else self.config['evaluation']['piece_development_bonus']
            
        # Bonus for castling rights
        score += self.config['evaluation']['piece_development_bonus'] * self.board.has_castling_rights(color)
        return score


    def _piece_activity(self, color):
        """Simple piece activity evaluation"""
        score = 0
        for square in self.board.pieces(chess.KNIGHT, color):
            score += len(self.board.attacks(square)) * self.config['evaluation']['piece_activity_bonus']
        for square in self.board.pieces(chess.BISHOP, color):
            score += len(self.board.attacks(square)) * self.config['evaluation']['piece_activity_bonus']
        return score

    # ==================== SPECIAL RULES ====================

    def _en_passant(self):
        """Bonus for en passant opportunity"""
        return self.config['evaluation']['en_passant_bonus'] if self.board.ep_square else 0

    def _pawn_promotion(self):
        """Bonus for pawn promotion threats"""
        score = 0
        for move in self.board.legal_moves:
            if move.promotion:
                score += self.config['evaluation']['pawn_promotion_bonus']
        return score

    def _knight_pair(self):
        """Bonus for having both knights"""
        knights = len(self.board.pieces(chess.KNIGHT, self.board.turn))
        return self.config['evaluation']['knight_pair_bonus'] if knights >= 2 else 0

    def _bishop_vision(self):
        """Bonus for bishops with good scope"""
        score = 0
        for square in self.board.pieces(chess.BISHOP, self.board.turn):
            if len(self.board.attacks(square)) > 3:
                score += self.config['evaluation']['bishop_vision_bonus']
        return score

    def _passed_pawns(self):
        """Bonus for passed pawns"""
        score = 0
        for square in self.board.pieces(chess.PAWN, self.board.turn):
            if self._is_passed_pawn(square, self.board.turn):
                score += self.config['evaluation']['passed_pawn_bonus']
        return score

    def _is_passed_pawn(self, square, color):
        """Check if pawn is passed"""
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        direction = 1 if color == chess.WHITE else -1
        
        # Check for opposing pawns blocking or controlling the path
        for check_file in [file - 1, file, file + 1]:
            if 0 <= check_file <= 7:
                for check_rank in range(rank + direction, 8 if color == chess.WHITE else -1, direction):
                    if 0 <= check_rank <= 7:
                        check_square = chess.square(check_file, check_rank)
                        piece = self.board.piece_at(check_square)
                        if piece and piece.piece_type == chess.PAWN and piece.color != color:
                            return False
        return True

    def _repeating_positions(self):
        """Penalty for threefold repetition"""
        return self.config['evaluation']['repeating_penalty'] if self.board.is_repetition(count=2) else 0
    
    def _knight_vision(self, color):
        """Penalize knights with limited mobility"""
        penalty = 0
        max_mobility = 8  # Maximum possible knight moves
        for square in self.board.pieces(chess.KNIGHT, color):
            mobility = len(self.board.attacks(square))
            missing_squares = max_mobility - mobility
            penalty += missing_squares * self.config['evaluation']['knight_vision_penalty']
        return penalty
    
    def _pawn_advancement(self, color):
        """Reward advancing central pawns"""
        bonus = 0
        central_files = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in self.board.pieces(chess.PAWN, color):
            rank = chess.square_rank(square)
            file = chess.square_file(square)
            # Bonus for central pawn advancement
            if file in [3, 4]:  # d/e files
                bonus += (rank - 1) * self.config['evaluation']['pawn_advancement_bonus']
        return bonus

    def _rook_development(self, color):
        """Penalty for undeveloped rooks"""
        penalty = 0
        starting_rook_squares = [chess.A1, chess.H1] if color == chess.WHITE else [chess.A8, chess.H8]
        
        for square in starting_rook_squares:
            piece = self.board.piece_at(square)
            if not self.board.has_castling_rights(color) and piece and piece.piece_type == chess.ROOK and piece.color == color:
                penalty += self.config['evaluation']['rook_development_penalty']
        return penalty

    def _castling_protection(self, color):
        """Strong castling protection - prevents losing castling rights"""
        score = 0
        
        # Large bonus for having castling rights
        if self.board.has_kingside_castling_rights(color):
            score += self.config['evaluation']['castling_protection_bonus']  # INCREASED from current bonus
        if self.board.has_queenside_castling_rights(color):
            score += self.config['evaluation']['castling_protection_bonus']
        
        # HUGE bonus for completed castling
        king_square = self.board.king(color)
        if color == chess.WHITE:
            if king_square in {2, 6}:  # g1 or c1 (castled)
                score += self.config['evaluation']['castling_bonus']
        else:
            if king_square in {58, 62}:  # g8 or c8 (castled)
                score += self.config['evaluation']['castling_bonus']
        
        # Penalty for king moves that lose castling
        if not self.board.has_castling_rights(color) and self.board.fullmove_number < 10:
            score += self.config['evaluation']['castling_protection_penalty'] # Heavy penalty for early loss of castling
        
        return score