# viper.py

""" Viper Evaluation Engine
This module implements the evaluation engine for the Viper chess AI.
It provides various search algorithms, evaluation functions, and move ordering
"""
# TODO: Refactor this module to use the new ruleset system and configuration management

from __future__ import annotations # Added for postponed evaluation of type annotations
import chess
import yaml
import random
import logging
import os
import threading
import time
from typing import Optional, Callable, Dict, Any, Tuple
from engine_utilities.piece_square_tables import PieceSquareTables
from engine_utilities.time_manager import TimeManager
from engine_utilities.opening_book import OpeningBook
from engine_utilities.viper_scoring_calculation import ViperScoringCalculation # Import the new scoring module
from collections import OrderedDict

# At module level, define a single logger for this file
# Renamed from evaluation_logger to viper_engine_logger for clarity, consistent with file/class name
viper_engine_logger = logging.getLogger("viper_evaluation_engine") # Renamed logger name
viper_engine_logger.setLevel(logging.DEBUG)
if not viper_engine_logger.handlers:
    if not os.path.exists('logging'):
        os.makedirs('logging', exist_ok=True)
    from logging.handlers import RotatingFileHandler
    log_file_path = "logging/viper_evaluation_engine.log" # New log file for ViperEvaluationEngine
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10*1024*1024,
        backupCount=3,
        delay=True
    )
    formatter = logging.Formatter(
        '%(asctime)s | %(funcName)-15s | %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    viper_engine_logger.addHandler(file_handler)
    viper_engine_logger.propagate = False

class LimitedSizeDict(OrderedDict):
    def __init__(self, *args, maxlen=100000, **kwargs):
        self.maxlen = maxlen
        super().__init__(*args, **kwargs)
    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxlen:
            oldest = next(iter(self))
            del self[oldest]

class ViperEvaluationEngine: # Renamed class from EvaluationEngine
    def __init__(self, board: chess.Board = chess.Board(), player: chess.Color = chess.WHITE, ai_config=None):
        self.board = board
        self.current_player = player
        self.time_manager = TimeManager()
        self.opening_book = OpeningBook()

        self.nodes_searched = 0
        self.transposition_table = LimitedSizeDict(maxlen=1000000)
        self.killer_moves = [[None, None] for _ in range(50)]
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

        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

        self.hash_size = self.config.get('performance', {}).get('hash_size', 1024)
        self.threads = self.config.get('performance', {}).get('thread_limit', 1)

        self.logging_enabled = self.config.get('monitor', {}).get('enable_logging', False)
        self.show_thoughts = self.config.get('debug', {}).get('show_thinking', False)
        self.logger = viper_engine_logger # Use the renamed logger
        if not self.logging_enabled:
            self.show_thoughts = False
        if self.logging_enabled:
            self.logger.debug("Logging enabled for ViperEvaluationEngine")

        self.ai_config = self._ensure_ai_config(ai_config, player)
        self.configure_for_side(self.board, self.ai_config)
        self.pst = PieceSquareTables()

        self.scoring_calculator = ViperScoringCalculation(
            config=self.config,
            ai_config=self.ai_config,
            piece_values=self.piece_values,
            pst=self.pst
        )

        self.strict_draw_prevention = self.config.get('game_config', {}).get('strict_draw_prevention', False)
        self.game_phase_awareness = self.config.get('game_config', {}).get('game_phase_awareness', False)
        self.endgame_factor = 0.0

        self.reset(self.board)

    def _ensure_ai_config(self, ai_config, player):
        if ai_config is None or not isinstance(ai_config, dict):
            ai_config = self.config.get('white_ai_config' if player == chess.WHITE else 'black_ai_config', {})
        ai_config['ai_type'] = ai_config.get('ai_type', 'random')
        ai_config['depth'] = ai_config.get('depth', 1)
        ai_config['max_depth'] = self.config.get('performance', {}).get('max_depth', 5)
        return ai_config

    def _get_ai_config(self, player_config: str):
        if player_config not in ['white_ai_config', 'black_ai_config']:
            raise ValueError("player_color for config retrieval must be 'white_ai_config' or 'black_ai_config'")
        
        ai_config_data = self.config.get(player_config, {})

        return {
            'exclude_from_metrics': ai_config_data.get('exclude_from_metrics', False),
            'ai_type': ai_config_data.get('ai_type', 'random'),
            'ai_color': ai_config_data.get('ai_color', 'white' if player_config == 'white_ai_config' else 'black'),
            'depth': ai_config_data.get('depth', 1),
            'max_depth': self.config.get('performance', {}).get('max_depth', 5),
            'use_solutions': ai_config_data.get('use_solutions', False),
            'pst_enabled': ai_config_data.get('pst', False),
            'pst_weight': ai_config_data.get('pst_weight', 1.0),
            'move_ordering_enabled': ai_config_data.get('move_ordering', False),
            'quiescence_enabled': ai_config_data.get('quiescence', False),
            'move_time_limit': ai_config_data.get('time_limit', 0),
            'engine': ai_config_data.get('engine', 'viper'),
            'ruleset': ai_config_data.get('ruleset', 'default_evaluation'),
            'scoring_modifier': ai_config_data.get('scoring_modifier', 1.0)
        }

    def configure_for_side(self, board: chess.Board, ai_config: dict):
        self.ai_config = self._ensure_ai_config(ai_config, board.turn)

        self.ai_type = self.ai_config.get('ai_type','random')
        self.ai_color = self.ai_config.get('ai_color', 'white')
        self.depth = self.ai_config.get('depth', 1)
        self.max_depth = self.config.get('performance', {}).get('max_depth', self.ai_config.get('max_depth', 5))
        self.solutions_enabled = self.ai_config.get('use_solutions', False)
        self.move_ordering_enabled = self.ai_config.get('move_ordering', False)
        self.quiescence_enabled = self.ai_config.get('quiescence', False)
        self.move_time_limit = self.ai_config.get('time_limit', 0)
        self.pst_enabled = self.ai_config.get('pst', False)
        self.pst_weight = self.ai_config.get('pst_weight', 1.0)
        self.eval_engine = self.ai_config.get('engine','viper')
        self.ruleset = self.ai_config.get('ruleset','default_evaluation')
        self.scoring_modifier = self.ai_config.get('scoring_modifier',1.0)

        if self.logging_enabled and self.logger:
            self.logger.debug(f"Configuring AI for {self.ai_color} with type={self.ai_type}, depth={self.depth}/{self.max_depth}, solutions={self.solutions_enabled}, move_ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, move_time={self.move_time_limit}, pst_enabled={self.pst_enabled}, pst_weight={self.pst_weight}, engine={self.eval_engine}, scoring_mod={self.scoring_modifier}, ruleset={self.ruleset}")
        
        if self.move_time_limit > 0:
            self.time_control = {"movetime": self.move_time_limit}
        else:
            self.time_control = {"infinite": True}
        
        self.scoring_calculator.ai_config = self.ai_config
        self.scoring_calculator.ruleset_name = self.ruleset
        self.scoring_calculator.current_ruleset = self.scoring_calculator.rulesets.get(self.ruleset, {})
        self.scoring_calculator.scoring_modifier = self.scoring_modifier
        self.scoring_calculator.pst_enabled = self.pst_enabled
        self.scoring_calculator.pst_weight = self.pst_weight


        if self.show_thoughts and self.logger:
            self.logger.debug(f"AI configured for {'White' if self.ai_color == 'white' else 'Black'}: type={self.ai_type} depth={self.depth}, ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, pst_enabled={self.pst_enabled} pst_weight={self.pst_weight}")

    def reset(self, board: chess.Board):
        self.board = board.copy()
        self.current_player = chess.WHITE if board.turn else chess.BLACK
        self.nodes_searched = 0
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.counter_moves.clear()
        if self.show_thoughts and self.logger:
            self.logger.debug(f"ViperEvaluationEngine for {self.ai_color} reset to initial state.")
        
        self.configure_for_side(self.board, self.ai_config)

    def _is_draw_condition(self, board):
        if board.can_claim_threefold_repetition():
            return True
        if board.can_claim_fifty_moves():
            return True
        if board.is_seventyfive_moves():
            return True
        return False

    def _get_game_phase_factor(self, board: chess.Board) -> float:
        if not self.game_phase_awareness:
            return 0.0
        
        total_material = 0
        for piece_type, value in self.piece_values.items():
            if piece_type != chess.KING:
                total_material += len(board.pieces(piece_type, chess.WHITE)) * value
                total_material += len(board.pieces(piece_type, chess.BLACK)) * value

        QUEEN_ROOK_MATERIAL = self.piece_values[chess.QUEEN] + self.piece_values[chess.ROOK]
        TWO_ROOK_MATERIAL = self.piece_values[chess.ROOK] * 2
        KNIGHT_BISHOP_MATERIAL = self.piece_values[chess.KNIGHT] + self.piece_values[chess.BISHOP]

        if total_material >= (QUEEN_ROOK_MATERIAL * 2) + (KNIGHT_BISHOP_MATERIAL * 2):
            return 0.0
        if total_material < (TWO_ROOK_MATERIAL + KNIGHT_BISHOP_MATERIAL * 2) and total_material > (KNIGHT_BISHOP_MATERIAL * 2):
            return 0.5
        if total_material <= (KNIGHT_BISHOP_MATERIAL * 2):
            return 1.0
        
        return 0.0

    # =================================
    # ===== MOVE SEARCH HANDLER =======

    def sync_with_game_board(self, game_board: chess.Board):
        if not isinstance(game_board, chess.Board) or not game_board.is_valid():
            if self.logger:
                self.logger.error(f"Invalid game board state detected during sync! | FEN: {getattr(game_board, 'fen', lambda: 'N/A')()}")
            return False
        self.board = game_board.copy()
        self.game_board = game_board.copy()
        return True

    def has_game_board_changed(self):
        if self.game_board is None:
            return False
        return self.board.fen() != self.game_board.fen()

    def search(self, board: chess.Board, player: chess.Color, ai_config: dict = {}, stop_callback: Optional[Callable[[], bool]] = None) -> chess.Move:
        self.nodes_searched = 0
        search_start_time = time.perf_counter()

        self.sync_with_game_board(board)
        best_move = chess.Move.null()
        self.board = board.copy()
        self.current_player = chess.WHITE if player == chess.WHITE else chess.BLACK

        self.ai_config = self._ensure_ai_config(ai_config, player)
        self.configure_for_side(self.board, self.ai_config)

        self.ai_type = self.ai_config.get('ai_type', 'random')
        self.depth = self.ai_config.get('depth', 1)
        self.max_depth = self.config.get('performance', {}).get('max_depth', self.ai_config.get('max_depth', 5))

        self.time_manager.start_timer(self.ai_config.get('move_time_limit', 0) / 1000.0)
        
        if self.solutions_enabled:
            book_move = self.opening_book.get_book_move(self.board)
            if book_move and self.board.is_legal(book_move):
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Opening book move found: {book_move} | FEN: {board.fen()}")
                
                search_duration = time.perf_counter() - search_start_time
                if self.logging_enabled and self.logger:
                    self.logger.debug(f"Opening book search took {search_duration:.4f} seconds and searched {self.nodes_searched} nodes.")
                return book_move
        
        trans_move, trans_score = self.get_transposition_move(board, self.depth)
        if trans_move:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Transposition table hit: {trans_move} (Score: {trans_score:.2f}) | FEN: {board.fen()}")
            
            search_duration = time.perf_counter() - search_start_time
            if self.logging_enabled and self.logger:
                self.logger.debug(f"Transposition table hit search took {search_duration:.4f} seconds and searched {self.nodes_searched} nodes.")
            return trans_move

        if self.show_thoughts:
            self.logger.debug(f"== EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) == | AI Type: {self.ai_config['ai_type']} | Depth: {self.ai_config['depth']} | Max Depth: {self.max_depth} ==")

        
        legal_moves = list(self.board.legal_moves)
        if not legal_moves:
            return chess.Move.null()

        if self.move_ordering_enabled:
            hash_move, _ = self.get_transposition_move(board, self.depth)
            ordered_moves = self.order_moves(board, legal_moves, hash_move=hash_move, depth=self.depth)
        else:
            ordered_moves = legal_moves
        
        best_score_overall = -float('inf')
        if self.current_player == chess.BLACK:
            best_score_overall = float('inf')

        best_move = ordered_moves[0] if ordered_moves else chess.Move.null()

        for move in ordered_moves:
            if self.time_manager.should_stop(self.depth, self.nodes_searched):
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Search stopped due to time limit during move iteration at root. Best move so far: {best_move}")
                break

            temp_board = self.board.copy()
            temp_board.push(move)

            current_move_score = 0.0

            try:
                if self.ai_type == 'deepsearch':
                    final_deepsearch_move_result = self._deep_search(self.board.copy(), self.depth, self.time_control, stop_callback=self.time_manager.should_stop) # Line 318
                    if final_deepsearch_move_result != chess.Move.null():
                        best_move = final_deepsearch_move_result
                        if self.board.is_legal(best_move):
                            temp_board_after_move = self.board.copy()
                            temp_board_after_move.push(best_move)
                            current_move_score = self.evaluate_position_from_perspective(temp_board_after_move, self.current_player)
                        
                        self.update_transposition_table(self.board, self.depth, best_move, current_move_score)
                        
                        search_duration = time.perf_counter() - search_start_time
                        if self.logging_enabled and self.logger:
                            self.logger.debug(f"Deepsearch final move selection took {search_duration:.4f} seconds and searched {self.nodes_searched} nodes.")
                        return best_move

                elif self.ai_type == 'minimax':
                    current_move_score = self._minimax_search(temp_board, self.depth -1, -float('inf'), float('inf'), not self.current_player, stop_callback=self.time_manager.should_stop) # Line 336
                elif self.ai_type == 'negamax':
                    current_move_score = -self._negamax_search(temp_board, self.depth - 1, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop) # Line 338
                elif self.ai_type == 'negascout':
                    current_move_score = -self._negascout(temp_board, self.depth - 1, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop) # Line 340
                elif self.ai_type == 'lookahead':
                    current_move_score = -self._lookahead_search(temp_board, self.depth - 1, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop) # Line 342
                elif self.ai_type == 'simple_search':
                    current_move_score = self.evaluate_position_from_perspective(temp_board, self.current_player)
                elif self.ai_type == 'evaluation_only':
                    current_move_score = self.evaluate_position_from_perspective(temp_board, self.current_player)
                elif self.ai_type == 'random':
                    best_move = self._random_search(self.board.copy(), self.current_player) # Line 348
                    search_duration = time.perf_counter() - search_start_time
                    if self.logging_enabled and self.logger:
                        self.logger.debug(f"Random search took {search_duration:.4f} seconds and searched {self.nodes_searched} nodes.")
                    return best_move
                else:
                    if self.show_thoughts and self.logger:
                        self.logger.warning(f"Unrecognized AI type '{self.ai_type}'. Falling back to _simple_search for score evaluation.")
                    current_move_score = self.evaluate_position_from_perspective(temp_board, self.current_player)
            except Exception as e:
                if self.logging_enabled and self.logger:
                    self.logger.error(f"Error in search algorithm '{self.ai_type}' for move {move}: {e}. Using immediate evaluation for this move. | FEN: {temp_board.fen()}")
                current_move_score = self.evaluate_position_from_perspective(temp_board, self.current_player)


            if self.current_player == chess.WHITE:
                if current_move_score > best_score_overall:
                    best_score_overall = current_move_score
                    best_move = move
            else:
                if current_move_score < best_score_overall:
                    best_score_overall = current_move_score
                    best_move = move
            
            self.update_transposition_table(self.board, self.depth, best_move, best_score_overall)

            if self.show_thoughts and self.logger:
                self.logger.debug(f"Root search iteration: Move={move}, Score={current_move_score:.2f}, Best Move So Far={best_move}, Best Score={best_score_overall:.2f}")

        if best_move == chess.Move.null() and legal_moves:
            best_move = random.choice(legal_moves)

        best_move = self._enforce_strict_draw_prevention(self.board, best_move)
        
        if not isinstance(best_move, chess.Move) or not self.board.is_legal(best_move):
            if self.logging_enabled and self.logger:
                self.logger.error(f"Invalid or illegal move detected after search: {best_move}. Selecting a random legal move as final fallback. | FEN: {self.board.fen()}")
            legal_moves = list(self.board.legal_moves)
            if legal_moves:
                best_move = random.choice(legal_moves)
            else:
                best_move = chess.Move.null()
        
        search_duration = time.perf_counter() - search_start_time
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Search for {self.current_player} took {search_duration:.4f} seconds and searched {self.nodes_searched} nodes.")

        return best_move

    # =================================
    # ===== EVALUATION FUNCTIONS ======

    def evaluate_position(self, board: chess.Board) -> float:
        """Calculate base position evaluation by delegating to scoring_calculator."""
        positional_evaluation_board = board.copy()
        if not isinstance(positional_evaluation_board, chess.Board) or not positional_evaluation_board.is_valid():
            if self.logger:
                self.logger.error(f"Invalid board state for evaluation: {positional_evaluation_board.fen() if hasattr(positional_evaluation_board, 'fen') else 'N/A'}")
            return 0.0
        
        endgame_factor = self._get_game_phase_factor(positional_evaluation_board)
        
        score = self.scoring_calculator.calculate_score(
            board=positional_evaluation_board,
            color=chess.WHITE,
            endgame_factor=endgame_factor
        ) - self.scoring_calculator.calculate_score(
            board=positional_evaluation_board,
            color=chess.BLACK,
            endgame_factor=endgame_factor
        )
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Position evaluation (delegated): {score:.3f} | FEN: {positional_evaluation_board.fen()} | Endgame Factor: {endgame_factor:.2f}")
        return score

    def evaluate_position_from_perspective(self, board: chess.Board, player: chess.Color) -> float:
        """Calculate position evaluation from specified player's perspective by delegating to scoring_calculator."""
        perspective_evaluation_board = board.copy()
        if not isinstance(player, chess.Color) or not perspective_evaluation_board.is_valid():
            if self.logger:
                self.logger.error(f"Invalid input for evaluation from perspective. Player: {player}, FEN: {perspective_evaluation_board.fen() if hasattr(perspective_evaluation_board, 'fen') else 'N/A'}")
            return 0.0
        
        endgame_factor = self._get_game_phase_factor(perspective_evaluation_board)

        white_score = self.scoring_calculator.calculate_score(
            board=perspective_evaluation_board,
            color=chess.WHITE,
            endgame_factor=endgame_factor
        )
        black_score = self.scoring_calculator.calculate_score(
            board=perspective_evaluation_board,
            color=chess.BLACK,
            endgame_factor=endgame_factor
        )
        
        score = (white_score - black_score) if player == chess.WHITE else (black_score - white_score)
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Position evaluation from {player} perspective (delegated): {score:.3f} | FEN: {perspective_evaluation_board.fen()} | Endgame Factor: {endgame_factor:.2f}")
        return score

    def evaluate_move(self, board: chess.Board, move: chess.Move = chess.Move.null()) -> float:
        """Quick evaluation of individual move on overall eval"""
        score = 0.0
        move_evaluation_board = board.copy()
        if not move_evaluation_board.is_legal(move):
            if self.logging_enabled and self.logger:
                self.logger.error(f"Attempted evaluation of an illegal move: {move} | FEN: {board.fen()}")
            return -9999999999
        
        move_evaluation_board.push(move)
        score = self.evaluate_position(move_evaluation_board)
        
        if self.show_thoughts and self.logger:
            self.logger.debug("Exploring the move: %s | Evaluation: %.3f | FEN: %s", move, score, board.fen())
        move_evaluation_board.pop()
        return score

    # ===================================
    # ======= HELPER FUNCTIONS ==========
    
    def order_moves(self, board: chess.Board, moves, hash_move: Optional[chess.Move] = None, depth: int = 0):
        """Order moves for better alpha-beta pruning efficiency"""
        if isinstance(moves, chess.Move):
            moves = [moves]
        
        if not moves or not isinstance(board, chess.Board) or not board.is_valid():
            if self.logger:
                self.logger.error(f"Invalid input to order_moves: board type {type(board)} | FEN: {board.fen() if hasattr(board, 'fen') else 'N/A'}")
            return []

        move_scores = []
        
        if hash_move and hash_move in moves:
            move_scores.append((hash_move, self.config.get('evaluation', {}).get('checkmate_move_bonus', 1000000.0) * 2))
            moves = [m for m in moves if m != hash_move]

        for move in moves:
            if not board.is_legal(move):
                if self.logger:
                    self.logger.warning(f"Illegal move passed to order_moves: {move} | FEN: {board.fen()}")
                continue
            
            score = self._order_move_score(board, move, depth)
            move_scores.append((move, score))

        move_scores.sort(key=lambda x: x[1], reverse=True)
        
        max_moves_to_evaluate = self.config.get('performance', {}).get('max_moves_evaluated', None)
        if max_moves_to_evaluate is not None and max_moves_to_evaluate > 0:
            if self.logging_enabled and self.logger:
                self.logger.debug(f"Limiting ordered moves from {len(move_scores)} to {max_moves_to_evaluate}")
            move_scores = move_scores[:max_moves_to_evaluate]

        if self.logging_enabled and self.logger:
            self.logger.debug(f"Ordered moves at depth {depth}: {[f'{move} ({score:.2f})' for move, score in move_scores]} | FEN: {board.fen()}")
        
        return [move for move, _ in move_scores]

    def _order_move_score(self, board: chess.Board, move: chess.Move, depth: int) -> float:
        score = 0.0

        temp_board = board.copy()
        temp_board.push(move)
        if temp_board.is_checkmate():
            temp_board.pop()
            return self.config.get('evaluation', {}).get('checkmate_move_bonus', 1000000.0)
        
        if temp_board.is_check():
            score += self.config.get('evaluation', {}).get('check_move_bonus', 10000.0)

        if board.is_capture(move):
            victim_piece_type = board.piece_type_at(move.to_square)
            aggressor_piece_type = board.piece_type_at(move.from_square)
            if victim_piece_type is not None and aggressor_piece_type is not None:
                victim_value = self.piece_values.get(victim_piece_type, 0)
                aggressor_value = self.piece_values.get(aggressor_piece_type, 0)
                score += self.config.get('evaluation', {}).get('capture_move_bonus', 4000.0) + (10 * victim_value - aggressor_value)
        
        if move.promotion:
            score += self.config.get('evaluation', {}).get('promotion_move_bonus', 3000.0)

        if depth < len(self.killer_moves) and move in self.killer_moves[depth]:
            score += self.config.get('evaluation', {}).get('killer_move_bonus', 2000.0)

        piece = board.piece_at(move.from_square)
        if piece is not None:
            history_key = (piece.piece_type, move.from_square, move.to_square)
            score += self.history_table.get(history_key, 0)
        
        temp_board.pop()

        return score
    
    def _quiescence_search(self, board: chess.Board, alpha: float, beta: float, depth: int = 0, stop_callback: Optional[Callable[[], bool]] = None) -> float:
        self.nodes_searched += 1
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn)

        if depth >= 5:
             return self.evaluate_position_from_perspective(board, board.turn)

        stand_pat = self.evaluate_position_from_perspective(board, board.turn)
        
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        quiescence_moves = []
        for move in board.legal_moves:
            if board.is_capture(move) or board.gives_check(move):
                quiescence_moves.append(move)

        if self.move_ordering_enabled:
            quiescence_moves = self.order_moves(board, quiescence_moves, depth=depth)

        for move in quiescence_moves:
            if stop_callback and stop_callback():
                break
            
            board.push(move)
            score = -self._quiescence_search(board, -beta, -alpha, depth + 1, stop_callback)
            board.pop()

            if score >= beta:
                self.update_killer_move(move, depth)
                return beta
            if score > alpha:
                alpha = score
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Quiescence search at depth {depth} | Alpha: {alpha} Beta: {beta} | Nodes searched: {self.nodes_searched}")
        
        return alpha
    
    def get_transposition_move(self, board: chess.Board, depth: int) -> Tuple[Optional[chess.Move], Optional[float]]:
        key = board.fen()
        if key in self.transposition_table:
            entry = self.transposition_table[key]
            if entry['depth'] >= depth:
                return entry['best_move'], entry['score']
        return None, None
    
    def update_transposition_table(self, board: chess.Board, depth: int, best_move: Optional[chess.Move], score: float):
        key = board.fen()
        if key in self.transposition_table:
            existing_entry = self.transposition_table[key]
            if depth < existing_entry['depth'] and score <= existing_entry['score']:
                return

        if best_move is not None:
            self.transposition_table[key] = {
                'best_move': best_move,
                'depth': depth,
                'score': score
            }

    def update_killer_move(self, move, ply): # Renamed depth to ply for clarity, as it's depth in current search tree
        """Update killer move table with a move that caused a beta cutoff"""
        if ply >= len(self.killer_moves): # Ensure ply is within bounds
            return
        
        if move not in self.killer_moves[ply]:
            self.killer_moves[ply].insert(0, move)
            self.killer_moves[ply] = self.killer_moves[ply][:2]

    def update_history_score(self, board, move, depth):
        """Update history heuristic score for a move that caused a beta cutoff"""
        piece = board.piece_at(move.from_square)
        if piece is None:
            return
        history_key = (piece.piece_type, move.from_square, move.to_square)

        # Update history score using depth-squared bonus
        self.history_table[history_key] = self.history_table.get(history_key, 0) + depth * depth

    def _enforce_strict_draw_prevention(self, board: chess.Board, move: Optional[chess.Move]) -> Optional[chess.Move]:
        """Enforce strict draw prevention rules to block moves that would lead to stalemate, insufficient material, or threefold repetition."""
        if not self.strict_draw_prevention or move is None:
            return move
        
        temp_board = board.copy()
        try:
            temp_board.push(move)
            if temp_board.is_stalemate() or temp_board.is_insufficient_material() or \
               temp_board.is_fivefold_repetition() or temp_board.is_repetition(count=3):
                
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Potential drawing move detected, enforcing strict draw prevention: {move} | FEN: {temp_board.fen()}")
                
                legal_moves_from_current_board = list(board.legal_moves)
                non_draw_moves = []
                for m in legal_moves_from_current_board:
                    if m == move:
                        continue
                    test_board_for_draw = board.copy()
                    test_board_for_draw.push(m)
                    if not (test_board_for_draw.is_stalemate() or test_board_for_draw.is_insufficient_material() or \
                            test_board_for_draw.is_fivefold_repetition() or test_board_for_draw.is_repetition(count=3)):
                        non_draw_moves.append(m)
                
                if non_draw_moves:
                    chosen_move = random.choice(non_draw_moves)
                    if self.logger:
                        self.logger.info(f"Strict draw prevention: Move {move} would result in a draw, replaced with {chosen_move}")
                    return chosen_move
                else:
                    if self.logger:
                        self.logger.info(f"Strict draw prevention: All legal moves result in draw, playing {move}")
                    return move
        except ValueError:
            if self.logger:
                self.logger.error(f"Draw prevention check encountered illegal move: {move} for FEN: {board.fen()}")
            return move

    # =======================================
    # ======= MAIN SEARCH ALGORITHMS ========
    
    def _random_search(self, board: chess.Board, player: chess.Color) -> chess.Move:
        """Select a random legal move from the board."""
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"No legal moves available for {player} | FEN: {board.fen()}")
            return chess.Move.null() # Return null move if no legal moves
        move = random.choice(legal_moves)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Randomly selected move: {move} | FEN: {board.fen()}")
        return move

    def _evaluation_only(self, board: chess.Board) -> float:
        """Evaluate the current position without searching"""
        evaluation = 0.0
        evaluation_only_board = board.copy()  # Work on a copy of the board
        try:
            evaluation = self.evaluate_position(evaluation_only_board)
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Evaluation only for position: {evaluation_only_board.fen()} score: {evaluation:.3f} ")
        except Exception as e:
            if self.show_thoughts and self.logger:
                self.logger.error(f"Error during evaluation only for position: {evaluation_only_board.fen()} | Error: {e}")
        return evaluation

    def _simple_search(self, board: chess.Board) -> chess.Move:
        """Simple search that evaluates all legal moves and picks the best one at 1 ply.
           This also serves as a fallback search.
        """
        best_move = chess.Move.null()
        # Initialize best_score to negative infinity for white, positive infinity for black for proper min/max
        best_score = -float('inf') if board.turn == chess.WHITE else float('inf')
        
        simple_search_board = board.copy()  # Work on a copy of the board

        legal_moves = list(simple_search_board.legal_moves)
        if not legal_moves:
            return chess.Move.null() # No legal moves, likely game over

        if self.move_ordering_enabled:
            legal_moves = self.order_moves(simple_search_board, legal_moves)
        
        for move in legal_moves:
            if self.time_manager.should_stop(self.depth, self.nodes_searched):
                break # Stop if time is up
            
            self.nodes_searched += 1 # Increment nodes searched
            
            temp_board = simple_search_board.copy()
            temp_board.push(move)
            
            score = self.evaluate_position_from_perspective(temp_board, simple_search_board.turn)
            
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Simple search evaluating move: {move} | Score: {score:.3f} | Best score: {best_score:.3f} | FEN: {temp_board.fen()}")

            if simple_search_board.turn == chess.WHITE: # Maximizing player
                if score > best_score:
                    best_score = score
                    best_move = move
            else: # Minimizing player
                if score < best_score:
                    best_score = score
                    best_move = move
            
        return best_move

    def _lookahead_search(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None) -> float:
        """Lookahead search with static depth. Returns score (float)."""
        self.nodes_searched += 1 # Increment nodes searched
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn)

        # Check transposition table
        tt_move, tt_score = self.get_transposition_move(board, depth)
        if tt_score is not None:
            return tt_score

        if depth == 0 or board.is_game_over(claim_draw=self._is_draw_condition(board)):
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, 0, stop_callback)
            else:
                return self.evaluate_position_from_perspective(board, board.turn)

        best_score = -float('inf') # Always maximizing from the current player's perspective

        legal_moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(board, legal_moves, hash_move=tt_move, depth=depth)

        for move in legal_moves:
            board.push(move)
            # Recursive call: _lookahead_search only returns score (float)
            score = -self._lookahead_search(board, depth - 1, -beta, -alpha, stop_callback)
            board.pop()

            if score > best_score:
                best_score = score
                # Update transposition table for this node (store best move found at this sub-node)
                self.update_transposition_table(board, depth, move, best_score) # Store move from THIS node
                
            alpha = max(alpha, best_score)
            if alpha >= beta:
                self.update_killer_move(move, depth)
                self.update_history_score(board, move, depth) # Update history for cutoff moves
                break # Alpha-beta cutoff
        
        return best_score

    def _minimax_search(self, board: chess.Board, depth: int, alpha: float, beta: float, maximizing_player: bool, stop_callback: Optional[Callable[[], bool]] = None) -> float:
        """Minimax search with alpha-beta pruning. Returns score (float)."""
        self.nodes_searched += 1 # Increment nodes searched
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn) # Return immediate eval if stopping

        # Check transposition table
        tt_move, tt_score = self.get_transposition_move(board, depth)
        if tt_score is not None:
            return tt_score

        if depth == 0 or board.is_game_over(claim_draw=self._is_draw_condition(board)):
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, 0, stop_callback)
            else:
                return self.evaluate_position_from_perspective(board, board.turn)

        best_score = -float('inf') if maximizing_player else float('inf')
        
        legal_moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(board, legal_moves, hash_move=tt_move, depth=depth)

        for move in legal_moves:
            board.push(move)
            # Recursive call: _minimax_search now always returns a score (float)
            score = self._minimax_search(board, depth-1, alpha, beta, not maximizing_player, stop_callback)
            board.pop()

            if maximizing_player:
                if score > best_score:
                    best_score = score
            else: # Minimizing player
                if score < best_score:
                    best_score = score
            
            # Alpha-beta pruning update
            if maximizing_player:
                alpha = max(alpha, score)
                if alpha >= beta:
                    self.update_killer_move(move, depth)
                    self.update_history_score(board, move, depth) # Update history for cutoff moves
                    break # Alpha-beta cutoff
            else: # Minimizing player
                beta = min(beta, score)
                if alpha >= beta:
                    break # Alpha-beta cutoff
        
        # Update transposition table for this node (store best move encountered during this sub-search)
        # Note: best_move itself is not directly propagated from sub-searches, but the score is.
        # The best_move at the root is determined by iterating and comparing scores.
        # This update stores the best score *for this position* at this depth.
        # The `best_move` parameter in update_transposition_table would need to be the actual move
        # that led to this `best_score` in this node's search, but for recursive calls returning only score,
        # that move is implicitly handled by the parent call choosing it.
        # A simple approach is to always store the move that *achieved* the best score at this sub-search level,
        # which is what `best_move_for_tt` would track.
        # For simplicity here, we rely on the root `search` function to manage the overall best_move.
        # Or, pass the best_move found *within this recursive call* to update_transposition_table.
        # For now, let's just store the score. If TT hit is only `trans_score`, then it's fine.
        
        # To store best move for this sub-search level, need a local best_move variable here.
        # Example:
        # best_move_for_tt = chess.Move.null()
        # ... update best_move_for_tt when score is better ...
        # self.update_transposition_table(board, depth, best_move_for_tt, best_score)
        
        # Keeping it simple for now, as the root search is handling overall best_move tracking.
        return best_score

    def _negamax_search(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None) -> float:
        """Negamax search with alpha-beta pruning. Returns score (float)."""
        self.nodes_searched += 1
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn)

        # Check transposition table
        tt_move, tt_score = self.get_transposition_move(board, depth)
        if tt_score is not None:
            return tt_score

        if depth == 0 or board.is_game_over(claim_draw=self._is_draw_condition(board)):
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, 0, stop_callback)
            else:
                return self.evaluate_position_from_perspective(board, board.turn)

        best_score = -float('inf')
        
        legal_moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(board, legal_moves, hash_move=tt_move, depth=depth)

        for move in legal_moves:
            board.push(move)
            # Recursive call: _negamax_search now always returns a score (float)
            score = -self._negamax_search(board, depth-1, -beta, -alpha, stop_callback)
            board.pop()

            if score > best_score:
                best_score = score
            
            alpha = max(alpha, score)
            if alpha >= beta:
                self.update_killer_move(move, depth)
                self.update_history_score(board, move, depth) # Update history for cutoff moves
                break # Alpha-beta cutoff

        # Update transposition table for this node (store best score encountered during this sub-search)
        # Best move from recursive call is not explicitly propagated here, just the score.
        # Rely on the root search function to track the actual best_move.
        return best_score

    def _negascout(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None) -> float:
        """Negascout search with alpha-beta pruning (Principal Variation Search). Returns score (float)."""
        self.nodes_searched += 1
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn)

        # Check transposition table
        tt_move, tt_score = self.get_transposition_move(board, depth)
        if tt_score is not None:
            return tt_score

        if depth == 0 or board.is_game_over(claim_draw=self._is_draw_condition(board)):
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, 0, stop_callback)
            else:
                return self.evaluate_position_from_perspective(board, board.turn)

        best_score = -float('inf')
        first_move = True

        legal_moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(board, legal_moves, hash_move=tt_move, depth=depth)

        for move in legal_moves:
            board.push(move)
            if first_move:
                # Recursive call: _negascout now always returns a score (float)
                score = -self._negascout(board, depth-1, -beta, -alpha, stop_callback)
            else:
                # Null window search (zero window search)
                score = -self._negascout(board, depth-1, -alpha-1, -alpha, stop_callback)
                
                # If the score is within the (alpha, beta) window, re-search with full window
                if alpha < score < beta:
                    score = -self._negascout(board, depth-1, -beta, -score, stop_callback)
            
            board.pop()

            if score > best_score:
                best_score = score
            
            alpha = max(alpha, score)
            if alpha >= beta:
                self.update_killer_move(move, depth)
                self.update_history_score(board, move, depth)
                break # Alpha-beta cutoff
            
            first_move = False
        
        # Update transposition table for this node (store best score encountered during this sub-search)
        return best_score
    
    def _deep_search(self, board: chess.Board, initial_depth: int, time_control: Dict[str, Any], stop_callback: Optional[Callable[[], bool]] = None) -> chess.Move:
        """
        Perform a search with iterative deepening, move ordering, quiescence search, and dynamic search depth.
        Returns only the best move found at the root.
        """
        best_move_root = chess.Move.null() # The best move found at the root of the search
        best_score_root = -float('inf')

        # Use the max_depth from AI config, ensuring it's not less than initial_depth
        max_search_depth = max(initial_depth, self.max_depth)
        
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return chess.Move.null() # No legal moves, likely game over
        if len(legal_moves) == 1:
            return legal_moves[0] # Only one move, no need to search

        # Iterative Deepening Loop
        for current_depth in range(1, max_search_depth + 1):
            if stop_callback and stop_callback():
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Deepsearch stopped due to time limit at depth {current_depth-1}.")
                break # Stop if time runs out

            if self.time_manager.should_stop(current_depth, self.nodes_searched):
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Deepsearch stopped by time manager at depth {current_depth-1}.")
                break # Stop if time manager says so

            # Re-order moves at each iteration if move ordering is enabled
            if self.move_ordering_enabled:
                # Get hash move from transposition table for current board state
                hash_move, _ = self.get_transposition_move(board, current_depth)
                ordered_moves = self.order_moves(board, legal_moves, hash_move=hash_move, depth=current_depth)
            else:
                ordered_moves = legal_moves

            local_best_move_at_depth = chess.Move.null()
            local_best_score_at_depth = -float('inf')

            # Alpha and Beta for the current iteration
            alpha = -float('inf')
            beta = float('inf')

            for move in ordered_moves:
                if stop_callback and stop_callback():
                    break # Stop if time is up mid-iteration

                temp_board = board.copy()
                temp_board.push(move)
                
                # Recursive call to negamax (or negascout, or minimax)
                # _negamax_search now always returns a score (float)
                current_move_score = -self._negamax_search(temp_board, current_depth - 1, -beta, -alpha, stop_callback)

                if current_move_score > local_best_score_at_depth:
                    local_best_score_at_depth = current_move_score
                    local_best_move_at_depth = move
                
                alpha = max(alpha, current_move_score) # Update alpha for the next sibling move
                if alpha >= beta:
                    # Beta cutoff, update killer and history
                    self.update_killer_move(move, current_depth)
                    self.update_history_score(board, move, current_depth)
                    break # Prune remaining moves at this depth
            
            # After each full depth iteration, update the overall best move
            if local_best_move_at_depth != chess.Move.null():
                best_move_root = local_best_move_at_depth
                best_score_root = local_best_score_at_depth
                # Store the best move found at this depth in transposition table
                self.update_transposition_table(board, current_depth, best_move_root, best_score_root)

            # If checkmate is found, stop early
            if abs(best_score_root) > self.config.get('evaluation', {}).get('checkmate_bonus', 1000000.0) / 2: # Checkmate score is very high
                if self.logging_enabled and self.logger:
                    self.logger.info(f"Deepsearch found a potential checkmate at depth {current_depth}. Stopping early.")
                break

            if self.show_thoughts and self.logger:
                self.logger.debug(f"Deepsearch finished depth {current_depth}: Best move {best_move_root} with score {best_score_root:.2f}")

        return best_move_root if best_move_root != chess.Move.null() else self._simple_search(board) # Fallback if no move found

    
    # ================================
    # ======= DEBUG AND TESTING =======
    
    def debug_evaluate_position(self, fen_position) -> Optional[float]:
        try:
            board = chess.Board(fen_position)
            return self.evaluate_position(board)
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Error in debug_evaluate_position: {e}")
            return None

    def debug_order_moves(self, fen_position: str, moves: list):
        try:
            board = chess.Board(fen_position)
            parsed_moves = []
            for m in moves:
                try:
                    parsed_moves.append(chess.Move.from_uci(m) if isinstance(m, str) else m)
                except ValueError:
                    if self.logger:
                        self.logger.warning(f"Invalid move in debug_order_moves input: {m}")
                    continue
            return self.order_moves(board, parsed_moves, depth=1)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in debug_order_moves: {e}")
            return []


