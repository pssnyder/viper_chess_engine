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
    def __init__(self, board, player):
        self.board = board
        self.current_player = player
        self.time_manager = TimeManager()

        # Variable init
        self.nodes_searched = 0
        self.transposition_table = {}
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table = {}
        self.counter_moves = {}

        # Default piece values
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

        # Performance settings
        self.hash_size = self.config['performance']['hash_size']
        self.threads = self.config['performance']['thread_limit']
        
        # Initialize AI settings
        self.ai_config = {
            'ai_color': self.board.turn,
            'ai_type': random,
            'depth': 1,
            'max_depth': 1,
            'move_ordering_enabled': False,
            'quiescence_enabled': False,
            'move_time_limit': 1000,
            'pst_enabled': False,
            'pst_weight': 0.0,
            'engine': 'None',
            'ruleset': 'None'
        }
        self.ai_type = self.ai_config.get('ai_type','random')
        self.ai_color = self.ai_config.get('ai_color',chess.WHITE)
        self.depth = self.ai_config.get('depth',1)
        self.max_depth = self.ai_config.get('max_depth',1)
        self.move_ordering_enabled = self.ai_config.get('move_ordering_enabled', False)
        self.quiescence_enabled = self.ai_config.get('quiescence_enabled', False)
        self.move_time_limit = self.ai_config.get('move_time_limit', 0)
        self.time_control = self.ai_config['infinite'] = True
        self.pst_enabled = self.ai_config.get('pst_enabled', False)
        self.pst_weight = self.ai_config.get('pst_weight', 1.0)
        self.engine = self.ai_config.get('engine','viper')
        self.ruleset = self.ai_config.get('ruleset','evaluation')
        
        # Enable logging
        self.logging_enabled = self.config['debug']['enable_logging']
        self.show_thoughts = self.config['debug']['show_thinking']
        self.logger = None
        if self.logging_enabled:
            self.setup_logger()
        else:
            self.show_thoughts = False
    
    # =================================
    # ==== EVALUATOR CONFIGURATION ====   
      
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
        # Update AI configuration for this bot
        new_depth = self.ai_config.get('depth', self.depth)
        self.max_depth = self.ai_config.get('max_depth', 1)
        self.depth = max(1, min(new_depth, self.max_depth))  # Clamp between 1 and max
        self.ai_color = self.ai_config.get('ai_color', chess.WHITE)
        self.move_ordering_enabled = self.ai_config.get('move_ordering_enabled', False)
        self.quiescence_enabled = self.ai_config.get('quiescence_enabled', False)
        self.move_time_limit = self.ai_config.get('move_time_limit', 1000)
        if self.move_time_limit == 0:
            self.time_control = {"infinite": True}
        else:
            self.time_control = {"movetime": self.move_time_limit}
        # Update piece-square table settings
        if hasattr(self, 'pst') and self.pst:
            self.pst_weight = ai_config.get('pst_weight', 1.0)
            self.pst_enabled = ai_config.get('pst_enabled', True)
        self.engine = self.ai_config.get('engine','None')
        self.ruleset = self.ai_config.get('ruleset','None')

        # Debug output for configuration changes
        if self.show_thoughts and self.logger:
            self.logger.debug(f"AI configured for {'White' if self.board.turn == chess.WHITE else 'Black'}: type={self.ai_type} depth={self.depth}, ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, pst_enabled={self.pst_enabled} pst_weight={self.pst_weight}")

    # =================================
    # ===== MOVE SEARCH HANDLERS ======
    
    def _search_for_move(self, board, player, ai_type, ai_config):
        """Searches for the best valid move using the AIs configured algorithm"""
        best_move = None
        self.board = board.copy()
        self.current_player = player
        self.ai_type = ai_type
        self.ai_config = ai_config
        # Set up this ai
        self.configure_for_side(ai_config)
        # Start move evaluation
        if self.show_thoughts:
            self.logger.debug(f"== EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) ==")
        
        # AI Selection
        if ai_type == 'deepsearch':
            best_move = self._deepsearch(self.board.copy(), self.depth, self.time_control)
        elif ai_type == 'minimax':
            best_move = self._minimax(self.board.copy(), self.depth, -float('inf'), float('inf'), self.player)
        elif ai_type == 'negamax':
            best_move = self._negamax(self.board.copy(), self.depth, -float('inf'), float('inf'))
        elif ai_type == 'lookahead':
            best_move = self._lookahead_search(self.board.copy(), self.depth)
        elif ai_type == 'simple_search':
            best_move = self._simple_search()
        elif ai_type == 'evaluation_only':
            best_move = self._evaluation_only()
        elif ai_type == 'random':
            best_move = self._random_search()
        else: # make a random move if other
            best_move = self._random_search()
        
        if self.quiescence_enabled:
            # Perform quiescence search if enabled
            best_move = self._quiescence_search(self.board.copy(), best_move, -float('inf'), float('inf'))
        if self.show_thoughts:
            self.logger.debug(f"AI is strongly considering the move: {best_move} | Evaluation: {self.evaluate_position(board):.3f} | FEN: {board.fen()}")
        
        return best_move if best_move else None
    
    # =================================
    # ===== EVALUATION FUNCTIONS ======
        
    def evaluate_position(self, board: chess.Board):
        """Calculate base position evaluation from white's perspective"""
        score = 0.0
        white_score = 0.0
        black_score = 0.0
        board = self.board.copy()
        try:
            white_score = self._calculate_score(board, chess.WHITE)
            black_score = self._calculate_score(board, chess.BLACK)
            score = white_score - black_score
        except Exception:
            # Fallback to simple material evaluation
            white_score = self._material_score(board, chess.WHITE)
            black_score = self._material_score(board, chess.BLACK)
            score = white_score - black_score            
        return score if score is not None else 0.0

    def evaluate_position_from_perspective(self, board, player):
        """Calculate position evaluation from specified player's perspective"""
        score = 0.0
        board = self.board.copy()
        try:
            white_score = self._calculate_score(board, chess.WHITE)
            black_score = self._calculate_score(board, chess.BLACK)
            score = float(white_score - black_score if player == chess.WHITE else black_score - white_score)
            return score if score is not None else 0.0
        except Exception as e:
            return 0.0  # Fallback to neutral score
    
    def evaluate_move(self, move):
        """Quick evaluation of individual move on overall eval"""
        score = 0.0
        board = self.board.copy()
        if move not in board.legal_moves:  # Add validation check
            return self.ai_config.get('checkmate_bonus') * -1000
        board.push(move)
        score = self.evaluate_position(board)
        # Debug output
        #if self.show_thoughts:
        #    self.logger.debug(f"Exploring the move: {move} | Evaluation: {score:.3f} | FEN: {board.fen()}")
        board.pop()
        return score if score is not None else 0.0

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

        moves = [m for m in moves if m in board.legal_moves]
        
        for move in moves:
            # Checks and Mates
            if move not in board.legal_moves :  # Add validation check
                return [] # ensure illegal move is never played
            board.push(move)
            # Check if this move gives checkmate!
            if board.is_checkmate():
                board.pop()
                return [move for move in moves if move in board.legal_moves]
            # Calculate score for move
            score = self._order_move_score(board.copy(), move, hash_move, depth)
            if score is None:
                score = 0.0
            move_scores.append((move, score))
            board.pop()
            
        # Sort moves by score in descending order
        move_scores.sort(key=lambda x: x[1], reverse=True)

        # Return just the moves, not the scores
        return [move for move, _ in move_scores]
    
    def _order_move_score(self, board, move, hash_move, depth):
        """Score a move for ordering"""
        # Base score
        score = 0.0

        # Hash move or checkmate gets highest priority
        if hash_move and move == hash_move:
            return self.config.get('evaluation', {}).get('hash_move_bonus', 5000.0)

        # Captures scored by MVV-LVA (Most Valuable Victim - Least Valuable Aggressor)
        if board.is_capture(move):
            victim_piece = board.piece_at(move.to_square)
            aggressor_piece = board.piece_at(move.from_square)
            if victim_piece is None or aggressor_piece is None:
                return 0.0
            # Most valuable victim (queen=9, rook=5, etc.) minus least valuable aggressor
            victim_value = self.piece_values.get(victim_piece.piece_type, 0)
            aggressor_value = self.piece_values.get(aggressor_piece.piece_type, 0)

            # MVV-LVA formula: 10 * victim_value - aggressor_value
            score += self.config.get('evaluation', {}).get('capture_move_bonus', 4000.0) + 10 * victim_value - aggressor_value

            # Bonus for promotions
            if move.promotion:
                score += float(self.config.get('evaluation', {}).get('promotion_move_bonus', 3000.0)) + 100  # High score for promotion captures

            return score if score is not None else 0.0

        # Killer moves (non-capture moves that caused a beta cutoff)
        if depth in self.killer_moves and move in self.killer_moves[depth]:
            return self.config.get('evaluation', {}).get('killer_move_bonus', 2000.0)

        # Counter moves (moves that are good responses to the previous move)
        last_move = board.peek() if board.move_stack else None
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            if counter_key in self.counter_moves and self.counter_moves[counter_key] == move:
                return self.config.get('evaluation', {}).get('counter_move_bonus', 1000.0)

        # History heuristic (moves that have caused cutoffs in similar positions)
        piece = board.piece_at(move.from_square)
        if piece is None:
            return 0.0
        history_key = (piece.piece_type, move.from_square, move.to_square)
        history_score = self.history_table.get(history_key, 0)

        # Promotions (already handled in captures, but add for non-capture promotions)
        if move.promotion:
            score += float(self.config.get('evaluation', {}).get('promotion_move_bonus', 3000.0))

        # Checks and Mates
        if move not in board.legal_moves:  # Add validation check
            return -1000000.0 # ensure legal move is never played
        
        # prepare the evaluation by pushing the move
        board.push(move)
        
        # Check if this move gives checkmate!
        if board.is_checkmate():
            board.pop()
            return self.config.get('evaluation', {}).get('checkmate_move_bonus', 1000000.0) * 1000.0
        
        if board.is_check():
            score += float(self.config['evaluation']['check_move_bonus'])

        # Add history score
        score += history_score

        return score if score is not None else 0.0
    
    def _get_dynamic_search_depth(self, board: chess.Board, depth: int, stop_callback: Callable[[], bool] = None) -> Tuple[Optional[chess.Move], float]:
        """Search to a dynamically selected depth"""
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
            moves = self.order_moves(board.copy(), moves)

        for move in moves:
            if stop_callback and stop_callback():
                break
            if self.time_manager.should_stop(depth, self.nodes_searched):
                break
            board.push(move)
            self.nodes_searched += 1
            # Search the position after this move
            score = -self._negamax(board, depth - 1, -beta, -alpha, stop_callback)
            #if self.show_thoughts:
            #    self.logger.debug(f"Exploring the move: {move} at a depth of {depth} | Evaluation: {score:.3f} a: {alpha} b: {beta} | FEN: {board.fen()}")
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
            self.logger.debug(f"Considering the move: {best_move} at a depth of {depth} | Evaluation: {best_score:.3f} a: {alpha} b: {beta} | FEN: {board.fen()}")
                        
        return best_move if best_move else None, best_score
    
    def _quiescence_search(self, board: chess.Board, move, alpha: float, beta: float, stop_callback: Callable[[], bool] = None, depth: int = 0):
        """
        Quiescence search to avoid horizon effect.
        Returns the original move provided, or a better move if found.
        """
        if stop_callback and stop_callback():
            return move

        if depth > 2:  # Limit quiescence depth
            return move

        stand_pat = self.evaluate_position_from_perspective(board, board.turn)
        best_score = stand_pat
        best_move = move

        if stand_pat >= beta:
            return move
        if stand_pat > alpha:
            alpha = stand_pat

        # Only search captures and checks in quiescence
        captures = [m for m in board.legal_moves if board.is_capture(m) or board.gives_check(m)]
        # Order captures by MVV-LVA
        captures.sort(key=lambda m: self._mvv_lva_score(board, m), reverse=True)
        if self.move_ordering_enabled:
            captures = self.order_moves(board.copy(), captures)

        for m in captures:
            if stop_callback and stop_callback():
                break
            if m not in board.legal_moves:
                continue
            board.push(m)
            if board.is_checkmate():
                board.pop()
                return m
            self.nodes_searched += 1
            score = -self._quiescence_search(board, m, -beta, -alpha, stop_callback, depth + 1)
            board.pop()
            if score > best_score:
                best_score = score
                best_move = m
            if score >= beta:
                return best_move
            if score > alpha:
                alpha = score

        return best_move
    
    def _mvv_lva_score(self, board: chess.Board, move: chess.Move):
        """Most Valuable Victim - Least Valuable Attacker score"""
        score = 0.0
        piece_values = [0, 1, 3, 3, 5, 9, 10]  # None, P, N, B, R, Q, K
        victim_piece = board.piece_at(move.to_square)
        attacker_piece = board.piece_at(move.from_square)
        if victim_piece is None or attacker_piece is None:
            return 0
        victim_value = piece_values[victim_piece.piece_type]
        attacker_value = piece_values[attacker_piece.piece_type]

        score = victim_value * 100 - attacker_value
        return score if score is not None else 0.0
    
    def new_game(self):
        """Reset engine for new game"""
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.nodes_searched = 0

    def set_max_depth(self, depth: int):
        """Set maximum search depth"""
        self.max_depth = max(1, min(depth, 10)) # bounding depth to 1-10
        self.depth = self.max_depth

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
    # ======= MAIN SEARCH ALGORITHMS ========
    
    def _random_search(self):
        legal_moves = list(self.board.legal_moves)
        return random.choice(legal_moves) if legal_moves else None
    
    def _evaluation_only(self): 
        """Evaluate the current position without searching"""
        return self.evaluate_position(self.board)
    
    def _simple_search(self):
        """Simple search that evaluates all legal moves and picks the best one"""
        best_move = None
        best_score = -float('inf') if self.board.turn == chess.WHITE else float('inf')
        board = self.board.copy()
        if self.depth == 0 or board.is_game_over():
            return None
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board.copy(), moves)
        for move in moves:
            board.push(move)
            score = self.evaluate_position_from_perspective(board, board.turn)
            board.pop()
            if self.board.turn == chess.WHITE:
                if score > best_score:
                    best_score = score
                    best_move = move
            else:
                if score < best_score:
                    best_score = score
                    best_move = move
        return best_move

    def _lookahead_search(self, board: chess.Board, depth: int, stop_callback: Callable[[], bool] = None):
        """Lookahead function to evaluate position at a given depth, returns best move"""
        if stop_callback and stop_callback():
            return None
        if depth == 0 or board.is_game_over(claim_draw=True):
            return None
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board.copy(), moves)
        best_move = None
        best_score = -float('inf') if board.turn == chess.WHITE else float('inf')
        for move in moves:
            new_board = board.copy()
            new_board.push(move)
            try:
                if depth - 1 == 0 or new_board.is_game_over(claim_draw=True):
                    score = self.evaluate_position_from_perspective(new_board, board.turn)
                else:
                    next_move = self._lookahead_search(new_board, depth - 1, stop_callback)
                    if next_move is not None:
                        new_board.push(next_move)
                    score = self.evaluate_position_from_perspective(new_board, board.turn)
            except Exception as e:
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Error during lookahead search: {e}")
                score = self.evaluate_position_from_perspective(new_board, board.turn)
            if board.turn == chess.WHITE:
                if score > best_score:
                    best_score = score
                    best_move = move
            else:
                if score < best_score:
                    best_score = score
                    best_move = move
        return best_move

    def _minimax(self, board: chess.Board, depth: int, alpha: float, beta: float, maximizing_player: bool, stop_callback: Callable[[], bool] = None):
        """Minimax that properly handles perspectives and returns best move at root"""
        if stop_callback and stop_callback():
            return None
        if depth == 0 or board.is_game_over():
            return None
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board.copy(), moves)
        best_move = None
        if maximizing_player:
            best_score = -float('inf')
            for move in moves:
                new_board = board.copy()
                new_board.push(move)
                if new_board.is_checkmate():
                    score = self.config['evaluation']['checkmate_bonus'] - (self.max_depth - depth)
                elif new_board.is_stalemate() or new_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax(new_board, depth-1, alpha, beta, False, stop_callback)
                    if result is None:
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                    else:
                        new_board.push(result)
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                if score > best_score:
                    best_score = score
                    best_move = move
                alpha = max(alpha, score)
                if beta <= alpha:
                    break
        else:
            best_score = float('inf')
            for move in moves:
                new_board = board.copy()
                new_board.push(move)
                if new_board.is_checkmate():
                    score = -self.config['evaluation']['checkmate_bonus'] + (self.max_depth - depth)
                elif new_board.is_stalemate() or new_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax(new_board, depth-1, alpha, beta, True, stop_callback)
                    if result is None:
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                    else:
                        new_board.push(result)
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                if score < best_score:
                    best_score = score
                    best_move = move
                beta = min(beta, score)
                if beta <= alpha:
                    break
        return best_move

    def _negamax(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Callable[[], bool] = None):
        """
        Negamax search with alpha-beta pruning, returns best move at root
        """
        if stop_callback and stop_callback():
            return None
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None
        if depth == 0 or board.is_game_over():
            return None
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board.copy(), moves)
        best_move = None
        best_score = -float('inf')
        for move in moves:
            board.push(move)
            if board.is_checkmate():
                score = self.config['evaluation']['checkmate_bonus'] - (self.max_depth - depth)
            elif board.is_stalemate() or board.is_insufficient_material():
                score = 0.0
            else:
                # For negamax, recursively call and negate the result
                result = self._negamax(board, depth-1, -beta, -alpha, stop_callback)
                if result is None:
                    score = self.evaluate_position_from_perspective(board, board.turn)
                else:
                    board.push(result)
                    score = -self.evaluate_position_from_perspective(board, not board.turn)
                    board.pop()
            board.pop()
            if score > best_score:
                best_score = score
                best_move = move
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best_move

    def _deepsearch(self, board: chess.Board, depth: int, time_control: Dict[str, Any], stop_callback: Callable[[], bool] = None):
        """
        Main search function, returns best move found
        """
        self.nodes_searched = 0
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None
        if len(legal_moves) == 1:
            return legal_moves[0]
        max_depth = self.max_depth
        if time_control.get('depth'):
            max_depth = time_control['depth']
        best_move = None
        best_score = -float('inf')
        try:
            for d in range(1, max_depth + 1):
                if stop_callback and stop_callback():
                    break
                if self.time_manager.should_stop(d, self.nodes_searched):
                    break
                move, score = self._get_dynamic_search_depth(board, d, stop_callback)
                if move is not None and (best_move is None or score > best_score):
                    best_move = move
                    best_score = score
                if abs(score) > 9000:
                    break
        except Exception as e:
            if self.logger:
                self.logger.debug(f"info string Search error: {e}")
        return best_move


    # ==================================
    # ====== RULE SCORING HANDLER ======
    
    def _calculate_score(self, board, color):
        """IMPROVED scoring with piece-square tables"""
        score = 0.0
        
        # Update the evaluator with the provided before scoring
        self.board = board
        self.current_player = color
        
        # Rules included in scoring
        score += 1.0 * (self._checkmate_threats(board) or 0.0)
        score += 1.0 * (self._piece_square_table_evaluation(board, color) or 0.0)
        score += 1.0 * (self._improved_mobility(board, color) or 0.0)
        score += 1.0 * (self._tempo_bonus(board, color) or 0.0)
        score += 1.0 * (self._repeating_positions(board) or 0.0)
        score += 1.0 * (self._material_score(board, color) or 0.0)
        score += 1.0 * (self._center_control(board) or 0.0)
        score += 1.0 * (self._piece_activity(color) or 0.0)
        score += 1.0 * (self._king_safety(color) or 0.0)
        score += 1.0 * (self._king_threat(board) or 0.0)
        score += 1.0 * (self._undeveloped_pieces(color) or 0.0)
        score += 1.0 * (self._special_moves(board) or 0.0)
        score += 1.0 * (self._tactical_evaluation(board) or 0.0)
        score += 1.0 * (self._castling_evaluation(board, color) or 0.0)
        score += 1.0 * (self._passed_pawns(board) or 0.0)
        score += 1.0 * (self._knight_pair(board) or 0.0)
        score += 1.0 * (self._bishiop_vision(board) or 0.0)
        score += 1.0 * (self._rook_coordination(board, color) or 0.0)

        return score
    
    # ==========================================
    # ========= RULE SCORING FUNCTIONS =========
    
    def _checkmate_threats(self, board):
        score = 0.0
        for move in board.legal_moves:
            board.push(move)
            if board.is_checkmate():
                score += self.config['evaluation']['checkmate_bonus']
                break
        board.pop()
        return score

    def _repeating_positions(self, board):
        score = 0.0
        if board.is_repetition(count=2):
            score += self.config['evaluation']['repetition_penalty']
        return score

    def _material_score(self, board, color):
        """Simple material count for given color"""
        return sum(len(board.pieces(p, color)) * v for p, v in self.piece_values.items())
    
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

    def _improved_mobility(self, board, color):
        """
        Mobility calculation with safe squares
        """
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            # Count safe moves (not attacked by enemy pawns)
            safe_moves = 0
            for target in board.attacks(square):
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self.config['evaluation']['knight_activity_bonus']

        for square in board.pieces(chess.BISHOP, color):
            safe_moves = 0
            for target in board.attacks(square):
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self.config['evaluation']['bishop_activity_bonus']

        return score

    def _tempo_bonus(self, board, color):
        if board.turn == color:
            return self.config['evaluation']['tempo_bonus']  # Small tempo bonus
        return 0.0

    def _is_attacked_by_pawn(self, board, square, by_color):
        """Helper function to check if a square is attacked by enemy pawns"""
        if by_color == chess.WHITE:
            # White pawns attack diagonally upward
            pawn_attacks = [square - 7, square - 9]
        else:
            # Black pawns attack diagonally downward
            pawn_attacks = [square + 7, square + 9]

        for attack_square in pawn_attacks:
            if 0 <= attack_square < 64:
                piece = board.piece_at(attack_square)
                if piece and piece.piece_type == chess.PAWN and piece.color == by_color:
                    return True
        return False

    def _center_control(self, board):
        """Simple center control"""
        score = 0.0
        center = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center:
            if board.piece_at(square) and board.piece_at(square).color == board.turn:
                score += self.config['evaluation']['center_control_bonus']
        return score

    def _piece_activity(self, board, color):
        """Mobility and attack patterns"""
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            score += len(board.attacks(square)) * self.config['evaluation']['knight_activity_bonus']

        for square in board.pieces(chess.BISHOP, color):
            score += len(board.attacks(square)) * self.config['evaluation']['bishop_activity_bonus']

        return score

    def _king_safety(self, board, color):
        score = 0.0
        king = board.king(color)
        if king is None:
            return score

        direction = 1 if color == board.turn else -1
        shield_squares = [
            king + 8 * direction + delta
            for delta in [-1, 0, 1]
            if 0 <= king + 8 * direction + delta < 64
        ]

        for shield in shield_squares:
            if shield in chess.SQUARES:
                piece = board.piece_at(shield)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    score += self.config['evaluation']['king_safety_bonus']

        return score

    def _king_threat(self, board):
        score = 0.0
        temp_board = board.copy()
        temp_board.turn = not board.turn

        if temp_board.is_check():
            score += self.config['evaluation']['king_threat_penalty']

        return score

    def _undeveloped_pieces(self, board, color):
        score = 0.0
        undeveloped = 0.0

        starting_squares = {
            chess.WHITE: [chess.B1, chess.G1, chess.C1, chess.F1],
            chess.BLACK: [chess.B8, chess.G8, chess.C8, chess.F8]
        }

        for square in starting_squares[color]:
            piece = board.piece_at(square)
            if piece and piece.color == color and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                undeveloped += 1

        if undeveloped > 0 and board.has_castling_rights(color):
            score = undeveloped * self.config['evaluation']['undeveloped_penalty']

        return score

    def _special_moves(self, board):
        """Evaluate special moves and opportunities"""
        score = 0.0
        
        # En passant
        if board.ep_square:
            score += self.config['evaluation']['en_passant_bonus']
        
        # Promotion opportunities
        for move in board.legal_moves:
            if move.promotion:
                score += self.config['evaluation']['pawn_promotion_bonus']
        
        return score

    def _tactical_evaluation(self, board):
        """Evaluate tactical elements"""
        score = 0.0
        
        # Captures
        for move in board.legal_moves:
            if board.is_capture(move):
                score += self.config['evaluation']['capture_bonus']
        
        # Checks
        for move in board.legal_moves:
            board.push(move)
            if board.is_check():
                score += self.config['evaluation']['check_bonus']
            board.pop()
        
        return score

    def _castling_evaluation(self, board, color):
        """Evaluate castling rights and opportunities"""
        score = 0.0
        if board.has_castling_rights(color):
            score += self.config['evaluation']['castling_protection_bonus']
        if board.has_castling_rights(color):
            score -= self.config['evaluation']['castling_protection_bonus']
        
        return score

    def _passed_pawns(self, board):
        """Basic pawn structure evaluation"""
        score = 0.0
        
        # Check for passed pawns
        for color in [chess.WHITE, chess.BLACK]:
            for square in board.pieces(chess.PAWN, color):
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
                                piece = board.piece_at(check_square)
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
    
    def _knight_pair(self, board):
        score = 0.0
        knights = []
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == board.turn:
                if piece.piece_type == chess.KNIGHT:
                    knights.append(square)
                    
        if len(knights) >= 2:
            score += len(knights) * self.config['evaluation']['knight_pair_bonus']
        return score

    def _bishiop_vision(self, board):
        score = 0.0
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == board.turn:
                if piece.piece_type == chess.BISHOP:
                    if len(board.attacks(square)) > 3:
                        score += self.config['evaluation']['bishop_vision_bonus']
        return score
    
    def _rook_coordination(self, board, color):
        """Calculate bonus for rook pairs on same file/rank"""
        score = 0.0
        rooks = [sq for sq in chess.SQUARES 
                if board.piece_at(sq) == chess.Piece(chess.ROOK, color)]
        
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

