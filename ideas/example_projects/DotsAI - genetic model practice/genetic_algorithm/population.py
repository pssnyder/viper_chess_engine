import random
from dot import Dot

# Configuration Constants
MUTATION_RATE = 0.01

class Population:
    def __init__(self, size, width, height, goal, obstacles):
        self.dots = [Dot(width, height, goal, obstacles) for _ in range(size)]
        self.gen = 1
        self.min_step = 400
        self.best_dot = 0

    def update(self):
        """Update all dots in the population."""
        for dot in self.dots:
            dot.update()

    def calculate_fitness(self):
        """Calculate fitness for all dots."""
        for dot in self.dots:
            dot.calculate_fitness()

    def natural_selection(self):
        """Perform natural selection to create a new generation."""
        new_dots = [None] * len(self.dots)
        self.set_best_dot()
        new_dots[0] = self.dots[self.best_dot].clone()
        new_dots[0].is_best = True
        for i in range(1, len(new_dots)):
            parent = self.select_parent()
            new_dots[i] = parent.clone()
        self.dots = new_dots
        self.gen += 1

    def select_parent(self):
        """Select a parent based on fitness."""
        fitness_sum = sum(dot.fitness for dot in self.dots)
        rand = random.uniform(0, fitness_sum)
        running_sum = 0
        for dot in self.dots:
            running_sum += dot.fitness
            if running_sum > rand:
                return dot
        return None

    def mutate(self):
        """Mutate all dots except the best one."""
        for i in range(1, len(self.dots)):
            self.dots[i].brain.mutate()

    def set_best_dot(self):
        """Set the best dot based on fitness."""
        max_fitness = 0
        max_index = 0
        for i, dot in enumerate(self.dots):
            if dot.fitness > max_fitness:
                max_fitness = dot.fitness
                max_index = i
        self.best_dot = max_index
        if self.dots[self.best_dot].reached_goal:
            self.min_step = self.dots[self.best_dot].brain.step