
import torch
import torch.nn as nn
import torch.optim as optim
import chess
import chess.pgn
import numpy as np
import yaml
import pickle
import os
from chess_core import ChessDataset, ChessAI
from genetic_algorithm import GeneticAlgorithm

torch.backends.cudnn.benchmark = True  # Enable CuDNN auto-tuner

# Load configuration
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# Enable CUDA if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def load_games(pgn_path):
    """Load games from PGN file"""
    games = []
    with open(pgn_path) as pgn:
        while True:
            game = chess.pgn.read_game(pgn)
            if game is None:
                break
            games.append(game)
    return games

def filter_v7p3r_games(games):
    """Filter games played by v7p3r"""
    v7p3r_games = []
    for game in games:
        if game.headers.get("White") == "v7p3r" or game.headers.get("Black") == "v7p3r":
            v7p3r_games.append(game)
    return v7p3r_games

def train_supervised_model(dataset, num_classes, epochs=10, batch_size=64):
    """Train a supervised model on the dataset before genetic evolution"""
    model = ChessAI(num_classes).to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    
    # Create DataLoader
    dataloader = torch.utils.data.DataLoader(
        dataset, batch_size=batch_size, shuffle=True
    )
    
    # Training loop
    for epoch in range(epochs):
        total_loss = 0
        correct = 0
        total = 0
        
        for positions, moves in dataloader:
            positions = positions.to(device)
            moves = moves.to(device)
            
            # Forward pass
            policy, _ = model(positions)
            loss = criterion(policy, moves)
            
            # Backward pass and optimize
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            # Calculate accuracy
            _, predicted = torch.max(policy.data, 1)
            total += moves.size(0)
            correct += (predicted == moves).sum().item()
            total_loss += loss.item()
        
        # Print epoch statistics
        print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(dataloader):.4f}, "
              f"Accuracy: {100 * correct / total:.2f}%")
    
    return model

def train_model():
    """Complete training pipeline with supervised learning and genetic evolution"""
    # Load data
    dataset = ChessDataset("games.pgn", "v7p3r")
    
    # Create move vocabulary
    move_to_index = {move: idx for idx, move in enumerate(np.unique(dataset.moves))}
    num_classes = len(move_to_index)
    
    # Save the move vocabulary
    with open("move_vocab.pkl", "wb") as f:
        pickle.dump(move_to_index, f)
    
    # Convert string moves to indices
    move_indices = [move_to_index[move] for move in dataset.moves]
    dataset.moves = move_indices
    
    print(f"Dataset created with {len(dataset)} positions and {num_classes} possible moves")
    
    # First, train with supervised learning to get a decent starting point
    pretrained_model = train_supervised_model(dataset, num_classes, epochs=5)
    
    # Load games for genetic algorithm fitness evaluation
    all_games = load_games("games.pgn")
    v7p3r_games = filter_v7p3r_games(all_games)
    print(f"Found {len(v7p3r_games)} games played by v7p3r")
    
    # Initialize genetic algorithm
    ga = GeneticAlgorithm(population_size=20)
    ga.initialize_population(pretrained_model)
    
    # Run genetic evolution
    num_generations = 30
    best_fitness_history = []
    
    for generation in range(num_generations):
        print(f"Generation {generation+1}/{num_generations}")
        
        # Evolve population
        best_model, best_fitness = ga.evolve_population(v7p3r_games)
        best_fitness_history.append(best_fitness)
        
        print(f"Best fitness: {best_fitness}")
        print(f"Best model genetic params: {best_model.genetic_params}")
        
        # Save best model every 5 generations
        if (generation + 1) % 5 == 0:
            torch.save(best_model.state_dict(), f"v7p3r_chess_gen_{generation+1}.pth")
    
    # Save final model
    torch.save(best_model.state_dict(), "v7p3r_chess_genetic_model.pth")
    print("Training complete!")
    
    # Plot fitness history
    try:
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 6))
        plt.plot(range(1, num_generations+1), best_fitness_history)
        plt.title("Best Fitness per Generation")
        plt.xlabel("Generation")
        plt.ylabel("Fitness")
        plt.grid(True)
        plt.savefig("fitness_history.png")
        print("Fitness history plot saved")
    except:
        print("Could not create fitness history plot")

if __name__ == "__main__":
    train_model()
