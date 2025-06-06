# chess_puzzles.py

"""
    This module provides the PuzzleManager class for managing, loading, and solving chess puzzles.
    It supports loading puzzles from a CSV file, filtering them by difficulty and type, and tracking solutions.
    The class also provides logging functionality and debug output for development and troubleshooting.

    CSV Format: PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags
    Sample CSV:
    00sHx,q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17,e8d7 a2e6 d7d8 f7f8,1760,80,83,72,mate mateIn2 middlegame short,https://lichess.org/yyznGmXs/black#34,Italian_Game Italian_Game_Classical_Variation
    00sJ9,r3r1k1/p4ppp/2p2n2/1p6/3P1qb1/2NQR3/PPB2PP1/R1B3K1 w - - 5 18,e3g3 e8e1 g1h2 e1c1 a1c1 f4h6 h2g1 h6c1,2671,105,87,325,advantage attraction fork middlegame sacrifice veryLong,https://lichess.org/gyFeQsOE#35,French_Defense French_Defense_Exchange_Variation
    00sJb,Q1b2r1k/p2np2p/5bp1/q7/5P2/4B3/PPP3PP/2KR1B1R w - - 1 17,d1d7 a5e1 d7d1 e1e3 c1b1 e3b6,2235,76,97,64,advantage fork long,https://lichess.org/kiuvTFoE#33,Sicilian_Defense Sicilian_Defense_Dragon_Variation
    00sO1,1k1r4/pp3pp1/2p1p3/4b3/P3n1P1/8/KPP2PN1/3rBR1R b - - 2 31,b8c7 e1a5 b7b6 f1d1,998,85,94,293,advantage discoveredAttack master middlegame short,https://lichess.org/vsfFkG0s/black#62,
    
    Classes:
        PuzzleManager: Handles the creation, management, and solving of chess puzzles, including configuration loading,
                       puzzle selection, solution checking, and result logging.

"""
import os
import logging
import yaml
import random

