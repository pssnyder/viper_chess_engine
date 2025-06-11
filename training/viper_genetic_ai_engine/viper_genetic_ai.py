import random
import numpy as np
import chess
import chess.pgn
import copy
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

class ChessDataset(Dataset):
    def __init__(self, pgn_path, username):
        self.positions = []
        self.moves = []
        
        pgn = open(pgn_path)
        while True:
            game = chess.pgn.read_game(pgn)
            if not game:
                break
            
            if game.headers["White"] == username or game.headers["Black"] == username:
                board = game.board()
                for move in game.mainline_moves():
                    if (board.turn == chess.WHITE and game.headers["White"] == username) or \
                       (board.turn == chess.BLACK and game.headers["Black"] == username):
                        self.positions.append(self.board_to_tensor(board))
                        self.moves.append(move.uci())
                    board.push(move)

    def board_to_tensor(self, board):
        tensor = np.zeros((12, 8, 8), dtype=np.float32)
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                channel = piece.piece_type - 1 + (6 if piece.color == chess.BLACK else 0)
                tensor[channel][7 - square//8][square%8] = 1
        return tensor

    def __len__(self):
        return len(self.positions)

    def __getitem__(self, idx):
        return self.positions[idx], self.moves[idx]

class ChessAI(nn.Module):
    def __init__(self, num_classes):
        super().__init__()
        
        # Convolutional layers for spatial pattern recognition
        self.conv1 = nn.Conv2d(12, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(128, 64, kernel_size=3, padding=1)
        
        # Fully connected layers for move prediction
        self.fc1 = nn.Linear(64 * 8 * 8, 512)
        self.fc2 = nn.Linear(512, 256)
        self.fc3 = nn.Linear(256, num_classes)
        
        # Value head for position evaluation
        self.value_fc1 = nn.Linear(64 * 8 * 8, 256)
        self.value_fc2 = nn.Linear(256, 1)
        
        # Initialize piece-square tables
        self.initialize_piece_tables()
        
        # Genetic parameters (will be evolved)
        self.genetic_params = {
            'material_weight': 1.0,
            'position_weight': 0.5,
            'search_depth': 2
        }
    
    def forward(self, x):
        # CNN forward pass
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        
        # Flatten
        x_flat = x.view(x.size(0), -1)
        
        # Policy head (move prediction)
        policy = F.relu(self.fc1(x_flat))
        policy = F.relu(self.fc2(policy))
        policy = self.fc3(policy)  # Raw logits
        
        # Value head (position evaluation)
        value = F.relu(self.value_fc1(x_flat))
        value = torch.tanh(self.value_fc2(value))  # Value between -1 and 1
        
        return policy, value


class GeneticAlgorithm:
    def __init__(self, population_size=30, mutation_rate=0.2, elite_count=3):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.elite_count = elite_count
        self.population = []
        
    def initialize_population(self, model_template):
        """Initialize a population of models with random genetic parameters"""
        self.population = []
        for _ in range(self.population_size):
            # Create a copy of the template model
            model = copy.deepcopy(model_template)
            
            # Randomize genetic parameters
            model.genetic_params = {
                'material_weight': random.uniform(0.5, 1.5),
                'position_weight': random.uniform(0.2, 0.8),
                'search_depth': random.randint(1, 3)
            }
            
            self.population.append(model)
    
    def evaluate_fitness(self, model, games):
        """Calculate fitness based on v7p3r's games performance"""
        fitness = 0
        
        for game in games:
            # Check if v7p3r played this game
            played_white = game.headers.get("White") == "v7p3r"
            played_black = game.headers.get("Black") == "v7p3r"
            
            if not (played_white or played_black):
                continue
                
            # Parse result
            result = game.headers.get("Result")
            if result == "1-0":
                result_score = 1.0  # White win
            elif result == "0-1":
                result_score = 0.0  # Black win
            else:
                result_score = 0.5  # Draw
            
            # Higher fitness if v7p3r won
            if (played_white and result_score == 1.0) or (played_black and result_score == 0.0):
                fitness += 10
            elif result_score == 0.5:
                fitness += 2
                
            # Test model's ability to predict v7p3r's moves
            board = chess.Board()
            move_count = 0
            
            for move in game.mainline_moves():
                # If it's v7p3r's turn
                if (board.turn == chess.WHITE and played_white) or (board.turn == chess.BLACK and played_black):
                    # Predict move
                    predicted_move, _ = model.select_move(board)
                    
                    # Compare with actual move
                    if predicted_move == move:
                        fitness += 2
                
                # Apply move
                board.push(move)
                move_count += 1
                
                # Limit to first 20 moves for performance
                if move_count >= 20:
                    break
        
        return fitness
    
    def evolve_population(self, games):
        """Evolve population through selection, crossover, and mutation"""
        # Evaluate fitness for each model
        fitness_scores = []
        for model in self.population:
            fitness = self.evaluate_fitness(model, games)
            fitness_scores.append(fitness)
        
        # Pair models with their fitness scores
        model_fitness = list(zip(self.population, fitness_scores))
        
        # Sort by fitness (descending)
        model_fitness.sort(key=lambda x: x[1], reverse=True)
        
        # Keep elite models
        new_population = [model for model, _ in model_fitness[:self.elite_count]]
        
        # Create offspring
        while len(new_population) < self.population_size:
            # Tournament selection
            parent1 = self._tournament_selection(model_fitness)
            parent2 = self._tournament_selection(model_fitness)
            
            # Crossover
            child = self._crossover(parent1, parent2)
            
            # Mutation
            child = self._mutate(child)
            
            # Add to new population
            new_population.append(child)
        
        # Update population
        self.population = new_population
        
        # Return best model and its fitness
        return self.population[0], model_fitness[0][1]
    
    def _tournament_selection(self, model_fitness, tournament_size=3):
        """Tournament selection - select best from random subset"""
        tournament = random.sample(model_fitness, tournament_size)
        tournament.sort(key=lambda x: x[1], reverse=True)
        return tournament[0][0]  # Return the model with highest fitness
    
    def _crossover(self, parent1, parent2):
        """Crossover genetic parameters from two parents"""
        child = copy.deepcopy(parent1)
        
        # For each genetic parameter, randomly choose from parent1 or parent2
        for key in child.genetic_params:
            if random.random() < 0.5:
                child.genetic_params[key] = parent2.genetic_params[key]
        
        return child
    
    def _mutate(self, model):
        """Mutate genetic parameters with probability mutation_rate"""
        for key in model.genetic_params:
            if random.random() < self.mutation_rate:
                # Mutate the parameter
                if key == 'search_depth':
                    model.genetic_params[key] = random.randint(1, 3)
                else:
                    # For continuous parameters, add random noise
                    model.genetic_params[key] *= random.uniform(0.8, 1.2)
        
        return model
