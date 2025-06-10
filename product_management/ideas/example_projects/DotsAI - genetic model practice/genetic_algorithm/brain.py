import random
import math

# Configuration Constants
MUTATION_RATE = 0.01

class Brain:
    def __init__(self, size):
        self.directions = [self.random_vector() for _ in range(size)]
        self.step = 0

    def random_vector(self):
        """Generate a random direction vector."""
        angle = random.uniform(0, 2 * math.pi)
        return (math.cos(angle), math.sin(angle))

    def clone(self):
        """Clone the brain."""
        clone = Brain(len(self.directions))
        clone.directions = self.directions[:]
        return clone

    def mutate(self):
        """Mutate the brain's directions."""
        for i in range(len(self.directions)):
            if random.random() < MUTATION_RATE:
                self.directions[i] = self.random_vector()