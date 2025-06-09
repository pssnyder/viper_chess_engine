# viper_scoring_calculation.py

""" Viper Scoring Calculation Module
This module implements the scoring calculation for the Viper Chess Engine.
It provides various scoring functions for evaluation, quiescence, and move ordering
"""
# TODO: Refactor this module to use the new ruleset system and configuration management

import chess
import yaml # Keep for config loading if needed directly, though passed via init now
import random
import logging
import os
import threading # TODO enable parallel score calculations via threading
from engine_utilities.piece_square_tables import PieceSquareTables # Need this for PST evaluation
from engine_utilities.time_manager import TimeManager # May not be directly needed here, but kept for context if sub-fns rely on it
from engine_utilities.opening_book import OpeningBook # Not directly needed here, but kept for context

# At module level, define a single logger for this file
# This logger will be used by ViperScoringCalculation, separate from main engine logger
scoring_logger = logging.getLogger("viper_scoring_calculation")
scoring_logger.setLevel(logging.DEBUG)
if not scoring_logger.handlers:
    if not os.path.exists('logging'):
        os.makedirs('logging', exist_ok=True)
    from logging.handlers import RotatingFileHandler
    log_file_path = "logging/viper_scoring_calculation.log" # New log file for scoring
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
    scoring_logger.addHandler(file_handler)
    scoring_logger.propagate = False


