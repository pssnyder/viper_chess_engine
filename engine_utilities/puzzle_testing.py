import os
import yaml
import logging
import chess
from ..evaluation_engine import EvaluationEngine
from puzzle_manager import PuzzleManager

class PuzzleTester:
    def __init__(self, config_path="config.yaml", db_path="puzzles.db", log_dir="logging"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.puzzle_manager = PuzzleManager(db_path=db_path)
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.logger = self._setup_logger()
        self.engine_config = self.config.get("white_ai_config", {})

    def _setup_logger(self):
        logger = logging.getLogger("puzzle_testing")
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(os.path.join(self.log_dir, "../logging/puzzle_testing.log"))
        formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
        fh.setFormatter(formatter)
        if not logger.handlers:
            logger.addHandler(fh)
        return logger

    def test_random_puzzle(self):
        cfg = self.config.get("puzzle_config", {})
        puzzle = self.puzzle_manager.get_random_puzzle(
            min_rating=cfg.get("min_rating", 0),
            max_rating=cfg.get("max_rating", 9999),
            themes=cfg.get("puzzle_types", []),
            max_moves=cfg.get("puzzle_solution_limit", 0)
        )
        if not puzzle:
            print("No puzzle found matching criteria.")
            return
        fen = puzzle["fen"]
        solution = puzzle["moves"].split()
        board = chess.Board(fen)
        ai_moves = []
        failed = False

        engine = EvaluationEngine(board, chess.WHITE)
        move_idx = 0
        while move_idx < len(solution):
            expected_move = solution[move_idx]
            ai_move = engine.search(board, board.turn, self.engine_config)
            ai_move_uci = ai_move.uci() if hasattr(ai_move, "uci") else str(ai_move)
            ai_moves.append(ai_move_uci)
            if ai_move_uci != expected_move:
                failed = True
                break
            board.push(chess.Move.from_uci(ai_move_uci))
            move_idx += 1

        if failed:
            self.logger.error(
                f"FAILED | PuzzleId: {puzzle['id']} | FEN: {fen} | Solution: {solution} | AI Moves: {ai_moves} | Config: {self.engine_config}"
            )
            print(f"Puzzle failed. See log for details.")
        else:
            self.logger.info(
                f"SUCCESS | PuzzleId: {puzzle['id']} | FEN: {fen} | Solution: {solution} | AI Moves: {ai_moves} | Config: {self.engine_config}"
            )
            print(f"Puzzle solved successfully.")

if __name__ == "__main__":
    tester = PuzzleTester()
    tester.test_random_puzzle()