# At module level, define a single logger for this file
puzzle_logger = logging.getLogger("puzzle_manager")
puzzle_logger.setLevel(logging.DEBUG)
if not puzzle_logger.handlers:
    if not os.path.exists('logging'):
        os.makedirs('logging', exist_ok=True)
    from logging.handlers import RotatingFileHandler
    log_file_path = "logging/puzzle_manager.log"
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10*1024*1024,
        backupCount=3
    )
    formatter = logging.Formatter(
        '%(asctime)s | %(funcName)-15s | %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    puzzle_logger.addHandler(file_handler)
    puzzle_logger.propagate = False

class PuzzleManager:
    """
    Class to handle chess puzzles.
    It provides methods to create, solve, and manage chess puzzles.
    """

    def __init__(self, debug=False):
        self.puzzles = []
        self.config = {}
        self.puzzle_config = {}
        self.positional_solutions = {}
        self.logger = puzzle_logger  # Use the module-level logger
        self.logging_enabled = self.config.get('logging_enabled', True)  # Default to True if not specified
        self.debug = debug
        self.loading = False  # Add loading flag
        
        # Load configuration with error handling
        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
            if self.debug:
                print("Loaded config file successfully.")
        except Exception as e:
            print("Error loading config: %s", e)

        # Debugging
        self.debug = debug if debug else self.config.get('show_thinking', False)
        
        # Set up puzzle solver
        self.puzzle_config = self.config.get('puzzle_config', {})
        self.puzzle_time_limit = self.puzzle_config.get('puzzle_time_limit', 60)
        self.puzzle_count = self.puzzle_config.get('puzzle_count', 1)
        self.puzzle_solution_limit = self.puzzle_config.get('puzzle_solution_limit', 1)
        self.puzzle_difficulty = self.puzzle_config.get('puzzle_difficulty', 0)
        self.puzzle_types = self.puzzle_config.get('puzzle_types', ['mate', 'mateIn2', 'mateIn3'])
        self.puzzle_file = self.puzzle_config.get('puzzle_file', 'puzzles/lichess_db_puzzle.csv')

        if self.debug:
            self.logger.info("Puzzle config: %s", self.puzzle_config)
            self.logger.info("Puzzle file: %s", self.puzzle_file)

        # Load puzzles from the puzzle file that match the configuration criteria
        self.load_puzzles()
    
    def load_puzzles(self):
        parts = []
        solution_text = ''
        solution = []
        keyword_text = ''
        keywords = []
        keyword_found = False

        self.logger.info("Starting to load puzzles from file: %s", self.puzzle_file)
        self.loading = True  # Set loading flag at start
        import_limit = self.puzzle_config.get('puzzle_import_limit', 0)
        import_offset = self.puzzle_config.get('puzzle_import_offset', 0)
        solution_limit = self.puzzle_config.get('puzzle_solution_limit', 0)
        max_difficulty = self.puzzle_config.get('puzzle_difficulty', 0)
        use_solutions = self.puzzle_config.get('use_solutions', False)
        allowed_types = [t.lower() for t in self.puzzle_config.get('puzzle_types', [])]
        loaded = 0
        skipped = 0
        loaded_solutions = 0
        
        try:
            if self.logging_enabled and self.logger:
                self.logger.info(f"Puzzle Criteria: import_limit={import_limit} | solution_limit={solution_limit} | max_difficulty={max_difficulty} | use_solutions={use_solutions} | allowed_types={allowed_types}")
            with open(self.puzzle_file, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    # Load all single move puzzles into the positional solutions dictionary and criteria matching puzzles into puzzles dictionary
                    parts = line.strip().split(',')
                    if parts[0].strip() == "PuzzleId":
                        continue  # Skip header line

                    if len(parts) >= 7 and parts[1].strip() and parts[2].strip() and parts[3].strip() and parts[7].strip():
                        # Extract the FEN, solution, rating, and keywords from the line
                        fen = parts[1]
                        solution_text = parts[2]
                        rating = parts[3]
                        keyword_text = parts[7] if len(parts) > 4 else ''
                        keyword_found = False
                        too_difficult = False
                        # Split the solution into individual moves
                        solution = solution_text.split()

                        # Split the keywords into a list
                        if isinstance(keyword_text, list):
                            keywords = [k.strip() for k in keyword_text]
                        else:
                            keywords = [keyword_text.strip()]

                        # Build positional_solutions dict (always, if use_solutions)
                        if use_solutions and fen not in self.positional_solutions:
                            self.positional_solutions[fen] = solution
                            loaded_solutions += 1
                        # Only load puzzles for solving if within offset/limit
                        if (not use_solutions and import_limit and loaded >= import_limit) or (use_solutions and import_limit and loaded >= import_limit):
                            continue
                        if import_offset and loaded < import_offset:
                            loaded += 1
                            continue

                        # Check if the puzzle fits the configuration criteria
                        for limiting_keyword in self.puzzle_types:
                            for keyword in keywords:
                                if limiting_keyword in keyword.lower():
                                    keyword_found = True
                                break  # Found a matching keyword, no need to check further
                        
                        # Check if the puzzle matches the difficulty level
                        if self.puzzle_difficulty > 0 and int(rating) < self.puzzle_difficulty:
                            too_difficult = True

                        # If the puzzle does not match the criteria, skip it
                        if self.puzzle_solution_limit != 0 and (len(solution) > self.puzzle_solution_limit or not keyword_found or too_difficult):
                            skipped += 1
                            self.logger.debug(
                                "Skipping puzzle at line %d: FEN=%s, reason=%s",
                                line_num, fen,
                                "too many moves in solution" if len(solution) > self.puzzle_solution_limit else
                                "keyword not found" if not keyword_found else
                                "too difficult"
                            )
                            continue # Skip puzzles that do not match the criteria
                        
                        self.logger.debug("Adding puzzle at line %d: FEN=%s, solution=%s", line_num, fen, solution)
                        # Add the puzzle to this puzzle session if it matches the criteria
                        self.add_puzzle(fen, solution)
                        loaded += 1
                    else:
                        self.logger.debug("Skipping line %d: insufficient columns or missing data", line_num)
                if self.debug:
                    self.logger.info("Puzzles added: %d", loaded)
                    self.logger.info("Puzzles skipped: %d", skipped)
                    self.logger.info("Positional solutions created: %d", loaded_solutions)

        except FileNotFoundError:
            self.logger.warning("File %s not found.", self.puzzle_file)
        except Exception as e:
            self.logger.error("Exception while loading puzzles: %s", e)
        self.loading = False  # Set loading flag to False when done

    def add_puzzle(self, fen: str, solution: str):
        self.logger.debug("add_puzzle called with FEN: %s, solution: %s", fen, solution)
        try:
            self.puzzles.append({'fen': fen, 'solution': solution, 'solved': False})
            self.logger.info("Puzzle added: FEN=%s, solution=%s", fen, solution)
        except Exception as e:
            self.logger.error("Error adding puzzle: %s", e)

    def get_puzzle(self, index: int):
        self.logger.debug("get_puzzle called with index: %d", index)
        if self.debug:
            self.logger.info("Getting puzzle at index: %d", index)
        if 0 <= index < len(self.puzzles):
            self.logger.info("Puzzle found at index %d: %s", index, self.puzzles[index])
            return self.puzzles[index]
        else:
            self.logger.warning("Requested puzzle index %d out of range (total puzzles: %d)", index, len(self.puzzles))
            return None

    def get_random_puzzle(self):
        self.logger.debug("get_random_puzzle called")
        unsolved = [p for p in self.puzzles if not p.get('solved', False)]
        if not unsolved:
            if self.debug:
                self.logger.warning("No unsolved puzzles available for random selection.")
            return None
        puzzle = random.choice(unsolved)
        if self.debug:
            self.logger.info("Random puzzle selected: %s", puzzle)
        self.logger.info("Returning unsolved random puzzle: %s", puzzle)
        return puzzle

    def solve_puzzle(self, index: int, move: str):
        """
        Check if the provided move solves the puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to check
        :return: True if the move is correct, False otherwise
        """
        puzzle = self.get_puzzle(index)
        if self.debug:
            self.logger.info("Solving puzzle at index %d with move %s. Puzzle: %s", index, move, puzzle)
        return puzzle is not None and puzzle['solution'] == move
    
    def find_puzzle_solution(self, fen: str):
        """
        Find a positional solution for a given FEN string.

        :param fen: FEN string representing the position
        :return: Single move solution in UCI format if found, None otherwise
        """
        if self.debug:
            self.logger.info("Finding solution for FEN: %s", fen)
        return self.positional_solutions.get(fen, None)
    
    def test_solution(self, index: int, move: str):
        """
        Test a solution against a puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to test
        :return: Tuple (is_correct, message)
        """
        if self.debug:
            self.logger.info("Testing solution for puzzle %d with move %s", index, move)
        if self.solve_puzzle(index, move):
            return True, "Correct solution!"
        else:
            return False, "Incorrect solution. Try again."

    def mark_puzzle_solved(self, fen: str):
        """
        Mark a puzzle as solved by its FEN string.
        
        :param fen: FEN string of the puzzle to mark as solved
        """
        for puzzle in self.puzzles:
            if puzzle['fen'] == fen:
                puzzle['solved'] = True
                self.logger.info("Puzzle with FEN %s marked as solved.", fen)
                return
        self.logger.warning("Puzzle with FEN %s not found to mark as solved.", fen)

    def log_result(self, index: int, result: str):
        """
        Log the result of solving a puzzle.
        
        :param index: Index of the puzzle
        :param result: Result of the attempt (e.g., 'correct', 'incorrect')
        """
        puzzle = self.get_puzzle(index)
        if puzzle:
            self.logger.info("Puzzle %d (%s): %s", index, puzzle['fen'], result)
        else:
            self.logger.warning("Attempted to log result for non-existent puzzle index %d.", index)

    # Add timer logic for puzzle_time_limit if you want to enforce time per puzzle
    # This is best handled in the game logic, but you can expose the value here:
    def get_time_limit(self):
        return self.puzzle_config.get('puzzle_time_limit', 0)


# Example usage
if __name__ == "__main__":
    puzzle_manager = PuzzleManager(debug=True)
    puzzle_manager.load_puzzles()
    random_puzzle = puzzle_manager.get_random_puzzle()
    if random_puzzle:
        print(f"Random Puzzle FEN: {random_puzzle['fen']}")
        move = input("Enter your move in UCI format (e.g., e2e4): ")
        is_correct, message = puzzle_manager.test_solution(0, move)
        print(message)
        puzzle_manager.log_result(0, 'correct' if is_correct else 'incorrect')