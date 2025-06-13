Here are the two detailed "how-to" guides you requested, outlining the setup for distributed chess engine computing and the creation of new machine learning-based AI engines. These guides consolidate information from our previous discussions and your provided project files, aiming to be actionable for implementation with the help of Gemini AI in VS Code Copilot.

-----

# 1\. Distributed Chess Engine Computing How-To Guide

This guide details how to set up a distributed computing network for your Viper Chess Engine, leveraging your existing Windows PCs and extending to a low-cost cloud environment like AWS. The goal is to efficiently run thousands or millions of game simulations and gather data for AI experimentation.

## Core Principles for Distributed Chess Engine Testing

Before diving into implementation, understanding these principles is key:

  * **Decoupling**: Separate your application into distinct, independent services:
      * **Game Runner/Worker**: An instance of your chess engine that plays games and generates data. This should be a lightweight, single-purpose unit.
      * **Metrics Storage**: A centralized database to store all game results, move-by-move data, and configuration details. This is the single source of truth for your analytics.
      * **Orchestration/Job Queue**: A system to manage and distribute game-playing tasks to available workers.
      * **Dashboard**: A visualization layer to monitor progress and analyze collected data.
  * **Stateless Workers**: Each game runner/worker should not retain state between game runs. It receives a task, executes it, reports results, and then is ready for a new, independent task. This simplifies scaling and fault tolerance.
  * **Centralized Data**: All output data (PGNs, detailed move metrics, game results, configurations) must be sent to a single, shared database. This is crucial for aggregated analysis and A/B testing.
  * **Scalability**: The architecture should allow you to easily add more workers (local PCs or cloud instances) to increase computational throughput without significant re-configuration.

## Step 1: Containerization with Docker

Docker allows you to package your application and its dependencies into a standardized unit (a container), ensuring it runs consistently across different environments (your various Windows PCs, Linux micro-PCs, or cloud servers).

### 1.1 Install Docker

  * **For Windows 10/11 Desktops/Laptops**: Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/). Ensure WSL 2 (Windows Subsystem for Linux 2) is enabled as Docker Desktop uses it for its backend.
  * **For Linux (Orange Pi, Raspberry Pi)**: Install [Docker Engine](https://docs.docker.com/engine/install/) directly.

### 1.2 Create a `Dockerfile`

In the root of your project, create a file named `Dockerfile`:

```dockerfile
# Dockerfile
# Use a slim Python base image for smaller container size
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file and install dependencies
# This step is cached if requirements.txt doesn't change, speeding up builds
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project directory into the container
COPY . .

# Set environment variables if needed (e.g., for database connection, Stockfish path)
# Stockfish path will be relative to /app/engine_utilities/external_engines/stockfish/
# DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME should be set dynamically or in Kubernetes/ECS
ENV VIPER_DB_HOST="localhost" \\\
    VIPER_DB_PORT="5432" \\\
    VIPER_DB_USER="chessuser" \\\
    VIPER_DB_PASSWORD="securepassword" \\\
    VIPER_DB_NAME="chess_metrics_db" \\\
    STOCKFISH_EXEC_PATH="/app/engine_utilities/external_engines/stockfish/stockfish-windows-x86-64-avx2.exe"

# Expose any ports if your application has a web interface (like the dashboard)
# EXPOSE 8050 # For the Dash dashboard

# Command to run your chess_game.py when the container starts
# The arguments passed will be available in sys.argv in chess_game.py
CMD ["python", "chess_game.py"]
```

### 1.3 Create `requirements.txt`

Ensure your `requirements.txt` includes all Python packages used:

```
pygame
python-chess
numpy
PyYAML
pandas
psutil
dash
plotly
sqlite3 # Although moving to PostgreSQL/MySQL, some modules might still rely on it internally or for initial setup
# For PostgreSQL:
psycopg2-binary
SQLAlchemy
```

### 1.4 Build the Docker Image

Navigate to your project root in the terminal and run:

```bash
docker build -t viper-chess-engine .
```

This will create a Docker image named `viper-chess-engine` which bundles your code and dependencies.

## Step 2: Centralized Database

SQLite is file-based and unsuitable for multiple concurrent writes from distributed workers, especially over a network. You need a robust, centralized database. PostgreSQL is an excellent open-source choice.

### 2.1 Choose a Database Solution

  * **Local Network**: Deploy **PostgreSQL** on one of your more powerful Windows desktops (e.g., the i9-11900k machine). You can run it directly or within Docker.
      * **Direct Installation (Windows)**: Download and install PostgreSQL from [postgresql.org](https://www.postgresql.org/download/windows/).
      * **Dockerized PostgreSQL**:
        ```bash
        docker run --name some-postgres -e POSTGRES_PASSWORD=securepassword -p 5432:5432 -d postgres
        ```
        This runs PostgreSQL in a container on a specified machine. Other machines can connect to `[IP_OF_POSTGRES_HOST]:5432`.
  * **Cloud (AWS)**: Use **Amazon RDS for PostgreSQL**. This is a managed service, meaning AWS handles setup, backups, patching, and scaling. It's not free tier eligible for continuous use but can be cost-effective for burst testing.

### 2.2 Update `MetricsStore` for PostgreSQL

Modify `metrics_store.py` to connect to PostgreSQL (or another SQL database) using SQLAlchemy.