import random
import math
from brain import Brain

# Configuration Constants
MAX_VELOCITY = 5
BRAIN_SIZE = 400

class Dot:
    def __init__(self, width, height, goal, obstacles):
        self.brain = Brain(BRAIN_SIZE)
        self.pos = [width / 2, height - 10]
        self.vel = [0, 0]
        self.acc = [0, 0]
        self.dead = False
        self.reached_goal = False
        self.fitness = 0
        self.width = width
        self.height = height
        self.goal = goal
        self.obstacles = obstacles
        self.is_best = False

    def move(self):
        """Move the dot according to its brain's directions."""
        if len(self.brain.directions) > self.brain.step:
            self.acc = self.brain.directions[self.brain.step]
            self.brain.step += 1
        else:
            self.dead = True

        self.vel[0] += self.acc[0]
        self.vel[1] += self.acc[1]
        self.limit_velocity(MAX_VELOCITY)
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]

    def limit_velocity(self, max_velocity):
        """Limit the velocity of the dot."""
        speed = math.sqrt(self.vel[0]**2 + self.vel[1]**2)
        if speed > max_velocity:
            self.vel[0] = (self.vel[0] / speed) * max_velocity
            self.vel[1] = (self.vel[1] / speed) * max_velocity

    def update(self):
        """Update the dot's position and check for collisions."""
        if not self.dead and not self.reached_goal:
            self.move()
            if self.pos[0] < 2 or self.pos[1] < 2 or self.pos[0] > self.width - 2 or self.pos[1] > self.height - 2:
                self.dead = True
            elif self.distance(self.pos, self.goal) < 5:
                self.reached_goal = True
            else:
                for obstacle in self.obstacles:
                    if obstacle.collidepoint(self.pos):
                        self.dead = True
                        break

    def calculate_fitness(self):
        """Calculate the fitness of the dot."""
        if self.reached_goal:
            self.fitness = 1.0 / 16.0 + 10000.0 / (self.brain.step * self.brain.step)
        else:
            distance_to_goal = self.distance(self.pos, self.goal)
            self.fitness = 1.0 / (distance_to_goal * distance_to_goal)

    def distance(self, pos1, pos2):
        """Calculate the distance between two points."""
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

    def clone(self):
        """Clone the dot."""
        clone = Dot(self.width, self.height, self.goal, self.obstacles)
        clone.brain = self.brain.clone()
        return clone