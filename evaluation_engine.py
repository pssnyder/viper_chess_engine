# evaluation_engine.py

import chess
import yaml
import random
import logging
import logging.handlers
from piece_square_tables import PieceSquareTables
from typing import Optional, Callable, Dict, Any, List, Tuple
from time_manager import TimeManager

class EvaluationEngine:
    def __init__(self, board):
        self.board = board
        self.time_manager = TimeManager()

        # Variable init
        self.nodes_searched = 0
        self.transposition_table = {}
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table = {}
        self.counter_moves = {}

        # Fallback piece values
        self.piece_values = {
            chess.KING: 0.0,
            chess.QUEEN: 9.0,
            chess.ROOK: 5.0,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3.0,
            chess.PAWN: 1.0
        }

        # Initialize piece-square tables
        try:
            self.pst = PieceSquareTables()
        except Exception as e:
            print(f"Warning: Could not initialize PST: {e}")
            self.pst = None

        # Cache for performance
        self._position_cache = {}

        # Load configuration with error handling
        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = self._get_default_config()

        # Search evaluation configuration
        self.depth = 0
        self.max_depth = 8
        self.hash_size = 64  # MB
        self.threads = 1
        self.async_mode = self.config['ai']['async_mode']
        self.logging_enabled = self.config['debug']['enable_logging']
        self.show_thoughts = self.config['debug']['show_thinking']
        self.move_ordering_enabled = self.config['ai']['move_ordering']
        self.quiescence_enabled = self.config['ai']['use_quiescence'],
        self.move_time_limit = self.config['ai']['move_time_limit']
        
        # Enable logging
        self.logger = None
        if self.logging_enabled:
            self.setup_logger()
        else:
            self.show_thoughts = False
    
    # =================================
    # ==== EVALUATOR CONFIGURATION ====   
    
    def _get_default_config(self):
        """Provide default configuration if config.yaml fails to load"""
        return {
            'ai': {
                'search_depth': 3,
                'async_mode': False,
                'move_time_limit': 0,
                'move_ordering': False,
                'use_quiescence': False
            },
            'debug': {
                'show_thinking': False,
                'enable_logging': True
            }
        }     
    
    def configure_for_side(self, ai_config):
        """Configure evaluation engine with side-specific settings"""
        
        # Store original settings for restoration if needed
        if not hasattr(self, '_original_settings'):
            self._original_settings = {
                'depth': self.depth,
                'move_ordering_enabled': self.move_ordering_enabled,
                'quiescence_enabled': self.quiescence_enabled,
                'move_time_limit': self.move_time_limit
            }

        # Update depth settings with validation
        new_depth = ai_config.get('depth', self.depth)
        self.depth = max(1, min(new_depth, 10))  # Clamp between 1 and 10

        # Update search settings
        self.move_ordering_enabled = ai_config.get('move_ordering', self.move_ordering_enabled)
        self.quiescence_enabled = ai_config.get('quiescence', self.quiescence_enabled)

        # Update time settings
        time_limit = ai_config.get('time_limit', 0)
        if time_limit > 0:
            self.move_time_limit = time_limit

        # Update piece-square table settings
        if hasattr(self, 'pst') and self.pst:
            self.pst_weight = ai_config.get('pst_weight', 1.0)
            self.pst_enabled = ai_config.get('pst_enabled', True)

        # Debug output for configuration changes
        if self.show_thoughts and self.logger:
            self.logger.debug(f"AI configured: depth={self.depth}, ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, pst_weight={getattr(self, 'pst_weight', 'N/A')}")

    # =================================
    # ======== SCORING HANDLER ========
    
    def _calculate_score(self, board, color):
        """IMPROVED scoring with piece-square tables"""
        self.board = board # Update evaluator board prior to scoring
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
    
    def _deepsearch_move(self, player):
        best_move = None
        board = self.board
        if self.show_thoughts:
            self.logger.debug(f"== DEEPSEARCH EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) ==")
        
        best_move = self._search(board, {})
    
        if self.show_thoughts:
            self.logger.debug(f"Deepsearch discovered move: {best_move} (Evaluation: {self.evaluate_position():.3f})")
        
        return best_move.uci() if best_move else None

    def _lookahead_move(self, player):
        best_move = None
        best_score = -float('inf') if player == chess.WHITE else float('inf')
        board = self.board
        
        if self.show_thoughts:
            self.logger.debug(f"== LOOKAHEAD EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) ==")
            
        for move in board.legal_moves:
            board.push(move)
            score = self.evaluate_position_with_lookahead(board)
            board.pop()
            
            if (player == chess.WHITE and score > best_score) or (player == chess.BLACK and score < best_score):
                best_score = score
                best_move = move
        
        if self.show_thoughts:
            self.logger.debug(f"Lookahead discovered move: {best_move} (Evaluation: {self.evaluate_position():.3f})")
        
        
        return best_move.uci() if best_move else None
    
    def _simple_eval_move(self, player):
        best_move = None
        best_score = -float('inf') if player == chess.WHITE else float('inf')
        board = self.board
        
        if self.show_thoughts:
            self.logger.debug(f"== SIMPLE EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) ==")
        
        # Get list of available moves
        moves = list(board.legal_moves)
        
        # Ordering of legal moves for faster pruning
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
            
        # Evaluate each move
        for move in moves:
            # Make the move
            board.push(move)
            
            # Get simple evaluation (no depth search)
            score = self.evaluate_position_from_perspective(board, player)
            
            # Debug output
            if self.show_thoughts:
                self.logger.debug(f"{'White' if player == chess.WHITE else 'Black'} is considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")

            # Undo the move
            board.pop()
            
            # Update best move based on player perspective
            if ((player == chess.WHITE and score > best_score) or (player == chess.BLACK and score < best_score)):
                best_score = score
                best_move = move
        
        if self.show_thoughts:
            self.logger.debug(f"Simple eval discovered move: {best_move} (Evaluation: {best_score:.3f})")
        
        return best_move.uci() if best_move else None
    
    def evaluate_position(self):
        """Calculate base position evaluation from white's perspective"""
        score = 0.0
        white_score = 0.0
        black_score = 0.0
        try:
            white_score = self._calculate_score(self.board, chess.WHITE)
            black_score = self._calculate_score(self.board, chess.BLACK)
            score = white_score - black_score
        except Exception:
            # Fallback to simple material evaluation
            white_score = self._material_score(chess.WHITE)
            black_score = self._material_score(chess.BLACK)
            score = white_score - black_score            
        return score

    def evaluate_position_from_perspective(self, board, player):
        """Calculate position evaluation from specified player's perspective"""
        score = 0.0
        white_score = self._calculate_score(board, chess.WHITE)
        black_score = self._calculate_score(board, chess.BLACK)
        
        if player == chess.WHITE:
            score = white_score - black_score
        else:
            score = black_score - white_score

        return score

    def evaluate_position_with_lookahead(self, board):
        """Minimax with proper perspective handling"""
        return self._minimax(self.depth, board, -float('inf'), float('inf'), board.turn == chess.WHITE)

    def evaluate_position_with_deepsearch(self, board):
        if self.move_time_limit == 0:
            time_control = {"infinite": True}
        else:
            time_control = {"movetime": self.move_time_limit}
        return self._search(board,time_control,stop_callback=0)
    
    def evaluate_move(self, board, move):
        """Quick evaluation of individual move on overall eval"""
        board.push(move)
        score = self.evaluate_position()

        # Debug output
        if self.show_thoughts:
            self.logger.debug(f"{'White' if board.turn == chess.WHITE else 'Black'} considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")

        board.pop()
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
    
    def _score_move(self, board, move, hash_move, depth):
        """Score a move for ordering"""
        # Base score
        score = 0.0

        # 1. Hash move gets highest priority
        if hash_move and move == hash_move:
            return 10000000

        # 2. Captures scored by MVV-LVA (Most Valuable Victim - Least Valuable Aggressor)
        if board.is_capture(move):
            victim_piece = board.piece_at(move.to_square)
            aggressor_piece = board.piece_at(move.from_square)
            if victim_piece is None or aggressor_piece is None:
                return 0
            # Most valuable victim (queen=9, rook=5, etc.) minus least valuable aggressor
            victim_value = self.piece_values.get(victim_piece.piece_type, 0)
            aggressor_value = self.piece_values.get(aggressor_piece.piece_type, 0)

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
        piece = board.piece_at(move.from_square)
        if piece is None:
            return 0
        history_key = (piece.piece_type, move.from_square, move.to_square)
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
    
    def new_game(self):
        """Reset engine for new game"""
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.nodes_searched = 0

    def set_max_depth(self, depth: int):
        """Set maximum search depth"""
        self.max_depth = max(1, min(depth, 20))
        #self.depth = self.max_depth # TODO commenting this out since I worry it will override depth in the wrong direction

    def set_hash_size(self, size_mb: int):
        """Set transposition table size"""
        self.hash_size = max(1, min(size_mb, 1024))
        # Clear table when resizing
        self.transposition_table.clear()

    def set_threads(self, threads: int):
        """Set number of search threads"""
        self.threads = max(1, min(threads, 8))

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
        piece = board.piece_at(move.from_square)
        if piece is None:
            return
        history_key = (piece.piece_type, move.from_square, move.to_square)

        # Update history score using depth-squared bonus
        self.history_table[history_key] += depth * depth

    def update_counter_move(self, last_move, current_move):
        """Update counter move table"""
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            self.counter_moves[counter_key] = current_move
    
    def setup_logger(self):
        """Setup file logging for AI thoughts"""
        self.logger = logging.getLogger('chess_ai')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        if self.show_thoughts:
            file_handler = logging.handlers.RotatingFileHandler(
                'logging/chess_ai_thoughts.log', 
                maxBytes=1000*1024*1024,  # 1GB max
                backupCount=3
            )
            
            formatter = logging.Formatter(
                '%(asctime)s | %(funcName)-15s | %(message)s',
                datefmt='%H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            self.logger.propagate = False

    # =======================================
    # ========== SEARCH ALGORITHMS ==========
    
    def _minimax(self, depth, board, alpha, beta, maximizing_player):
        """Minimax that properly handles perspectives"""
        score = 0.0
        move = None
        if depth == 0 or board.is_game_over():
            base_eval = self.evaluate_position_from_perspective(board, board.turn)
            return base_eval
        
        # Get list of available moves
        moves = list(board.legal_moves)
        
        # Ordering of legal moves for faster pruning
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
            
        if maximizing_player:
            max_eval = -float('inf')
            for move in moves:
                board.push(move)
                score = self._minimax(depth-1, board, alpha, beta, False)
                # Debug output
                if self.show_thoughts:
                    self.logger.debug(f"{'White' if board.turn  == chess.WHITE else 'Black'} considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")
                board.pop()
                max_eval = max(max_eval, score)
                alpha = max(alpha, score)
                if beta <= alpha:
                    if self.show_thoughts:
                        self.logger.debug(f"Minimax discovered move: {move} (Evaluation: {score:.3f})")
                    break
            return max_eval
        else:
            min_eval = float('inf')
            for move in moves:
                board.push(move)
                score = self._minimax(depth-1, board, alpha, beta, True)
                # Debug output
                if self.show_thoughts:
                    self.logger.debug(f"{'White' if board.turn  == chess.WHITE else 'Black'} considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")
                board.pop()
                min_eval = min(min_eval, score)
                beta = min(beta, score)
                if beta <= alpha:
                    if self.show_thoughts:
                        self.logger.debug(f"Minimax discovered move: {move} (Evaluation: {score:.3f})")
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
        move = None
        score = 0.0

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

        try:
            # Iterative deepening search
            for depth in range(1, max_depth + 1):
                if stop_callback and stop_callback():
                    break
                if self.time_manager.should_stop(depth, self.nodes_searched):
                    break

                move, score = self._search_depth(board, depth, stop_callback)

                if move:
                    # Print UCI info
                    elapsed = self.time_manager.time_elapsed()
                    nps = int(self.nodes_searched / max(elapsed, 0.001))
                    # Debug output
                    if self.show_thoughts:
                        self.logger.debug(f"info depth {depth} score cp {int(score * 100)} "
                          f"nodes {self.nodes_searched} time {int(elapsed * 1000)} "
                          f"nps {nps} pv {move.uci()}")

                # Don't continue if we found a mate
                if abs(score) > 9000:  # Mate score threshold
                    break

        except Exception as e:
            self.logger.debug(f"info string Search error: {e}")

        return move.uci() if move else None

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
        move = None
        score = 0.0
        
        # Get list of available moves
        moves = list(board.legal_moves)
        
        # Ordering of legal moves for faster pruning
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)

        for move in moves:
            if stop_callback and stop_callback():
                break
            if self.time_manager.should_stop(depth, self.nodes_searched):
                break

            board.push(move)
            self.nodes_searched += 1

            # Search the position after this move
            score = -self._negamax(board, depth - 1, -beta, -alpha, stop_callback)
            
            # Debug output
            if self.show_thoughts:
                self.logger.debug(f"{'White' if board.turn  == chess.WHITE else 'Black'} considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")
            
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
            
        if self.show_thoughts:
            self.logger.debug(f"Minimax discovered move: {best_move} (Evaluation: {best_score:.3f})")
                        
        return best_move.uci() if best_move else None, best_score
    
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
        original_alpha = alpha
        best_move = None
        best_score = float('-inf')
        move = None
        score = 0.0
        
        if stop_callback and stop_callback():
            return 0.0
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return 0.0

        # Terminal node evaluation
        if depth == 0 and self.quiescence_enabled:
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
        
        # Get list of available moves
        moves = list(board.legal_moves)
        
        # Ordering of legal moves for faster pruning
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)

        for move in moves:
            if stop_callback and stop_callback():
                break
            if self.time_manager.should_stop(depth, self.nodes_searched):
                break

            board.push(move)
            self.nodes_searched += 1

            score = -self._negamax(board, depth - 1, -beta, -alpha, stop_callback)
            
            # Debug output
            if self.show_thoughts:
                self.logger.debug(f"{'White' if board.turn  == chess.WHITE else 'Black'} considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")
                
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
            return self.evaluate_position_from_perspective(board, board.turn)

        # Stand pat score
        stand_pat = self.evaluate_position_from_perspective(board, board.turn)

        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        move = None
        score = 0.0
        
        # Only search captures in quiescence
        captures = [move for move in board.legal_moves if board.is_capture(move)]

        # Order captures by MVV-LVA (Most Valuable Victim - Least Valuable Attacker)
        captures.sort(key=lambda move: self._mvv_lva_score(board, move), reverse=True)
        
        # Ordering of legal moves for faster pruning
        if self.move_ordering_enabled:
            captures = self.order_moves(board, captures)
        
        for move in captures:
            if stop_callback and stop_callback():
                break

            board.push(move)
            self.nodes_searched += 1

            score = -self._quiescence_search(board, -beta, -alpha, stop_callback, depth + 1)
            
            # Debug output
            if self.show_thoughts:
                self.logger.debug(f"{'White' if board.turn == chess.WHITE else 'Black'} considering move: {move} | Resulting eval: {score:.3f} | FEN: {board.fen()}")
            
            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

        return alpha

    def _mvv_lva_score(self, board: chess.Board, move: chess.Move) -> int:
        """Most Valuable Victim - Least Valuable Attacker score"""
        piece_values = [0, 1, 3, 3, 5, 9, 10]  # None, P, N, B, R, Q, K

        victim_piece = board.piece_at(move.to_square)
        attacker_piece = board.piece_at(move.from_square)

        if victim_piece is None or attacker_piece is None:
            return 0

        victim_value = piece_values[victim_piece.piece_type]
        attacker_value = piece_values[attacker_piece.piece_type]

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
        weight = self.config['white_ai_config']['white_pst_weight'] if color == chess.WHITE else self.config['black_ai_config']['black_pst_weight']
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
