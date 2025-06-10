# Setting Up Your Local Chess Engine Distributed Compute Environment

This guide will walk you through transforming your Beelink Mini PC into a robust central server for your chess engine's distributed compute environment, and then integrating your worker nodes (like your Orange Pi and other PCs) to report their results.

## Project Overview

  * **Goal:** Establish a local server/client architecture where distributed chess engine worker nodes (running on Orange Pi, other PCs) send game results and data to a central database on a Beelink Mini PC, which also hosts a web-based dashboard for visualization.
  * **Central Server (Product Owner / Main Server):** Beelink Mini S12 Pro (Intel N100, 16GB RAM, 500GB SSD)
  * **Worker Nodes (Developers / Compute Engines):** Orange Pi (Quad-core Cortex-A7, 238MB RAM) and other local PCs.
  * **Key Technologies:** Ubuntu Server, Docker, Docker Compose, PostgreSQL, Python (for data ingestion/dashboard backend), HTML/CSS/JS (for dashboard frontend).

-----

## Part 1: Setting Up the Beelink Mini PC (The Central Server)

The Beelink, with its significantly better specifications, is perfectly suited to be the brains of your operation – handling the database, data ingestion, and the dashboard.

### 1.1 Operating System Installation: Ubuntu Server

**Why Ubuntu Server?**
For a headless server that will run Docker and a database, Ubuntu Server is an excellent choice. It's free, highly optimized for server tasks, resource-efficient compared to Windows, boasts robust Docker support, and has a vast community for support.

**Steps:**

