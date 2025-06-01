# evaluation_engine.py

import chess
import yaml
import random
from piece_square_tables import PieceSquareTables
from typing import Optional, Callable, Dict, Any, List, Tuple
from time_manager import TimeManager

class ImprovedEvaluationEngine:
    def __init__(self, board, depth):
        self.board = board.copy()
        self.depth = depth
        self.time_manager = TimeManager()
        self.max_depth = 8
        self.hash_size = 64  # MB
        self.threads = 1
        self.nodes_searched = 0
        self.transposition_table = {}
        self.killer_moves = [[None, None] for _ in range(50)]  # 2 killer moves per ply
        self.history_table = {}
        self.counter_moves = {}
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

    # =================================
    # ======== SCORING HANDLER ========
    
    def _calculate_score(self, color):
        """IMPROVED scoring with piece-square tables (UNCHANGED)"""
        score = 0.0

        # Rules included in scoring
        score += 1.0 * (self._piece_square_table_evaluation(color) or 0.0)
        score += 1.0 * (self._improved_mobility(color) or 0.0)
        score += 1.0 * (self._tempo_bonus(color) or 0.0)
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
        score += 1.0 * (self._knight_pair() or 0.0)
        score += 1.0 * (self._bishiop_vision() or 0.0)
        score += 1.0 * (self._rook_coordination(color) or 0.0)

        return score
    
    # =================================
    # ===== EVALUATION FUNCTIONS ======
    
    def evaluate_position(self):
        """Calculate position evaluation from white's perspective (UNCHANGED)"""
        try:
            white_score = self._calculate_score(chess.WHITE)
            black_score = self._calculate_score(chess.BLACK)
            return white_score - black_score
        except Exception:
            # Fallback to simple material evaluation
            return self._material_score(self.board.turn)

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

    def evaluate_position_with_deepsearch(self):
        if self.config['ai']['move_time_limit'] == 0:
            time_control = {"infinite": True}
        else:
            time_control = {"movetime": self.config['ai']['move_time_limit']}
        return self._search(self.board,time_control,stop_callback=0)
    
    def evaluate_move(self, move):
        """Quick evaluation of individual move"""
        self.board.push(move)
        score = self.evaluate_position()
        self.board.pop()
        return score

    # ===================================
    # ======= HELPER FUNCTIONS ==========
    
    def order_moves(self, board, moves, hash_move=None, depth=0):
        """
        Order moves for better alpha-beta pruning efficiency

        Args:
            board: The current chess board state
            moves: List of legal moves to order
            hash_move: Move from transposition table if available
            depth: Current search depth

        Returns:
            Ordered list of moves
        """
        # Store move scores for later sorting
        move_scores = []

        for move in moves:
            # Calculate score for move
            score = self._score_move(board, move, hash_move, depth)
            move_scores.append((move, score))

        # Sort moves by score in descending order
        move_scores.sort(key=lambda x: x[1], reverse=True)

        # Return just the moves, not the scores
        return [move for move, _ in move_scores]
    
    def new_game(self):
        """Reset engine for new game"""
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.nodes_searched = 0

    def set_max_depth(self, depth: int):
        """Set maximum search depth"""
        self.max_depth = max(1, min(depth, 20))
        self.depth = self.max_depth

    def set_hash_size(self, size_mb: int):
        """Set transposition table size"""
        self.hash_size = max(1, min(size_mb, 1024))
        # Clear table when resizing
        self.transposition_table.clear()

    def set_threads(self, threads: int):
        """Set number of search threads"""
        self.threads = max(1, min(threads, 8))
    
    def _score_move(self, board, move, hash_move, depth):
        """Score a move for ordering"""
        # Base score
        score = 0.0

        # 1. Hash move gets highest priority
        if hash_move and move == hash_move:
            return 10000000

        # 2. Captures scored by MVV-LVA (Most Valuable Victim - Least Valuable Aggressor)
        if board.is_capture(move):
            victim_type = board.piece_at(move.to_square).piece_type
            aggressor_type = board.piece_at(move.from_square).piece_type

            # Most valuable victim (queen=9, rook=5, etc.) minus least valuable aggressor
            victim_value = self.piece_values.get(victim_type, 0)
            aggressor_value = self.piece_values.get(aggressor_type, 0)

            # MVV-LVA formula: 10 * victim_value - aggressor_value
            score = 1000000 + 10 * victim_value - aggressor_value

            # Bonus for promotions
            if move.promotion:
                score += 900000  # High score for promotions

            return score

        # 3. Killer moves (non-capture moves that caused a beta cutoff)
        if depth in self.killer_moves and move in self.killer_moves[depth]:
            return 900000

        # 4. Counter moves (moves that are good responses to the previous move)
        last_move = board.peek() if board.move_stack else None
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            if counter_key in self.counter_moves and self.counter_moves[counter_key] == move:
                return 800000

        # 5. History heuristic (moves that have caused cutoffs in similar positions)
        piece_type = board.piece_at(move.from_square).piece_type
        history_key = (piece_type, move.from_square, move.to_square)
        history_score = self.history_table.get(history_key, 0)

        # 6. Promotions (already handled in captures, but add for non-capture promotions)
        if move.promotion:
            score += 700000

        # 7. Checks
        board.push(move)
        gives_check = board.is_check()
        board.pop()

        if gives_check:
            score += 600000

        # Add history score
        score += history_score

        return score

    def update_killer_move(self, move, depth):
        """Update killer move table with a move that caused a beta cutoff"""
        if depth not in self.killer_moves:
            self.killer_moves[depth] = [move]
        elif move not in self.killer_moves[depth]:
            self.killer_moves[depth].insert(0, move)
            # Keep only the best 2 killer moves per depth
            self.killer_moves[depth] = self.killer_moves[depth][:2]

    def update_history_score(self, board, move, depth):
        """Update history heuristic score for a move that caused a beta cutoff"""
        piece_type = board.piece_at(move.from_square).piece_type
        history_key = (piece_type, move.from_square, move.to_square)

        # Update history score using depth-squared bonus
        self.history_table[history_key] += depth * depth

    def update_counter_move(self, last_move, current_move):
        """Update counter move table"""
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            self.counter_moves[counter_key] = current_move
          
    # =======================================
    # ========== SEARCH ALGORITHMS ==========
    
    def _minimax(self, depth, alpha, beta, maximizing_player):
        """Minimax that properly handles perspectives"""
        if depth == 0 or self.board.is_game_over():
            # Always return from White's perspective, then adjust in the calling function
            base_eval = self.evaluate_position()
            return base_eval
        # Get list of available moves
        legal_moves = list(self.board.legal_moves)
        
        # Ordering of legal moves for faster pruning
        if self.config['ai']['move_ordering']:
            legal_moves = self.order_moves(self.board, legal_moves)
            
        if maximizing_player:
            max_eval = -float('inf')
            for move in legal_moves:
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
            for move in legal_moves:
                self.board.push(move)
                eval = self._minimax(depth-1, alpha, beta, True)
                self.board.pop()
                min_eval = min(min_eval, eval)
                beta = min(beta, eval)
                if beta <= alpha:
                    break
            return min_eval

    def _search(self, board: chess.Board, time_control: Dict[str, Any], 
               stop_callback: Callable[[], bool] = None) -> Optional[chess.Move]:
        """
        Main search function

        Args:
            board: Current position
            time_control: Time control parameters
            stop_callback: Function to check if search should stop

        Returns:
            Best move found
        """
        self.nodes_searched = 0

        # Set up evaluation engine with current board
        self.board = board

        # Allocate time for this move
        allocated_time = self.time_manager.allocate_time(time_control, board)
        self.time_manager.start_timer(allocated_time)

        # Handle special cases
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None

        if len(legal_moves) == 1:
            return legal_moves[0]  # Only one legal move

        # Determine search depth
        max_depth = self.max_depth
        if time_control.get('depth'):
            max_depth = time_control['depth']

        best_move = None
        best_score = float('-inf')

        try:
            # Iterative deepening search
            for depth in range(1, max_depth + 1):
                if stop_callback and stop_callback():
                    break
                if self.time_manager.should_stop(depth, self.nodes_searched):
                    break

                move, score = self._search_depth(board, depth, stop_callback)

                if move:
                    best_move = move
                    best_score = score

                    # Print UCI info
                    elapsed = self.time_manager.time_elapsed()
                    nps = int(self.nodes_searched / max(elapsed, 0.001))

                    print(f"info depth {depth} score cp {int(score * 100)} "
                          f"nodes {self.nodes_searched} time {int(elapsed * 1000)} "
                          f"nps {nps} pv {move.uci()}")

                # Don't continue if we found a mate
                if abs(score) > 900:  # Mate score threshold
                    break

        except Exception as e:
            print(f"info string Search error: {e}")

        return best_score  # Fallback to first legal move

    def _search_depth(self, board: chess.Board, depth: int, 
                    stop_callback: Callable[[], bool] = None) -> Tuple[Optional[chess.Move], float]:
        """
        Search to a specific depth

        Args:
            board: Current position
            depth: Search depth
            stop_callback: Function to check if search should stop

        Returns:
            Tuple of (best_move, best_score)
        """
        alpha = float('-inf')
        beta = float('inf')
        best_move = None
        best_score = float('-inf')

        # Get ordered moves for better alpha-beta pruning
        moves = self.order_moves(board, depth)

        for move in moves:
            if stop_callback and stop_callback():
                break
            if self.time_manager.should_stop(depth, self.nodes_searched):
                break

            board.push(move)
            self.nodes_searched += 1

            # Search the position after this move
            score = -self._negamax(board, depth - 1, -beta, -alpha, stop_callback)

            board.pop()

            if score > best_score:
                best_score = score
                best_move = move
                alpha = max(alpha, score)

                # Update killer moves
                if depth < len(self.killer_moves):
                    if self.killer_moves[depth][0] != move:
                        self.killer_moves[depth][1] = self.killer_moves[depth][0]
                        self.killer_moves[depth][0] = move

        return best_move, best_score
    
    def _negamax(self, board: chess.Board, depth: int, alpha: float, beta: float,
                stop_callback: Callable[[], bool] = None) -> float:
        """
        Negamax search with alpha-beta pruning

        Args:
            board: Current position
            depth: Remaining search depth
            alpha: Alpha value for pruning
            beta: Beta value for pruning
            stop_callback: Function to check if search should stop

        Returns:
            Position evaluation score
        """
        if stop_callback and stop_callback():
            return 0.0
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return 0.0

        # Terminal node evaluation
        if depth == 0:
            return self._quiescence_search(board, alpha, beta, stop_callback)

        # Check for game over
        if board.is_game_over():
            if board.is_checkmate():
                return -1000 + (self.max_depth - depth)  # Prefer faster mates
            else:
                return 0  # Draw

        # Transposition table lookup
        board_hash = chess.polyglot.zobrist_hash(board)
        if board_hash in self.transposition_table:
            entry = self.transposition_table[board_hash]
            if entry['depth'] >= depth:
                if entry['flag'] == 'EXACT':
                    return entry['score']
                elif entry['flag'] == 'LOWERBOUND' and entry['score'] >= beta:
                    return entry['score']
                elif entry['flag'] == 'UPPERBOUND' and entry['score'] <= alpha:
                    return entry['score']

        original_alpha = alpha
        best_score = float('-inf')
        best_move = None

        # Get ordered moves
        moves = self.order_moves(board, depth)

        for move in moves:
            if stop_callback and stop_callback():
                break
            if self.time_manager.should_stop(depth, self.nodes_searched):
                break

            board.push(move)
            self.nodes_searched += 1

            score = -self._negamax(board, depth - 1, -beta, -alpha, stop_callback)

            board.pop()

            if score > best_score:
                best_score = score
                best_move = move

            alpha = max(alpha, score)
            if alpha >= beta:
                # Update killer moves for cutoff
                if depth < len(self.killer_moves) and not board.is_capture(move):
                    if self.killer_moves[depth][0] != move:
                        self.killer_moves[depth][1] = self.killer_moves[depth][0]
                        self.killer_moves[depth][0] = move
                break  # Beta cutoff

        # Store in transposition table
        flag = 'EXACT'
        if best_score <= original_alpha:
            flag = 'UPPERBOUND'
        elif best_score >= beta:
            flag = 'LOWERBOUND'

        self.transposition_table[board_hash] = {
            'score': best_score,
            'depth': depth,
            'flag': flag,
            'move': best_move
        }

        # Limit transposition table size
        if len(self.transposition_table) > self.hash_size * 1000:
            # Remove random entries to free space
            keys_to_remove = random.sample(list(self.transposition_table.keys()), 
                                         len(self.transposition_table) // 4)
            for key in keys_to_remove:
                del self.transposition_table[key]

        return best_score
    
    def _quiescence_search(self, board: chess.Board, alpha: float, beta: float,
                         stop_callback: Callable[[], bool] = None, depth: int = 0) -> float:
        """
        Quiescence search to avoid horizon effect

        Args:
            board: Current position
            alpha: Alpha value for pruning
            beta: Beta value for pruning
            stop_callback: Function to check if search should stop
            depth: Current quiescence depth

        Returns:
            Position evaluation score
        """
        if stop_callback and stop_callback():
            return 0.0
        if depth > 10:  # Limit quiescence depth
            return self.evaluate_position(board)

        # Stand pat score
        stand_pat = self.evaluate_position(board)

        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        # Only search captures in quiescence
        captures = [move for move in board.legal_moves if board.is_capture(move)]

        # Order captures by MVV-LVA (Most Valuable Victim - Least Valuable Attacker)
        captures.sort(key=lambda move: self._mvv_lva_score(board, move), reverse=True)

        for move in captures:
            if stop_callback and stop_callback():
                break

            board.push(move)
            self.nodes_searched += 1

            score = -self._quiescence_search(board, -beta, -alpha, stop_callback, depth + 1)

            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

        return alpha

    def _mvv_lva_score(self, board: chess.Board, move: chess.Move) -> int:
        """Most Valuable Victim - Least Valuable Attacker score"""
        piece_values = [0, 1, 3, 3, 5, 9, 10]  # None, P, N, B, R, Q, K

        victim = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)

        if victim is None:
            return 0

        victim_value = piece_values[victim.piece_type]
        attacker_value = piece_values[attacker.piece_type]

        return victim_value * 100 - attacker_value
    
    # ==========================================
    # ============= RULE FUNCTIONS =============
    
    def _piece_square_table_evaluation(self, color):
        pst_score = 0.0

        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == color:
                # Get piece-square table value for this piece on this square
                pst_value = self.pst.get_piece_value(piece, square, color)
                pst_score += pst_value / 100.0  # Convert centipawns to pawn units

        # Weight the piece-square table evaluation
        weight = self.config['evaluation']['pst_weight']
        return pst_score * weight

    def _improved_mobility(self, color):
        """
        Mobility calculation with safe squares
        """
        score = 0.0

        for square in self.board.pieces(chess.KNIGHT, color):
            # Count safe moves (not attacked by enemy pawns)
            safe_moves = 0
            for target in self.board.attacks(square):
                if not self._is_attacked_by_pawn(target, not color):
                    safe_moves += 1
            score += safe_moves * self.config['evaluation']['knight_activity_bonus']

        for square in self.board.pieces(chess.BISHOP, color):
            safe_moves = 0
            for target in self.board.attacks(square):
                if not self._is_attacked_by_pawn(target, not color):
                    safe_moves += 1
            score += safe_moves * self.config['evaluation']['bishop_activity_bonus']

        return score

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
            if self.board.is_checkmate() and self.board.turn:
                score += self.config['evaluation']['checkmate_bonus']
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
        score = 0.0
        
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
        score = 0.0
        
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
        score = 0.0
        
        if self.board.has_castling_rights(chess.WHITE):
            score += self.config['evaluation']['castling_protection_bonus']
        if self.board.has_castling_rights(chess.BLACK):
            score -= self.config['evaluation']['castling_protection_bonus']
        
        return score

    def _pawn_structure(self):
        """Basic pawn structure evaluation"""
        score = 0.0
        
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
        score = 0.0
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
        score = 0.0
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn:
                if piece.piece_type == chess.BISHOP:
                    if len(self.board.attacks(square)) > 3:
                        score += self.config['evaluation']['bishop_vision_bonus']
        return score
    
    def _rook_coordination(self, color):
        """Calculate bonus for rook pairs on same file/rank"""
        score = 0.0
        rooks = [sq for sq in chess.SQUARES 
                if self.board.piece_at(sq) == chess.Piece(chess.ROOK, color)]
        
        # Check all unique rook pairs
        for i in range(len(rooks)):
            for j in range(i+1, len(rooks)):
                sq1, sq2 = rooks[i], rooks[j]
                
                # Same file bonus (15 centipawns)
                if chess.square_file(sq1) == chess.square_file(sq2):
                    score += self.config['evaluation']['stacked_rooks_bonus']
                    
                # Same rank bonus (10 centipawns)
                if chess.square_rank(sq1) == chess.square_rank(sq2):
                    score += self.config['evaluation']['coordinated_rooks_bonus']
        
        return score