# Example usage and testing
if __name__ == "__main__":
    import logging
    import logging.handlers
    import random
    from typing import Callable, Dict, Any, Optional, Tuple

    test_logger = logging.getLogger("test_viper_evaluation_engine")
    test_logger.setLevel(logging.DEBUG)
    if not test_logger.handlers:
        ch = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        test_logger.addHandler(ch)

    print("--- ViperEvaluationEngine Test ---")

    try:
        board = chess.Board()
        engine = ViperEvaluationEngine(board, chess.WHITE)
        score = engine.evaluate_position(board)
        print(f"Initial Evaluation: {score:.3f}")
        assert score is not None, "Initial evaluation failed"
        assert isinstance(score, float), "Evaluation score is not a float"
        print("Test 1: Basic Initialization and Evaluation - PASSED")
    except Exception as e:
        print(f"Test 1: Basic Initialization and Evaluation - FAILED: {e}")

    try:
        board.reset()
        engine.reset(board)
        engine.ai_type = 'deepsearch'
        engine.depth = 3
        
        print(f"\n--- Test 2: Searching for White move (AI Type: {engine.ai_type}, Depth: {engine.depth}) ---")
        best_move = engine.search(board.copy(), chess.WHITE)
        print(f"Best move found by deepsearch: {best_move}")
        assert best_move is not None and isinstance(best_move, chess.Move), "Search did not return a valid move"
        assert board.is_legal(best_move), "Search returned an illegal move"
        print("Test 2: Search for a move - PASSED")
    except Exception as e:
        print(f"Test 2: Search for a move - FAILED: {e}")

    try:
        endgame_fen = "8/8/8/8/4k3/4K3/8/8 w - - 0 1"
        endgame_board = chess.Board(endgame_fen)
        engine_eg = ViperEvaluationEngine(endgame_board, chess.WHITE)
        engine_eg.game_phase_awareness = True

        initial_eval_eg = engine_eg.evaluate_position(endgame_board)
        print(f"\n--- Test 3: Endgame Phase Awareness for FEN: {endgame_fen} ---")
        endgame_factor = engine_eg._get_game_phase_factor(endgame_board)
        print(f"Endgame Factor for board: {endgame_factor:.2f}")
        assert endgame_factor > 0.0, "Endgame factor not correctly identified"
        
        king_white_e4_mg_val = engine_eg.pst.get_piece_value(chess.Piece(chess.KING, chess.WHITE), chess.E4, chess.WHITE, endgame_factor=0.0)
        king_white_e4_eg_val = engine_eg.pst.get_piece_value(chess.Piece(chess.KING, chess.WHITE), chess.E4, chess.WHITE, endgame_factor=1.0)
        print(f"King on e4 (MG): {king_white_e4_mg_val}, (EG): {king_white_e4_eg_val}")
        assert king_white_e4_eg_val > king_white_e4_mg_val, "King PST not encouraging centralization in endgame"

        print("Test 3: Endgame Phase Awareness - PASSED")
    except Exception as e:
        print(f"Test 3: Endgame Phase Awareness - FAILED: {e}")
        
    try:
        board.reset()
        engine_tt = ViperEvaluationEngine(board, chess.WHITE)
        engine_tt.ai_type = 'negamax'
        engine_tt.depth = 2
        engine_tt.transposition_table.clear()

        print("\n--- Test 4: Transposition Table Usage ---")
        best_move_tt = engine_tt.search(board.copy(), chess.WHITE) 
        score_from_tt_entry = None
        if board.fen() in engine_tt.transposition_table:
            tt_entry = engine_tt.transposition_table[board.fen()]
            score_from_tt_entry = tt_entry.get('score')

        print(f"Initial search (via engine.search) for {board.fen()}: Move={best_move_tt}, TT Score={score_from_tt_entry}")
        
        engine_tt.nodes_searched = 0 
        found_move_via_tt = engine_tt.search(board.copy(), chess.WHITE)

        print(f"Second search (should hit TT) for {board.fen()}: Move={found_move_via_tt}, TT Score={score_from_tt_entry}")

        assert board.fen() in engine_tt.transposition_table, "Position not stored in transposition table"
        tt_entry = engine_tt.transposition_table[board.fen()]
        print(f"TT Entry: {tt_entry}")
        assert tt_entry['best_move'] == best_move_tt, "TT best move mismatch after second search"
        assert tt_entry['score'] is not None, "TT score should not be None"
        
        print("Test 4: Transposition Table Usage - PASSED")

    except Exception as e:
        print(f"Test 4: Transposition Table Usage - FAILED: {e}")

    try:
        tactical_fen = "rnbqkbnr/pp1ppp1p/6p1/2pP4/8/8/PPP1PPPP/RNBQKBNR w KQkq - 0 3"
        tactical_board = chess.Board(tactical_fen)
        engine_q = ViperEvaluationEngine(tactical_board, chess.WHITE)
        engine_q.quiescence_enabled = True
        engine_q.ai_type = 'deepsearch'

        print(f"\n--- Test 5: Quiescence Search for FEN: {tactical_fen} ---")
        q_score = engine_q._quiescence_search(tactical_board.copy(), -float('inf'), float('inf'))
        print(f"Quiescence search score: {q_score}")
        assert q_score is not None, "Quiescence search returned None"
        print("Test 5: Quiescence Search - PASSED")
    except Exception as e:
        print(f"Test 5: Quiescence Search - FAILED: {e}")

    try:
        board_fallback = chess.Board()
        engine_fb = ViperEvaluationEngine(board_fallback, chess.WHITE)
        engine_fb.ai_type = 'non_existent_ai_type'
        engine_fb.depth = 0

        print("\n--- Test 6: Fallback to _simple_search for invalid AI type ---")
        fallback_move = engine_fb.search(board_fallback.copy(), chess.WHITE)
        print(f"Fallback move: {fallback_move}")
        assert fallback_move is not None and isinstance(fallback_move, chess.Move), "Fallback did not return a valid move"
        assert board_fallback.is_legal(fallback_move), "Fallback returned an illegal move"
        print("Test 6: Fallback to _simple_search - PASSED")
    except Exception as e:
        print(f"Test 6: Fallback to _simple_search - FAILED: {e}")

    try:
        board_opening = chess.Board()
        engine_opening = ViperEvaluationEngine(board_opening, chess.WHITE)
        engine_opening.solutions_enabled = True
        
        print("\n--- Test 7: Opening Book Lookup ---")
        
        book_moves_data = engine_opening.opening_book.book.get(board_opening.fen(), [])
        expected_book_moves = [move for move, _ in book_moves_data]

        if expected_book_moves:
            print(f"Possible book moves for initial position: {[m.uci() for m in expected_book_moves]}")
            found_move = engine_opening.search(board_opening.copy(), chess.WHITE)
            print(f"Search returned: {found_move}")
            
            assert found_move in expected_book_moves, f"Opening book move not returned. Expected one of {expected_book_moves}, got {found_move}"
            print("Test 7: Opening Book Lookup - PASSED")
        else:
            print("Skipping Test 7: No opening book move found for starting position in book data. Please ensure opening_book.py has entries for the initial board.")
            print("Test 7: Opening Book Lookup - SKIPPED")
    except Exception as e:
        print(f"Test 7: Opening Book Lookup - FAILED: {e}")

    print("\n--- All ViperEvaluationEngine Tests Complete ---")