1.  **Download Ubuntu Server ISO:**

      * On a working computer, go to the official Ubuntu website ([ubuntu.com/download/server](https://ubuntu.com/download/server)) and download the latest **LTS (Long Term Support)** version (e.g., Ubuntu Server 22.04 LTS).

2.  **Create a Bootable USB Drive:**

      * Insert a USB flash drive (at least 4GB) into your working computer.
      * Use a tool like **Rufus (Windows)** or **Etcher (Windows/macOS/Linux)** to "burn" the downloaded ISO image onto the USB drive. This makes the USB drive bootable.

3.  **Install Ubuntu Server on Beelink:**

      * Connect a monitor and keyboard to your Beelink Mini PC for the initial installation.
      * Insert the bootable USB drive into the Beelink.
      * Power on the Beelink and repeatedly press the key to enter the BIOS/Boot Menu (commonly `Del`, `F2`, `F7`, `F10`, or `F12` – check your Beelink's documentation if unsure).
      * Select the USB drive as the boot device.
      * Follow the on-screen prompts for installation:
          * Choose your language.
          * Select "Install Ubuntu Server".
          * **Crucially:** When prompted for disk partitioning, choose to **"Erase disk and install Ubuntu"**. This will wipe the corrupt Windows installation.
          * Configure your network (DHCP is usually fine for a home network). Note down the IP address if displayed, or you'll find it later.
          * Create your user account (e.g., `pat`). Remember your username and password\!
          * **Select "Install OpenSSH server"** when prompted. This is vital for managing the Beelink headless after installation.
          * Complete the installation. Once finished, remove the USB drive when prompted and press Enter to reboot.
      * After reboot, you can disconnect the monitor and keyboard.

### 1.2 Initial Server Configuration

Now that Ubuntu Server is installed, you'll manage it remotely via SSH.

1.  **Access via SSH:**

      * From your main PC, open a terminal (Linux/macOS) or use an SSH client like PuTTY (Windows).
      * Connect to your Beelink:
        ```bash
        ssh pat@<Beelink_IP_Address>
        ```
      * Replace `<Beelink_IP_Address>` with the actual IP address of your Beelink (you might find this from your router's connected devices list if you didn't note it during installation).

2.  **Update System Packages:**

      * It's crucial to update your system after installation to get the latest security patches and software.

    <!-- end list -->

    ```bash
    sudo apt update
    sudo apt upgrade -y
    ```

3.  **Configure Firewall (UFW):**

      * The Uncomplicated Firewall (UFW) is installed by default on Ubuntu. It's vital for security.
      * Allow SSH access (so you don't lock yourself out) and then enable the firewall.

    <!-- end list -->

    ```bash
    sudo ufw allow ssh
    sudo ufw enable
    sudo ufw status verbose
    ```

      * Later, you'll need to allow ports for your database (PostgreSQL) and dashboard.

### 1.3 Install Docker & Docker Compose

Docker will allow you to package your database and applications into isolated containers, making management, updates, and portability incredibly easy.

1.  **Install Docker Engine and Docker Compose Plugin:**
    ```bash
    # Add Docker's official GPG key:
    sudo apt update
    sudo apt install apt-transport-https ca-certificates curl software-properties-common -y
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Add the Docker repository to Apt sources:
    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt update

    # Install Docker packages:
    sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
    ```
2.  **Add Your User to the `docker` Group:**
      * This allows you to run Docker commands without `sudo`.
    <!-- end list -->
    ```bash
    sudo usermod -aG docker pat # Replace 'pat' with your username
    newgrp docker # Apply group changes immediately, or log out and back in
    ```
3.  **Verify Installation:**
    ```bash
    docker run hello-world
    ```
    You should see a "Hello from Docker\!" message.

### 1.4 Set Up Central Database (PostgreSQL with Docker Compose)

While your chess engine uses SQLite locally, a central database requires a more robust, networked solution. PostgreSQL is an excellent choice for its reliability and features.

1.  **Create Project Directory:**

    ```bash
    mkdir -p ~/chess-server/database
    cd ~/chess-server/database
    ```

2.  **Create `docker-compose.yml` for PostgreSQL:**

      * Use a text editor like `nano` (`nano docker-compose.yml`).

    <!-- end list -->

    ```yaml
    version: '3.8'
    services:
      db:
        image: postgres:15 # Using PostgreSQL version 15
        restart: always
        environment:
          POSTGRES_DB: chess_results
          POSTGRES_USER: your_db_user # <--- CHANGE THIS to a strong, unique username!
          POSTGRES_PASSWORD: your_strong_password # <--- CHANGE THIS to a VERY strong, unique password!
        volumes:
          - ./data:/var/lib/postgresql/data # Persist database data
        ports:
          - "5432:5432" # Host_port:Container_port - Expose port 5432 to the host network
        healthcheck:
          test: ["CMD-SHELL", "pg_isready -U your_db_user -d chess_results"]
          interval: 5s
          timeout: 5s
          retries: 5
    ```

      * **Important:** Replace `your_db_user` and `your_strong_password` with secure credentials.

3.  **Start the Database Container:**

    ```bash
    docker compose up -d
    ```

    The `-d` flag runs it in "detached" mode (in the background).

4.  **Allow Database Port in Firewall:**

    ```bash
    sudo ufw allow 5432/tcp
    sudo ufw reload
    ```

5.  **Database Schema (Conceptual):**

      * You'll need to design your database schema (tables, columns) to store the extracted data from your PGN, YAML, and log files.
      * Example tables: `games` (for PGN data), `simulations` (for metadata from YAML), `worker_logs` (for log entries).
      * You can create these tables using a PostgreSQL client (e.g., `psql` from a Docker container or directly if you install it) once the database is running.

### 1.5 Data Ingestion & Dashboard Backend (Python with Docker)

This will be a custom Python application that acts as an API gateway for your worker nodes and serves data to your dashboard.

1.  **Conceptual Overview:**

      * **Functionality:**
          * **API Endpoint:** Expose an HTTP POST endpoint (e.g., `/submit_results`) where worker nodes can send their raw files (PGN, YAML, logs) or pre-parsed data.
          * **Data Processing:** Parse the incoming PGN, YAML, and log data.
          * **Database Insertion:** Connect to the PostgreSQL database and insert the parsed data into the appropriate tables.
          * **Dashboard APIs:** Provide additional GET endpoints for your web dashboard to retrieve aggregated or raw data from the database for visualization.
      * **Frameworks:** Use a lightweight Python web framework like **Flask** or **FastAPI**.
      * **Containerization:** This application will run in its own Docker container, defined by a `Dockerfile` and integrated into your `docker-compose.yml`.

2.  **Example `Dockerfile` (Conceptual):**

      * Create a directory for your backend app (e.g., `~/chess-server/backend`).
      * A simple `Dockerfile` would look like:
        ```dockerfile
        # backend/Dockerfile
        FROM python:3.10-slim
        WORKDIR /app
        COPY requirements.txt .
        RUN pip install -r requirements.txt
        COPY . .
        EXPOSE 8000 # Or whatever port your Flask/FastAPI app listens on
        CMD ["python", "app.py"] # Or "uvicorn app:app --host 0.0.0.0 --port 8000" for FastAPI
        ```

3.  **Integrate into `docker-compose.yml` (Conceptual):**

      * Add a new service to your existing `docker-compose.yml` (in `~/chess-server`):
        ```yaml
        # ~/chess-server/docker-compose.yml (updated)
        version: '3.8'
        services:
          db:
            # ... (PostgreSQL service as defined before) ...

          backend:
            build: ./backend # Points to the backend directory containing Dockerfile
            restart: always
            ports:
              - "8000:8000" # Expose backend API port
            environment:
              DATABASE_URL: postgresql://your_db_user:your_strong_password@db:5432/chess_results # Container-to-container communication
            depends_on:
              db:
                condition: service_healthy # Ensures DB is ready before backend starts
        ```
      * **Note:** The `DATABASE_URL` uses the service name `db` because Docker Compose sets up internal networking where services can resolve each other by their names.

4.  **Allow Backend Port in Firewall:**

      * If you expose your backend API on port 8000 (or another), allow it:

    <!-- end list -->

    ```bash
    sudo ufw allow 8000/tcp
    sudo ufw reload
    ```

### 1.6 Local Dashboard Frontend (Static Assets with Nginx in Docker)

This will be the web interface for visualizing your chess engine data.

1.  **Conceptual Overview:**

      * **Technology:** Simple HTML, CSS, and JavaScript. The JavaScript will make requests to your Python backend's API endpoints to fetch data and then use charting libraries (e.g., Chart.js, D3.js) to display it.
      * **Containerization:** Served by a lightweight web server like Nginx, also within a Docker container.

2.  **Example Structure:**

      * Create a directory for your frontend (e.g., `~/chess-server/frontend`).
      * Place your `index.html`, `style.css`, `script.js` files here.

3.  **Integrate into `docker-compose.yml` (Conceptual):**

      * Add another service to your `docker-compose.yml`:
        ```yaml
        # ~/chess-server/docker-compose.yml (updated)
        version: '3.8'
        services:
          db:
            # ...

          backend:
            # ...

          frontend:
            image: nginx:alpine # Lightweight Nginx image
            restart: always
            volumes:
              - ./frontend:/usr/share/nginx/html:ro # Mount your frontend files
            ports:
              - "80:80" # Or another port like 8080 if 80 is in use
            depends_on:
              - backend # Frontend depends on backend for data
        ```
      * **Access Dashboard:** Open your web browser and navigate to `http://<Beelink_IP_Address>`.

4.  **Allow Frontend Port in Firewall:**

    ```bash
    sudo ufw allow 80/tcp # Or 8080/tcp if you chose that port
    sudo ufw reload
    ```

-----

## Part 2: Configuring Worker Nodes (Orange Pi & Other PCs)

Your worker nodes will run the chess engine and send their results to the Beelink server.

### 2.1 Modify Chess Engine Output & Data Publishing

The core change here is to replace local file storage with network-based data submission.

1.  **Update Chess Engine Script:**
      * Locate the part of your Python chess engine script that writes game results (PGN), simulation metadata (YAML), and logs to files.
      * Modify this logic to:
          * **Read the generated data:** Even if it writes to temporary files first, read that data into Python variables.
          * **Send data via HTTP POST:** Use Python's `requests` library to send this data to your Beelink's backend API endpoint.
        <!-- end list -->
        ```python
        import requests
        import json # Or yaml, etc., depending on your data format

        BEELINK_API_URL = "http://<Beelink_IP_Address>:8000/submit_results" # Adjust port if different

        def send_results_to_server(pgn_data, yaml_data, log_data):
            payload = {
                "pgn": pgn_data,
                "yaml": yaml_data,
                "logs": log_data
            }
            try:
                response = requests.post(BEELINK_API_URL, json=payload, timeout=30)
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                print(f"Successfully submitted results: {response.json()}")
            except requests.exceptions.RequestException as e:
                print(f"Error submitting results: {e}")

        # Example usage after a game/simulation is done
        # pgn_content = "..."
        # yaml_content = "..."
        # log_content = "..."
        # send_results_to_server(pgn_content, yaml_content, log_content)
        ```
      * Ensure all worker nodes (Orange Pi, other PCs) have the `requests` library installed (`pip install requests`).

### 2.2 Orange Pi Specific Considerations

The Orange Pi, while limited in RAM, can still act as a dedicated worker.

1.  **Keep it Lean:** Only run the necessary services: the operating system and your chess engine with its modified Python script. Avoid unnecessary background processes.
2.  **Python Environment:** Ensure your Python environment on the Orange Pi (likely an ARM-compatible Python distribution) is correctly set up with all dependencies for your chess engine and the `requests` library.
3.  **Power & Stability:** Its low power consumption makes it ideal for continuous, long-running simulations.

-----

## Part 3: Future Considerations (Scaling & Advanced Orchestration)

Once your core setup is stable, you can explore further enhancements.

1.  **Automation & Monitoring:**

      * **System Updates:** Set up `unattended-upgrades` on Ubuntu to automate security updates.
      * **Docker Container Restarts:** Ensure `restart: always` is set for all your services in `docker-compose.yml`.
      * **Monitoring Tools:** Consider lightweight monitoring tools (e.g., Prometheus with Grafana) if you want to track server health and application metrics, though this adds complexity.

2.  **Security Hardening:**

      * **SSH Keys:** Disable password authentication for SSH and exclusively use SSH keys for more secure access.
      * **Database Access:** Configure your PostgreSQL database to only allow connections from specific IP addresses (your Beelink's internal Docker network and potentially your backend service).

3.  **Kubernetes (K3s/MicroK8s) as a Future Option:**

      * With the Beelink's 16GB RAM, running a lightweight Kubernetes distribution like **K3s** or **MicroK8s** becomes entirely feasible.
      * This would allow you to:
          * Orchestrate your database, backend, and frontend services with more advanced features (self-healing, scaling).
          * Potentially manage dynamic deployments of your chess engine worker processes directly on the Beelink, or use it as a master node to coordinate worker pods across multiple home PCs if you expand to a larger cluster.
      * **Recommendation:** Master the Docker Compose setup first. Kubernetes offers immense power but adds a significant layer of complexity.

-----

This guide should give you a solid roadmap to implement your vision for a powerful, yet cost-effective, local distributed compute environment. Good luck\!