Chess engines are incredibly complex pieces of software that combine sophisticated search algorithms with detailed evaluation functions to determine the best moves. Here's a breakdown of the most common elements:

## **Evaluation Rules (Static Evaluation Function)**

The evaluation function assigns a numerical score to a chess position, indicating its favorability for one side (usually positive for White, negative for Black, and zero for equality). This score is typically measured in "centipawns," where 100 centipawns equal the value of one pawn.  
Common evaluation rules and factors include:

1. **Material Balance:** This is the most fundamental aspect. Each piece is assigned a relative value:  
   * Pawn: 1 point  
   * Knight: 3 points  
   * Bishop: 3 points (often slightly more due to the "bishop pair" advantage)  
   * Rook: 5 points  
   * Queen: 9 points  
   * King: Incalculable (its loss ends the game) Engines calculate the total material for each side.  
2. **Piece-Square Tables (PSTs):** Pieces have different values depending on the squares they occupy. For example:  
   * Knights are often stronger in the center and weaker on the edge.  
   * Pawns on certain ranks might be more valuable (e.g., passed pawns).  
   * Rooks on open files are usually better. PSTs add or subtract points based on a piece's location.  
3. **Pawn Structure:**  
   * **Doubled Pawns:** Penalized as they are less flexible and harder to defend.  
   * **Isolated Pawns:** Penalized as they lack pawn support.  
   * **Backward Pawns:** Penalized as they are on a semi-open file and easily attacked.  
   * **Passed Pawns:** Valued highly, especially as they advance, as they have the potential to promote.  
4. **King Safety:** This is crucial. Engines assess:  
   * **Pawn Shield:** The presence and strength of pawns defending the king.  
   * **Open Files/Diagonals:** If there are open lines leading to the king, it's less safe.  
   * **Enemy Attackers:** The number and proximity of enemy pieces threatening the king.  
5. **Piece Activity/Mobility:** Pieces that can move to more squares are generally better.  
   * **Mobility Score:** Counts the number of legal moves for each piece.  
   * **Centralization:** Pieces in the center of the board are often more active.  
6. **Coordination:** How well pieces work together to achieve a common goal (e.g., attack, defense).  
7. **Threats and Defenses:** Identifying immediate threats (attacks on undefended pieces, checks) and how well pieces are defended.  
8. **Initiative:** The ability to make forcing moves and dictate the flow of the game.  
9. **Game Phase:** The relative importance of different factors changes throughout the game (opening, middlegame, endgame). For example, king safety is paramount in the middlegame, while pawn structure and passed pawns become more critical in the endgame.

Modern engines often use **neural networks** (like AlphaZero and Leela Chess Zero) that learn these evaluation rules implicitly from vast numbers of self-played games, rather than having them explicitly programmed. However, traditional "hand-crafted" evaluation functions still form the basis of many strong engines like Stockfish.

## **Search Functions (Search Algorithms)**

The search function explores the "game tree" of possible moves and counter-moves to a certain "depth" (number of half-moves). The goal is to find the sequence of moves that leads to the best possible evaluation score.  
The most common search functions and techniques include:

1. **Minimax Algorithm:** This is the foundational algorithm. It assumes both players play optimally. It works by:  
   * Evaluating all possible positions up to a certain depth.  
   * For the engine's moves (maximizing player), it chooses the move that leads to the highest possible evaluation score.  
   * For the opponent's moves (minimizing player), it assumes the opponent will choose the move that leads to the lowest possible evaluation score for the engine.  
2. **Alpha-Beta Pruning:** This is a crucial optimization of Minimax. It significantly reduces the number of positions that need to be evaluated by eliminating branches of the search tree that cannot possibly lead to a better result than what has already been found. If a move is found that is clearly worse than a move already considered, that branch is "pruned."  
3. **Iterative Deepening:** Instead of searching directly to a fixed depth, engines start with a shallow search (e.g., depth 1), then progressively increase the depth (depth 2, depth 3, etc.) until a time limit is reached or a stable best move is found. This allows the engine to return a "best move so far" if it runs out of time and helps with move ordering.  
4. **Quiescence Search:** This is an extension of the main search. It's applied at the "leaf nodes" (the deepest points of the main search) to ensure that the evaluation isn't made in the middle of a tactical sequence. It continues searching *only forcing moves* (captures, checks, pawn promotions) until a "quiet" position is reached, preventing the "horizon effect" (where the engine might miss a tactic just beyond its search depth).  
5. **Transposition Tables (Hash Tables):** Chess positions can be reached in many different ways (transpositions). A transposition table stores the evaluation and search results for positions that have already been encountered, preventing redundant calculations and speeding up the search significantly.  
6. **Move Ordering:** The order in which moves are considered within the search dramatically impacts the effectiveness of Alpha-Beta Pruning. Good move ordering (e.g., trying captures and checks first) leads to more pruning.  
7. **Heuristics and Reductions:**  
   * **Null Move Pruning:** A strong heuristic where the engine considers passing a turn to the opponent to see if they still have a good move. If the opponent still has a strong move even after getting an extra tempo, the current position might be worse than initially thought.  
   * **Late Move Reductions (LMR):** Moves that are tried late in the move order (i.e., they are not forcing or promising) are searched to a shallower depth, as they are less likely to be the best move.  
8. **Monte Carlo Tree Search (MCTS):** While traditional engines primarily use Alpha-Beta, MCTS is famously used by neural network-based engines like Leela Chess Zero. MCTS works by building a search tree through repeated simulations (playouts) of games from the current position. It focuses its computational effort on more promising lines by balancing exploration of new moves with exploitation of moves that have historically performed well.

The combination of sophisticated evaluation functions and efficient search algorithms allows modern chess engines to play at a superhuman level.