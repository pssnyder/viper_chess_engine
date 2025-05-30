# evaluation_engine.py
import chess

class EvaluationEngine:
    # Set depth for eval
    def __init__(self, board, depth=3):
        self.board = board
        self.depth = depth
        self.piece_values = {
            chess.KING: 10,
            chess.QUEEN: 9,
            chess.ROOK: 5,
            chess.BISHOP: 3,
            chess.KNIGHT: 3,
            chess.PAWN: 1
        }
    
    # Rules
        # _checkmate_threats()
        # _material_score() [simple]
        # _material_evaluation() [enhanced]
        # _positional_evaluation()
        # _center_control()
        # _castling_rights()
        # _king_safety()
        # _en_passant()
        # _pawn_promotion()
        # _king_attack()
        # _king_threat()
        # _king_in_check()
        # _winning_material
        # _hanging_pieces
        # _losing_material()
        # _trapped_pieces()
        # _piece_development()
        # _knight_pair()
    
    def evaluate_position(self):
        # Calculate from both perspectives
        white_score = self._calculate_score(chess.WHITE)
        black_score = self._calculate_score(chess.BLACK)
        return white_score - black_score  # Net score favoring white
    
    def evaluate_move(self, move):
        """Quick evaluation of individual move"""
        self.board.push(move)
        score = self.evaluate_position()
        self.board.pop()
        return score

    def evaluate_position_with_lookahead(self):
        return self._minimax(self.depth, -float('inf'), float('inf'), True)

    def _minimax(self, depth, alpha, beta, maximizing_player):
        board = self.board.copy()  # Use copy instead of original
        if depth == 0 or self.board.is_game_over():
            return self.evaluate_position()
        
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
            for move in board.legal_moves:
                board.push(move)
                eval = self._minimax(depth-1, alpha, beta, True)
                board.pop()
                min_eval = min(min_eval, eval)
                beta = min(beta, eval)
                if beta <= alpha:
                    break
            return min_eval
    
    def _calculate_score(self, color):
        score = 0
        score += self._checkmate_threats()
        score += self._material_score(color)
        score += self._material_evaluation()
        score += self._center_control()
        score += self._castling_rights(color)
        score += self._king_safety(color)
        score += self._en_passant()
        score += self._pawn_promotion()
        score += self._king_attack()
        score += self._king_threat()
        score += self._king_in_check()
        score += self._winning_material()
        score += self._hanging_pieces()
        score += self._losing_material()
        score += self._trapped_pieces()
        score += self._piece_development()
        score += self._knight_pair()
        score += self._repeating_positions()
        score += self._piece_activity(color)
        return score
    
    # Piece Value Calculation
    # -----------------------
    
    # Simple Piece Values
    def _material_score(self, color):
        values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3.25,
            chess.ROOK: 5,
            chess.QUEEN: 9,
            chess.KING: 0  # King value handled in king safety
        }
        return sum(len(self.board.pieces(p, color)) * v for p, v in values.items())
    
    # Enhanced Piece Values
    def _material_evaluation(self):
        """Calculate material advantage with phase-based piece values"""
        phase = self._game_phase()
        score = 0.0
        
        # Define piece values (opening, endgame)
        PIECE_VALUES = {
            chess.PAWN: (1.0, 1.2),
            chess.KNIGHT: (3.0, 3.2),
            chess.BISHOP: (3.2, 3.3),
            chess.ROOK: (5.0, 5.5),
            chess.QUEEN: (9.0, 9.5),
            chess.KING: (0, 4.0)  # Increased value in endgame
        }

        for piece_type in PIECE_VALUES:
            opening_val, endgame_val = PIECE_VALUES[piece_type]
            
            # Interpolate value based on game phase
            piece_value = opening_val * (1 - phase) + endgame_val * phase
            
            # Calculate material difference
            white_count = len(self.board.pieces(piece_type, chess.WHITE))
            black_count = len(self.board.pieces(piece_type, chess.BLACK))
            score += (white_count - black_count) * piece_value

        # Adjust score for current player's perspective
        return score if self.board.turn == chess.WHITE else -score
    
    # Helper function for material eval
    def _game_phase(self):
        """Calculate game phase (0 = opening, 1 = endgame) based on remaining material"""
        # Count non-pawn material for both sides
        non_pawn_material = 0
        for piece in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            non_pawn_material += len(self.board.pieces(piece, chess.WHITE))
            non_pawn_material += len(self.board.pieces(piece, chess.BLACK))
        
        # Normalize to 0-1 range (assuming max 32 non-pawn pieces in initial position)
        phase = 1.0 - min(non_pawn_material / 32, 1.0)
        return phase

    # Helper function for piece exchange calculation
    def static_exchange_evaluation(self, move):
        """Quickly evaluate capture profitability"""
        if not self.board.is_capture(move):
            return 0
        
        gain = [self.piece_values[self.board.piece_at(move.to_square).piece_type]]
        board = self.board.copy()
        attacker = board.piece_at(move.from_square).piece_type
        color = board.turn
        board.push(move)
        
        while True:
            defender = board.attackers(not color, move.to_square)
            if not defender:
                break
            defender = min(defender, key=lambda sq: self.piece_values[board.piece_at(sq).piece_type])
            gain.append(self.piece_values[board.piece_at(defender).piece_type])
            board.push(chess.Move(defender, move.to_square))
            color = not color
        
        total = 0
        while gain:
            total = gain.pop() - total
            if total < 0:
                break
        return max(total, 0)

    # Rule Implementation
    # -------------------
    
    # Rule: IF there is a mate in 1 scenario on the board THEN add 1000 to the eval FOR allowing the AI to properly win if there is a Checkmate scenario available.
    def _checkmate_threats(self):
        score = 0
        
        for move in self.board.legal_moves:
            self.board.push(move)
            if self.board.is_checkmate():
                score += 1000 if self.board.turn else -1000
            self.board.pop()
        return score

    # Rule: IF a piece controls (is on or can attack) the center squares of the board THEN add 1 point to the evaluation score FOR good board control.
    def _center_control(self):
        score = 0
        center = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center:
            if self.board.piece_at(square) and self.board.piece_at(square).color == self.board.turn:
                score += 1
        return score
    
    #Rule: IF the King and at least one Rook have not moved and the squares between them are clear of pieces and are not under attack from an opposing piece THEN add 3 points to the eval FOR being able to castle.
    def _castling_rights(self,color):
        """Castling rights and pawn shield"""
        score = 0
        if self.board.has_castling_rights(color):
            score += 2
        return score
    
    # Rule: IF there are pawns directly in front of the king THEN add 0.5 to the evaluation for each pawn present in front of the king FOR having pawns shielding the king from attack
    def _king_safety(self, color):
        score = 0
        king = self.board.king(color)
        if king is None:  # Should never happen, but safety check
            return score
        
        # Pawn shield evaluation
        direction = 1 if color == chess.WHITE else -1
        shield_squares = [
            king + 8 * direction + delta
            for delta in [-1, 0, 1]
            if 0 <= king + 8 * direction + delta < 64  # Add bounds check
        ]
        
        for shield in shield_squares:
            if shield in chess.SQUARES:  # Validate square index
                piece = self.board.piece_at(shield)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    score += 0.5
        return score


    # Rule: IF an opposing pawn last moved two squares forward and is on the same rank as a players pawn THEN add 1 point FOR being able to capture en passant.
    def _en_passant(self):
        score = 0
        if self.board.ep_square:
            score += 1
        return score
    
    # Rule: IF a pawn is on the 7th rank AND the pawn can move to the 8th rank THEN add 5 points to the evaluation score FOR being able to promote.
    def _pawn_promotion(self):
        score = 0
        for move in self.board.legal_moves:
            if move.promotion:
                score += 5
        return score

    # Rule: IF a piece has a legal move that checks the opposing King THEN add 10 points to the evaluation score FOR check threats.
    def _king_attack(self):
        score = 0
        # Current player's check threats
        for move in self.board.legal_moves:
            self.board.push(move)
            if self.board.is_check():
                score += 10
            self.board.pop()
        return score
    
    # Rule: IF an opposing piece can check the King on the next move THEN subtract 5 points FOR a check threat.
    def _king_threat(self):
        score = 0
        # Opponent's next-move check threats
        temp_board = self.board.copy()
        temp_board.turn = not self.board.turn
        if temp_board.is_check():
            score -= 5
        return score

    # Rule: IF the King is in check THEN subtract 10 points to the evaluation score FOR being in check.
    def _king_in_check(self):
        score = 0
        # Player king in check
        if self.board.is_check():
            score -= 10
        return score
    
    # Rule: IF an opposing piece can be captured AND the piece being attacked is more valuable THEN add 3 points to the evaluation score plus the difference in piece value FOR an available material win.
    def _winning_material(self):
        score = 0
        # Capturing higher-value pieces
        for move in self.board.legal_moves:
            if self.board.is_capture(move):
                attacker = self.board.piece_at(move.from_square)
                victim = self.board.piece_at(move.to_square)
                if victim and self.piece_values[victim.piece_type] > self.piece_values[attacker.piece_type]:
                    # Immediate material gain + positional bonus
                    score += 3 + (self.piece_values[victim.piece_type] - self.piece_values[attacker.piece_type])
        return score
    
    # Rule: IF an opposing piece can be attacked and has no defending pieces THEN add 2 to the evaluation FOR a being able to attack a hanging piece.
    def _hanging_pieces(self):
        score = 0
        # Hanging pieces
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                attackers = self.board.attackers(self.board.turn, square)
                defenders = self.board.attackers(not self.board.turn, square)

                if not defenders and attackers:
                    score += 2
        return score

    # Rule: IF a piece is being attacked by a piece with a lower value and has no defending pieces THEN subtract 3 points from the eval minus the difference in piece value FOR an available material loss.
    def _losing_material(self):
        score = 0
        # Losing trade exchanges
        for move in self.board.legal_moves:
            if self.board.is_capture(move):
                attacker = self.board.piece_at(move.from_square)
                victim = self.board.piece_at(move.to_square)
                if victim and self.piece_values[victim.piece_type] < self.piece_values[attacker.piece_type]:
                    score -= 3 - (self.piece_values[attacker.piece_type] - self.piece_values[victim.piece_type])
        return score
    
    # Rule: IF a piece has no legal squares to move to or all legal moves would result in a capture THEN subtract 5 points from the eval FOR a trapped piece.
    def _trapped_pieces(self):
        score = 0
        legal_moves = list(self.board.legal_moves)
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                moves = [m for m in legal_moves if m.from_square == square]
                if not moves or all(self.board.is_capture(m) for m in moves):
                    score -= 5
        return score

    # Rule: IF both Bishops and both Knights have been moved from their starting squares THEN add 2 points to the eval FOR having all minor pieces developed.
    def _piece_development(self):
        bishops = knights = 0
        start_bishops = [chess.B1, chess.G1] if self.board.turn == chess.WHITE else [chess.B8, chess.G8]
        start_knights = [chess.B1, chess.G1] if self.board.turn == chess.WHITE else [chess.B8, chess.G8]
        
        for sq in start_bishops:
            if self.board.piece_at(sq) != chess.Piece(chess.BISHOP, self.board.turn):
                bishops += 1
        for sq in start_knights:
            if self.board.piece_at(sq) != chess.Piece(chess.KNIGHT, self.board.turn):
                knights += 1
                
        return 2 if bishops >= 2 and knights >= 2 else 0

    # Rule: IF both Knights are still in play THEN add 1 point to each Knight piece’s value FOR having a Knight pair.
    def _knight_pair(self):
        modifier = 0
        knights = []
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                if piece.piece_type == chess.KNIGHT:
                    knights.append(square)
                    
        if len(knights) >= 2:
            modifier += len(knights)
        return modifier

    # Rule: IF a Bishop controls more than 3 squares THEN add 1 point to that Bishop’s piece value FOR having good board coverage.
    def _bishiop_vision(self):
        modifier = 0
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                if piece.piece_type == chess.BISHOP:
                    if len(self.board.attacks(square)) > 3:
                        modifier += 1
        return modifier
    
    # Rule: IF a pawn has no opposing pawns in either of its adjacent files THEN add 1 point to that pawn’s piece value FOR it being a passed pawn.
    def _passed_pawns(self):
        modifier = 0
        
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                if piece.piece_type == chess.PAWN and self._is_passed_pawn(square):
                    modifier += 1
            
        return modifier
    
    # Helper function for _passed_pawns
    def _is_passed_pawn(self, square):
        pawn = self.board.piece_at(square)
        if pawn.piece_type != chess.PAWN:
            return False
            
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        color = pawn.color
        direction = 1 if color == chess.WHITE else -1
        
        # Check opposing pawns in front
        for f in [file-1, file, file+1]:
            if 0 <= f <= 7:
                for r in range(rank + direction, 7 if color == chess.WHITE else 0, direction):
                    target = chess.square(f, r)
                    opp_pawn = self.board.piece_at(target)
                    if opp_pawn and opp_pawn.piece_type == chess.PAWN and opp_pawn.color != color:
                        return False
        return True

    # Rule: IF a legal move would result in a three-fold repetition THEN subtract 100 from the evaluation FOR discouraging draws.
    def _repeating_positions(self):
        score = 0
        
        # Penalize repeating positions
        if self.board.is_repetition(count=2):
            score -= 100  # Strong penalty to prevent draw by repetition
        
        return score
    
    # Rule: IF the Knights and/or Bishops are able to attack an opposing piece THEN add 0.1 for every piece attacked by a Knight and 0.15 for every piece attacked by a Bishop FOR having active minor pieces.         
    def _piece_activity(self, color):
        """Mobility and attack patterns"""
        score = 0
        for square in self.board.pieces(chess.KNIGHT, color):
            score += len(self.board.attacks(square)) * 0.1
        for square in self.board.pieces(chess.BISHOP, color):
            score += len(self.board.attacks(square)) * 0.15
        return score