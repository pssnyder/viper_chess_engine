# chess_puzzles.py

import chess
import chess.pgn
import logging
import yaml

class ChessPuzzles:
    """
    Class to handle chess puzzles.
    It provides methods to create, solve, and manage chess puzzles.
    """

    def __init__(self):
        self.puzzles = []
        self.config = {}
        self.puzzle_ai_config = 'white_ai_config'  # Default AI configuration
        self.puzzle_config = {}
        self.ai_config = {}
        self.logger = None

        # Load configuration with error handling
        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

        # Set up puzzle solver
        self.puzzle_config = self.config.get('puzzle_config', {})
        if not self.puzzle_config:
            raise ValueError("Puzzle configuration not found in config file.")
        self.puzzle_count = self.puzzle_config.get('puzzle_count', 1)
        self.puzzle_difficulty = self.puzzle_config.get('puzzle_difficulty', 'easy')
        self.puzzle_types = self.puzzle_config.get('puzzle_types', ['mate', 'mateIn2', 'mateIn3'])
        
        # Set up logging
        self.configure_logging(self.config.get('log_file', 'logging/puzzle_solving.log'))
        self.logger = logging.getLogger(__name__)
        
    def configure_logging(self, log_file: str):
        """
        Configure logging for the class.
        
        :param log_file: Path to the log file
        """
        logging.basicConfig(filename=log_file, level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
    def add_puzzle(self, fen: str, solution: str):
        """
        Add a new puzzle with its FEN string and solution.
        
        :param fen: FEN string representing the puzzle position
        :param solution: Solution in UCI format (e.g., 'e2e4')
        """
        self.puzzles.append({'fen': fen, 'solution': solution})

    def get_puzzle(self, index: int):
        """
        Get a puzzle by its index.
        
        :param index: Index of the puzzle
        :return: Dictionary containing the FEN and solution
        """
        return self.puzzles[index] if 0 <= index < len(self.puzzles) else None

    def solve_puzzle(self, index: int, move: str):
        """
        Check if the provided move solves the puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to check
        :return: True if the move is correct, False otherwise
        """
        puzzle = self.get_puzzle(index)
        return puzzle is not None and puzzle['solution'] == move
    
    def test_solution(self, index: int, move: str):
        """
        Test a solution against a puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to test
        :return: Tuple (is_correct, message)
        """
        if self.solve_puzzle(index, move):
            return True, "Correct solution!"
        else:
            return False, "Incorrect solution. Try again."
        
    def log_result(self, index: int, result: str):
        """
        Log the result of solving a puzzle.
        
        :param index: Index of the puzzle
        :param result: Result of the attempt (e.g., 'correct', 'incorrect')
        """
        puzzle = self.get_puzzle(index)
        if puzzle:
            self.logger.info(f"Puzzle {index} ({puzzle['fen']}): {result}")
        else:
            self.logger.warning(f"Attempted to log result for non-existent puzzle index {index}.")
    
    
    
# Example usage and testing:
if __name__ == "__main__":
    cp = ChessPuzzles()
    # Load puzzles from a file
    puzzle_file = 'puzzles/lichess_db_puzzle.csv'
    try:
        with open(puzzle_file, 'r', encoding='utf-8') as file:
            for line in file:
                parts = line.strip().split(',')
                if len(parts) >= 3 and parts[1].strip() and parts[2].strip():
                    fen = parts[1]
                    solution = parts[2]  # Assuming the solution is in UCI format
                    cp.add_puzzle(fen, solution)
                    
    except FileNotFoundError:
        print(f"File {puzzle_file} not found.")

    # Test solving sample puzzle from the file
    if cp.puzzles:
        sample_index = 0  # Change this to test different puzzles
        sample_move = cp.puzzles[sample_index]['solution']  # Use the correct solution for testing
        is_correct, message = cp.test_solution(sample_index, sample_move)
        cp.log_result(sample_index, 'correct' if is_correct else 'incorrect')
        print(f"Puzzle {sample_index} test result: {message}")
    else:
        print("No puzzles loaded.")