class ViperScoringCalculation:
    """
    Encapsulates all evaluation scoring functions for the Viper Chess Engine.
    Allows for dynamic selection of evaluation rulesets.
    """
    def __init__(self, viper_yaml_config: dict, ai_config: dict, piece_values: dict, pst: PieceSquareTables):
        # viper_yaml_config is the parsed content of viper.yaml (specifically the 'viper' key)
        self.viper_config = viper_yaml_config 
        self.ai_config = ai_config # This is the resolved AI config for the current player/search
        self.piece_values = piece_values
        self.pst = pst

        # Ruleset and scoring modifier are determined by the resolved ai_config
        self.ruleset_name = self.ai_config.get('ruleset', self.viper_config.get('ruleset', 'default_evaluation'))
        self.scoring_modifier = self.ai_config.get('scoring_modifier', self.viper_config.get('scoring_modifier', 1.0))
        
        # PST settings from resolved ai_config (which considers viper_config and player specifics)
        self.pst_enabled = self.ai_config.get('pst', {}).get('enabled', True)
        self.pst_weight = self.ai_config.get('pst', {}).get('weight', 1.0)

        # Logging setup - use global monitoring settings from ai_config if available, else viper_config
        # Assuming ai_config might carry 'monitoring' settings from chess_game.yaml if relevant here
        # For simplicity, let's assume viper_config's debug/logging is primary for scoring module's own logs
        viper_debug_settings = self.viper_config.get('debug', {})
        self.logging_enabled = viper_debug_settings.get('enable_scoring_logs', False) # More specific key
        self.show_thoughts = viper_debug_settings.get('show_scoring_details', False) # More specific key
        self.logger = scoring_logger
        if not self.logging_enabled:
            self.logger.disabled = True

        # Load all rulesets defined in viper_yaml_config under the 'rulesets' key
        self.rulesets = self.viper_config.get('rulesets', {})
        # Add 'default_evaluation' if it's defined at the top level of viper_config and not in rulesets
        if 'default_evaluation' in self.viper_config and 'default_evaluation' not in self.rulesets:
            self.rulesets['default_evaluation'] = self.viper_config.get('default_evaluation', {})
        
        # Ensure the selected ruleset exists, fallback to a default or an empty dict
        if self.ruleset_name not in self.rulesets:
            self.logger.warning(f"Ruleset '{self.ruleset_name}' not found in viper_config. Falling back to an empty ruleset for '{self.ruleset_name}'.")
            self.rulesets[self.ruleset_name] = {} # Create an empty ruleset to avoid errors
        self.current_ruleset = self.rulesets.get(self.ruleset_name, {})
        
        if self.logging_enabled:
            self.logger.debug(f"ViperScoringCalculation initialized. Effective AI Config: {self.ai_config}")
            self.logger.debug(f"Using ruleset: '{self.ruleset_name}'. Rules: {self.current_ruleset}")
            self.logger.debug(f"PST Enabled: {self.pst_enabled}, PST Weight: {self.pst_weight}")

    def _get_rule_value(self, rule_key: str, default_value: float = 0.0) -> float:
        """Helper to safely get a rule value from the current ruleset."""
        # Fallback to viper_config's top-level 'default_evaluation' if key not in current_ruleset
        # then to the hardcoded default_value.
        value = self.current_ruleset.get(rule_key)
        if value is None: # Key not in specific ruleset
            # Check in viper_config's 'default_evaluation' as a global fallback for rules
            default_eval_rules = self.viper_config.get('default_evaluation', {})
            value = default_eval_rules.get(rule_key, default_value)
            if self.logging_enabled and value != default_value:
                 self.logger.debug(f"Rule '{rule_key}' not in ruleset '{self.ruleset_name}', using value from default_evaluation: {value}")
            elif self.logging_enabled and value == default_value and rule_key not in default_eval_rules:
                 self.logger.debug(f"Rule '{rule_key}' not in ruleset '{self.ruleset_name}' or default_evaluation, using hardcoded default: {default_value}")
        return value

    # Renamed from _calculate_score to calculate_score to be the public API
    def calculate_score(self, board: chess.Board, color: chess.Color, endgame_factor: float = 0.0) -> float:
        """
        Calculates the position evaluation score for a given board and color,
        applying dynamic ruleset settings and endgame awareness.
        This is the main public method for this class.
        """
        score = 0.0

        # Ensure the current ruleset is up-to-date based on ai_config (in case it changed)
        # This is important if the same ViperScoringCalculation instance is used across different contexts
        # where ai_config might change (e.g. switching sides or re-configuring mid-game if that's a feature)
        current_ruleset_name_from_ai_config = self.ai_config.get('ruleset', self.viper_config.get('ruleset', 'default_evaluation'))
        if self.ruleset_name != current_ruleset_name_from_ai_config:
            self.ruleset_name = current_ruleset_name_from_ai_config
            if self.ruleset_name not in self.rulesets:
                self.logger.warning(f"Ruleset '{self.ruleset_name}' (from updated ai_config) not found. Using empty ruleset.")
                self.current_ruleset = {}
            else:
                self.current_ruleset = self.rulesets.get(self.ruleset_name, {})
            if self.logging_enabled:
                self.logger.debug(f"Switched to ruleset: '{self.ruleset_name}'. Rules: {self.current_ruleset}")
        
        # Update other relevant parameters from ai_config
        self.scoring_modifier = self.ai_config.get('scoring_modifier', self.viper_config.get('scoring_modifier', 1.0))
        self.pst_enabled = self.ai_config.get('pst', {}).get('enabled', True)
        self.pst_weight = self.ai_config.get('pst', {}).get('weight', 1.0)

        # Critical scoring components
        score += self.scoring_modifier * (self._checkmate_threats(board, color) or 0.0)
        score += self.scoring_modifier * (self._king_safety(board, color) or 0.0)
        score += self.scoring_modifier * (self._king_threat(board, color) or 0.0)
        score += self.scoring_modifier * (self._draw_scenarios(board) or 0.0)

        # Material and piece-square table evaluation
        score += self.scoring_modifier * self._material_score(board, color)
        if self.pst_enabled:
            # Pass endgame_factor directly to PST evaluation
            # The PST evaluation itself should be color-aware or return a neutral score
            # that is then interpreted by the caller (ViperEvaluationEngine.evaluate_position)
            # For now, assuming pst.evaluate_board_position gives a score from White's perspective.
            # If calculate_score is for a specific color, PST score might need adjustment if it's neutral.
            # Let's assume pst.evaluate_board_position is neutral and needs to be perspectivized if color is BLACK.
            pst_board_score = self.pst.evaluate_board_position(board, endgame_factor) # This is likely from White's perspective
            if color == chess.BLACK:
                pst_board_score = -pst_board_score # Adjust if PST is always White-centric
            score += self.scoring_modifier * self.pst_weight * pst_board_score

        # Piece coordination and control
        score += self.scoring_modifier * (self._piece_coordination(board, color) or 0.0)
        score += self.scoring_modifier * (self._center_control(board, color) or 0.0)
        score += self.scoring_modifier * (self._pawn_structure(board, color) or 0.0)
        score += self.scoring_modifier * (self._pawn_weaknesses(board, color) or 0.0)
        score += self.scoring_modifier * (self._passed_pawns(board, color) or 0.0)
        score += self.scoring_modifier * (self._pawn_majority(board, color) or 0.0)
        score += self.scoring_modifier * (self._bishop_pair(board, color) or 0.0)
        score += self.scoring_modifier * (self._knight_pair(board, color) or 0.0)
        score += self.scoring_modifier * (self._bishop_vision(board, color) or 0.0)
        score += self.scoring_modifier * (self._rook_coordination(board, color) or 0.0)
        score += self.scoring_modifier * (self._castling_evaluation(board, color) or 0.0)

        # Piece development and mobility
        score += self.scoring_modifier * (self._piece_activity(board, color) or 0.0)
        score += self.scoring_modifier * (self._improved_minor_piece_activity(board, color) or 0.0)
        score += self.scoring_modifier * (self._mobility_score(board, color) or 0.0)
        score += self.scoring_modifier * (self._undeveloped_pieces(board, color) or 0.0)

        # Tactical and strategic considerations
        score += self.scoring_modifier * (self._tactical_evaluation(board, color) or 0.0)
        score += self.scoring_modifier * (self._tempo_bonus(board, color) or 0.0)
        score += self.scoring_modifier * (self._special_moves(board, color) or 0.0) # Pass color
        score += self.scoring_modifier * (self._open_files(board, color) or 0.0)
        score += self.scoring_modifier * (self._stalemate(board) or 0.0)

        if self.show_thoughts and self.logging_enabled:
            self.logger.debug(f"Final score for {color}: {score:.3f} (Ruleset: {self.ruleset_name}, Modifier: {self.scoring_modifier}) | FEN: {board.fen()}")

        return score

    # ==========================================
    # ========= RULE SCORING FUNCTIONS =========
    # These functions are now methods of ViperScoringCalculation
    # and access their rule values via self._get_rule_value()

    def _checkmate_threats(self, board: chess.Board, color: chess.Color) -> float:
        score = 0.0
        # Only check threats for the current player's turn to avoid double counting
        # or checking irrelevant checks for the given 'color' if not their turn.
        # This function should assess if 'color' can deliver a checkmate on their *next* move.
        original_turn = board.turn
        # Only consider pseudo-legal moves for the correct color
        try:
            # Use a copy so we don't mutate the original board
            board_copy = board.copy()
            board_copy.turn = color
            for move in board_copy.pseudo_legal_moves:
                # Only consider moves that are legal (pseudo-legal may include illegal under check)
                if not board_copy.is_legal(move):
                    continue
                board_copy.push(move)
                if board_copy.is_checkmate():
                    score += self._get_rule_value('checkmate_bonus', 0)
                    board_copy.pop()
                    # If a checkmate is found, we can break and return the bonus.
                    # However, a common heuristic might be to give the bonus to the side *delivering* mate.
                    # This function implies it's for `color` to *threaten* mate to opponent.
                    # So the `board.turn` in `board.is_checkmate()` should be the *opponent's* turn after `move` is pushed.
                    if board_copy.turn != color: # If the checkmate is on the *opponent's* king
                        return score # Return immediately
                else:
                    board_copy.pop()
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in _checkmate_threats: {e} | FEN: {board.fen()}")
        return score

    def _draw_scenarios(self, board: chess.Board) -> float:
        score = 0.0
        if board.is_stalemate() or board.is_insufficient_material() or board.is_fivefold_repetition() or board.is_repetition(count=2):
            score += self._get_rule_value('draw_penalty', -9999999999.0)
        return score

    def _material_score(self, board: chess.Board, color: chess.Color) -> float:
        """Simple material count for given color"""
        score = 0.0
        for piece_type, value in self.piece_values.items():
            score += len(board.pieces(piece_type, color)) * value
        # Apply material weight from ruleset
        return score * self._get_rule_value('material_weight', 1.0)
    
    # This method is correctly called directly from self.pst.evaluate_board_position in calculate_score

    def _improved_minor_piece_activity(self, board: chess.Board, color: chess.Color) -> float:
        """
        Mobility calculation with safe squares for Knights and Bishops.
        """
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            safe_moves = 0
            # Iterate through squares attacked by the knight
            for target in board.attacks(square):
                # Check if the target square is not attacked by enemy pawns
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self._get_rule_value('knight_activity_bonus', 0.0)

        for square in board.pieces(chess.BISHOP, color):
            safe_moves = 0
            for target in board.attacks(square):
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self._get_rule_value('bishop_activity_bonus', 0.0)

        return score

    def _tempo_bonus(self, board: chess.Board, color: chess.Color) -> float:
        """If it's the player's turn and the game is still ongoing, give a small tempo bonus"""
        # The 'current_player' attribute is from EvaluationEngine, need to pass it or infer.
        # This method is part of scoring specific 'color'. So, if it's 'color's turn.
        if board.turn == color and not board.is_game_over() and board.is_valid():
            return self._get_rule_value('tempo_bonus', 0.0)
        return 0.0

    def _is_attacked_by_pawn(self, board: chess.Board, square: chess.Square, by_color: chess.Color) -> bool:
        """Helper function to check if a square is attacked by enemy pawns"""
        # Check if any of the attackers of 'square' from 'by_color' are pawns.
        for attacker_square in board.attackers(by_color, square):
            piece = board.piece_at(attacker_square)
            if piece and piece.piece_type == chess.PAWN:
                return True
        return False

    def _center_control(self, board: chess.Board, color: chess.Color) -> float:
        """Simple center control"""
        score = 0.0
        center = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center:
            # Check if current player controls (has a piece on) center square
            piece = board.piece_at(square)
            if piece and piece.color == color:
                score += self._get_rule_value('center_control_bonus', 0.0)
        return score

    def _piece_activity(self, board: chess.Board, color: chess.Color) -> float:
        """Mobility and attack patterns"""
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            score += len(list(board.attacks(square))) * self._get_rule_value('knight_activity_bonus', 0.0)

        for square in board.pieces(chess.BISHOP, color):
            score += len(list(board.attacks(square))) * self._get_rule_value('bishop_activity_bonus', 0.0)

        return score

    def _king_safety(self, board: chess.Board, color: chess.Color) -> float:
        score = 0.0
        king_square = board.king(color)
        if king_square is None:
            return score

        king_file = chess.square_file(king_square)
        king_rank = chess.square_rank(king_square)

        # Define squares for pawn shield relative to king's current rank
        # Consider pawns on the two ranks in front of the king for a shield
        shield_ranks = []
        if color == chess.WHITE:
            if king_rank < 7: shield_ranks.append(king_rank + 1)
            if king_rank < 6: shield_ranks.append(king_rank + 2) # For king on 1st rank
        else: # Black
            if king_rank > 0: shield_ranks.append(king_rank - 1)
            if king_rank > 1: shield_ranks.append(king_rank - 2) # For king on 8th rank

        for rank_offset in shield_ranks:
            for file_offset in [-1, 0, 1]: # Check adjacent files too
                target_file = king_file + file_offset
                if 0 <= target_file <= 7 and 0 <= rank_offset <= 7:
                    shield_square = chess.square(target_file, rank_offset)
                    piece = board.piece_at(shield_square)
                    if piece and piece.piece_type == chess.PAWN and piece.color == color:
                        score += self._get_rule_value('king_safety_bonus', 0.0)
        
        return score

    def _king_threat(self, board: chess.Board, color: chess.Color) -> float:
        """
        Evaluate if the opponent's king is under threat (in check) from 'color'.
        Adds a penalty/bonus if the specified 'color' is giving or receiving check.
        """
        score = 0.0
        # Check if the board is in check.
        if board.is_check():
            # If it's 'color's turn AND 'color' just caused check (i.e., opponent is in check)
            # This is hard to tell from `board.turn` directly without knowing the previous move.
            # Simpler: if `color` is the one whose turn it is AND the board IS in check, it means
            # the *opponent* of `color` is in check (from previous move).
            # If `color` is the one whose turn it is NOT AND the board IS in check, it means
            # `color` itself is in check.
            
            # This method calculates score from the perspective of 'color'
            if board.turn != color: # If it's *not* 'color's turn, and board is in check, 'color' is in check
                score += self._get_rule_value('in_check_penalty', 0.0)
            else: # If it *is* 'color's turn, and board is in check, then 'color' just gave check
                score += self._get_rule_value('check_bonus', 0.0)
        return score

    def _undeveloped_pieces(self, board: chess.Board, color: chess.Color) -> float:
        score = 0.0
        undeveloped_count = 0.0

        starting_squares = {
            chess.WHITE: {chess.KNIGHT: [chess.B1, chess.G1], chess.BISHOP: [chess.C1, chess.F1]},
            chess.BLACK: {chess.KNIGHT: [chess.B8, chess.G8], chess.BISHOP: [chess.C8, chess.F8]}
        }

        for piece_type_key, squares in starting_squares[color].items(): # Renamed piece_type to piece_type_key
            for square in squares:
                piece = board.piece_at(square)
                # Ensure piece exists before accessing attributes
                if piece and piece.color == color and piece.piece_type == piece_type_key:
                    # Piece is still on its starting square
                    undeveloped_count += 1

        # Apply penalty only if castling rights exist (implies early/middlegame and not yet developed)
        if undeveloped_count > 0 and (board.has_kingside_castling_rights(color) or board.has_queenside_castling_rights(color)):
            score += undeveloped_count * self._get_rule_value('undeveloped_penalty', 0.0)

        return score

    def _mobility_score(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate mobility of pieces"""
        score = 0.0
        
        # Iterate over all pieces of the given color
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color and piece.piece_type != chess.KING: # Exclude king from general mobility
                score += len(list(board.attacks(square))) * self._get_rule_value('piece_mobility_bonus', 0.0)

        return score
    
    def _special_moves(self, board: chess.Board, color: chess.Color) -> float: # Added color parameter
        """Evaluate special moves and opportunities for the given color"""
        score = 0.0
        
        # En passant opportunity for 'color'
        if board.ep_square:
            for move in board.legal_moves:
                # Check if the move is an en passant capture by 'color'
                if move.to_square == board.ep_square:
                    piece_on_from_square = board.piece_at(move.from_square)
                    # Ensure piece_on_from_square is not None before accessing attributes
                    if piece_on_from_square and piece_on_from_square.piece_type == chess.PAWN and piece_on_from_square.color == color:
                        if board.is_en_passant(move):
                            score += self._get_rule_value('en_passant_bonus', 0.0)
                            break # Found one en passant, bonus applied
        
        # Promotion opportunities for 'color'
        # Iterate legal moves for the current player on the board. 
        # If board.turn is not 'color', these are not 'color's opportunities right now.
        # This function should evaluate based on 'color's potential.
        # A simple way: check pawns of 'color' that are one step from promotion.
        promotion_rank = 7 if color == chess.WHITE else 0
        for pawn_square in board.pieces(chess.PAWN, color):
            if chess.square_rank(pawn_square) == (promotion_rank -1 if color == chess.WHITE else promotion_rank + 1):
                # Check if pawn can advance to promotion rank
                # This is a simplified check; a full check involves move generation.
                # For now, just having a pawn on the 7th/2nd is a strong indicator.
                score += self._get_rule_value('pawn_promotion_bonus', 0.0) 
                # A more accurate way would be to check board.generate_legal_moves() for promotions for 'color'
                # but that might be too slow for an eval term. The current approach is a heuristic.
        return score

    def _tactical_evaluation(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate tactical elements related to captures and hanging pieces."""
        score = 0.0
        
        for move in board.legal_moves:
            if board.is_capture(move):
                piece_making_capture = board.piece_at(move.from_square)
                # Ensure piece_making_capture is not None
                if piece_making_capture and piece_making_capture.color == color:
                    score += self._get_rule_value('capture_bonus', 0.0)
        
        opponent_color = not color

        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == opponent_color:
                # Check if it's attacked by 'color' and not defended by 'opponent_color' (i.e., not attacked by opponent_color)
                if board.is_attacked_by(color, square) and not board.is_attacked_by(opponent_color, square):
                    score += self._get_rule_value('hanging_piece_bonus', 0.0)
            elif piece and piece.color == color:
                # Penalty for 'color' having pieces attacked by opponent_color and not defended by 'color'
                if board.is_attacked_by(opponent_color, square) and not board.is_attacked_by(color, square):
                    score += self._get_rule_value('undefended_piece_penalty', 0.0)
        
        return score

    def _castling_evaluation(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate castling rights and opportunities"""
        score = 0.0

        # Check if castled - more robust check considering king's final position
        king_sq = board.king(color)
        if king_sq: # Ensure king exists
            if color == chess.WHITE:
                if king_sq == chess.G1: # Kingside castled
                    score += self._get_rule_value('castling_bonus', 0.0)
                elif king_sq == chess.C1: # Queenside castled
                    score += self._get_rule_value('castling_bonus', 0.0)
            else: # Black
                if king_sq == chess.G8: # Kingside castled
                    score += self._get_rule_value('castling_bonus', 0.0)
                elif king_sq == chess.C8: # Queenside castled
                    score += self._get_rule_value('castling_bonus', 0.0)

        # Penalty if castling rights lost and not yet castled
        initial_king_square = chess.E1 if color == chess.WHITE else chess.E8
        if not board.has_castling_rights(color) and king_sq == initial_king_square:
            score += self._get_rule_value('castling_protection_penalty', 0.0)
        
        # Bonus if still has kingside or queenside castling rights
        if board.has_kingside_castling_rights(color) and board.has_queenside_castling_rights(color):
            score += self._get_rule_value('castling_protection_bonus', 0.0)
        elif board.has_kingside_castling_rights(color) or board.has_queenside_castling_rights(color):
            score += self._get_rule_value('castling_protection_bonus', 0.0) / 2
        
        return score

    def _piece_coordination(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate piece defense coordination for all pieces of the given color."""
        score = 0.0
        # For each piece of the given color
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                # If the piece is defended by another friendly piece (i.e., the square it's on is attacked by its own color)
                if board.is_attacked_by(color, square): 
                    score += self._get_rule_value('piece_coordination_bonus', 0.0) 
        return score
    
    def _pawn_structure(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate pawn structure (doubled, isolated pawns)"""
        score = 0.0
        
        # Count doubled pawns
        for file in range(8):
            pawns_on_file = [s for s in board.pieces(chess.PAWN, color) if chess.square_file(s) == file]
            if len(pawns_on_file) > 1:
                score += (len(pawns_on_file) - 1) * self._get_rule_value('doubled_pawn_penalty', 0.0)
        
        # Count isolated pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            is_isolated = True

            # Check left file
            if file > 0:
                for r in range(8):
                    p = board.piece_at(chess.square(file - 1, r))
                    if p and p.piece_type == chess.PAWN and p.color == color:
                        is_isolated = False
                        break

            # Check right file
            if is_isolated and file < 7:
                for r in range(8):
                    p = board.piece_at(chess.square(file + 1, r))
                    if p and p.piece_type == chess.PAWN and p.color == color:
                        is_isolated = False
                        break

            if is_isolated:
                score += self._get_rule_value('isolated_pawn_penalty', 0.0)
        
        # No general pawn_structure_bonus here, as it's typically derived from good structure
        # (absence of penalties, presence of passed pawns, etc.)
        # If score is positive from penalties, it implies bad structure, so no bonus.
        # if score > 0: 
        #     score += self._get_rule_value('pawn_structure_bonus', 0.0)

        return score

    def _pawn_weaknesses(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate pawn weaknesses (e.g., backward pawns)"""
        score = 0.0
        
        # Count backward pawns
        # A pawn is backward if it cannot be defended by another pawn and is on an open or semi-open file
        direction = 1 if color == chess.WHITE else -1
        for square in board.pieces(chess.PAWN, color):
            # Example: Check if a pawn is passed (this is just an example, not backward pawn logic)
            # if board.is_passed_pawn(square): # Changed from is_passed - This method does not exist on board
            # TODO: Implement actual backward pawn logic here
            # TODO: Implement passed pawn check here if desired, e.g. by checking files ahead.
            # Example for passed pawn (simplified, does not check attacks):
            # is_passed = True
            # opponent_pawn_squares = board.pieces(chess.PAWN, not color)
            # current_file = chess.square_file(square)
            # current_rank = chess.square_rank(square)
            # for opp_pawn_sq in opponent_pawn_squares:
            #     opp_file = chess.square_file(opp_pawn_sq)
            #     opp_rank = chess.square_rank(opp_pawn_sq)
            #     if opp_file >= current_file -1 and opp_file <= current_file + 1: # same or adjacent files
            #         if (color == chess.WHITE and opp_rank > current_rank) or \
            #            (color == chess.BLACK and opp_rank < current_rank): # in front of our pawn
            #             is_passed = False
            #             break
            # if is_passed:
            #     score += self._get_rule_value('passed_pawn_bonus', 0.0) 
            pass # Placeholder for backward/passed pawn logic
        
        return score

    def _pawn_majority(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate pawn majority on the queenside or kingside"""
        score = 0.0
        
        # Count pawns on each side of the board for both colors
        # Files a-d are queenside, e-h are kingside
        white_pawns_kingside = len([p for p in board.pieces(chess.PAWN, chess.WHITE) if chess.square_file(p) >= 4])
        white_pawns_queenside = len([p for p in board.pieces(chess.PAWN, chess.WHITE) if chess.square_file(p) < 4])
        black_pawns_kingside = len([p for p in board.pieces(chess.PAWN, chess.BLACK) if chess.square_file(p) >= 4])
        black_pawns_queenside = len([p for p in board.pieces(chess.PAWN, chess.BLACK) if chess.square_file(p) < 4])
        
        # Compare pawn counts on each wing
        if color == chess.WHITE:
            if white_pawns_kingside > black_pawns_kingside:
                score += self._get_rule_value('pawn_majority_bonus', 0.0) / 2 # Half bonus for kingside
            if white_pawns_queenside > black_pawns_queenside:
                score += self._get_rule_value('pawn_majority_bonus', 0.0) / 2 # Half bonus for queenside
            # Optionally add penalty for minority
            # if white_pawns_kingside < black_pawns_kingside:
            #     score += self._get_rule_value('pawn_minority_penalty', 0.0) / 2
            # if white_pawns_queenside < black_pawns_queenside:
            #     score += self._get_rule_value('pawn_minority_penalty', 0.0) / 2
        else: # Black
            if black_pawns_kingside > white_pawns_kingside:
                score += self._get_rule_value('pawn_majority_bonus', 0.0) / 2
            if black_pawns_queenside > white_pawns_queenside:
                score += self._get_rule_value('pawn_majority_bonus', 0.0) / 2
            # Optionally add penalty for minority
            # if black_pawns_kingside < white_pawns_kingside:
            #     score += self._get_rule_value('pawn_minority_penalty', 0.0) / 2
            # if black_pawns_queenside < white_pawns_queenside:
            #     score += self._get_rule_value('pawn_minority_penalty', 0.0) / 2
        
        return score

    def _passed_pawns(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate passed pawns for the given color."""
        score = 0.0
        opponent_color = not color
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            is_passed = True
            # Check all pawns of the opponent
            for opp_square in board.pieces(chess.PAWN, opponent_color):
                opp_file = chess.square_file(opp_square)
                opp_rank = chess.square_rank(opp_square)
                # For white, passed if no black pawn is on same/adjacent file and ahead
                # For black, passed if no white pawn is on same/adjacent file and ahead
                if abs(opp_file - file) <= 1:
                    if (color == chess.WHITE and opp_rank > rank) or (color == chess.BLACK and opp_rank < rank):
                        is_passed = False
                        break
            if is_passed:
                score += self._get_rule_value('passed_pawn_bonus', 0.0)
        return score

    def _knight_pair(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate knight pair bonus"""
        score = 0.0
        knights = list(board.pieces(chess.KNIGHT, color))
        if len(knights) >= 2:
            score += self._get_rule_value('knight_pair_bonus', 0.0) # Bonus for having *a* knight pair
            # If the bonus is per knight in a pair, it would be len(knights) * bonus / 2 (or similar)
        return score

    def _bishop_pair(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate bishop pair bonus"""
        score = 0.0
        bishops = list(board.pieces(chess.BISHOP, color))
        if len(bishops) >= 2:
            score += self._get_rule_value('bishop_pair_bonus', 0.0)
        return score

    def _bishop_vision(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate bishop vision bonus based on squares attacked."""
        score = 0.0
        for sq in board.pieces(chess.BISHOP, color):
            attacks = board.attacks(sq)
            # Bonus for having more attacked squares (i.e., good vision)
            if len(list(attacks)) > 5: # Bishops generally attack 7-13 squares, adjust threshold as needed
                score += self._get_rule_value('bishop_vision_bonus', 0.0)
        return score

    def _rook_coordination(self, board: chess.Board, color: chess.Color) -> float:
        """Calculate bonus for rook pairs on same file/rank and 7th rank."""
        score = 0.0
        rooks = list(board.pieces(chess.ROOK, color))

        for i in range(len(rooks)):
            for j in range(i+1, len(rooks)):
                sq1, sq2 = rooks[i], rooks[j]
                if chess.square_file(sq1) == chess.square_file(sq2):
                    score += self._get_rule_value('stacked_rooks_bonus', 0.0)
                if chess.square_rank(sq1) == chess.square_rank(sq2):
                    score += self._get_rule_value('coordinated_rooks_bonus', 0.0)
                
                # Rook on 7th rank bonus (critical for attacking pawns)
                # Check for white on rank 7 (index 6) or black on rank 2 (index 1)
                if (color == chess.WHITE and (chess.square_rank(sq1) == 6 or chess.square_rank(sq2) == 6)) or \
                   (color == chess.BLACK and (chess.square_rank(sq1) == 1 or chess.square_rank(sq2) == 1)):
                    score += self._get_rule_value('rook_position_bonus', 0.0)
        return score

    def _open_files(self, board: chess.Board, color: chess.Color) -> float:
        """Evaluate open files for rooks and king safety."""
        score = 0.0
        
        for file in range(8):
            is_file_open = True
            has_own_pawn_on_file = False
            has_opponent_pawn_on_file = False
            for rank in range(8):
                sq = chess.square(file, rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN:
                    is_file_open = False # File is not open if it has any pawns
                    if piece.color == color:
                        has_own_pawn_on_file = True
                    else:
                        has_opponent_pawn_on_file = True
            
            # Bonus for controlling an open or semi-open file
            # An open file has no pawns. A semi-open file has only opponent pawns.
            if is_file_open: # Truly open file
                score += self._get_rule_value('open_file_bonus', 0.0)
            elif not is_file_open and not has_own_pawn_on_file and has_opponent_pawn_on_file: # Semi-open file for 'color'
                score += self._get_rule_value('open_file_bonus', 0.0) / 2 # Half bonus for semi-open (tuneable)

            # Bonus if a rook is on an open or semi-open file
            if any(board.piece_at(chess.square(file, r)) == chess.Piece(chess.ROOK, color) for r in range(8)):
                if is_file_open or (not is_file_open and not has_own_pawn_on_file): # If open or semi-open
                    score += self._get_rule_value('file_control_bonus', 0.0)
            
            # Exposed king penalty if king is on an open/semi-open file
            king_sq = board.king(color)
            if king_sq is not None and chess.square_file(king_sq) == file:
                if is_file_open or (not is_file_open and not has_own_pawn_on_file): # If king is on an open/semi-open file
                    score += self._get_rule_value('exposed_king_penalty', 0.0)

        return score
    
    def _stalemate(self, board: chess.Board) -> float:
        """Check if the position is a stalemate"""
        if board.is_stalemate():
            return self._get_rule_value('stalemate_penalty', 0.0)
        return 0.0