# Git Workflow Guide: `prod`, `non-prod`, and `main` Branch Strategy

This guide outlines the structured Git workflow for managing our project's codebase across three distinct branches: `main`, `non-prod`, and `prod`. This tiered approach ensures code quality, prevents regressions, and maintains clear sources of truth for development, integration, and production deployment.

## 1. Understanding the Branch Strategy

Imagine our Git repository as a multi-stage manufacturing process, where each branch represents a different level of refinement and readiness for our product.

### 1.1. `main` Branch (The Master Project Archive / Raw Materials)

* **Purpose:** The comprehensive, overarching source of truth for the *entire project*. This branch contains *all* code, documentation, experimental features, research, project management artifacts, and anything else related to the project.
* **Content:** Everything. This is our project's complete historical record, including files not intended for `prod` or `non-prod` (e.g., design docs, prototypes).
* **Workflow:** Primarily receives merges from `non-prod`. Specialized CI/CD pipelines will filter and deploy `prod`-specific content *from* `main` *to* `prod`. Direct commits are highly discouraged and restricted by branch protection rules.
* **Rule Gates:** Strong protection, requiring Pull Requests and status checks for merges.

### 1.2. `non-prod` Branch (The Component Assembly Line / Development Integration)

* **Purpose:** Your primary integration and testing branch for active development. This is where features and bug fixes from individual developer branches are integrated and thoroughly tested *before* they are considered for `main`. It should always remain in a functional, deployable state (though not necessarily production-ready).
* **Content:** A clean reflection of `main` plus all integrated developer changes intended for the application.
* **Workflow:**
    * Developers **pull** from `non-prod` to create new feature branches.
    * Individual feature branches then **push** their changes and submit **Pull Requests** back into `non-prod`.
    * `non-prod` periodically **merges** its accumulated, tested changes into `main` via a Pull Request.
* **Rule Gates:** Strong protection, requiring Pull Requests, approvals, and status checks for merges.

### 1.3. `prod` Branch (The Certified Product Line / Final Release)

* **Purpose:** This is your **release** branch. Only code that has been rigorously tested, verified, and deemed ready for distribution/deployment should ever land here. It's your single source of truth for what's live or ready to be live. It must always contain perfect, running code.
* **Content:** Minimalist and focused on deployable, runtime-essential code. No project management docs, experimental features, or non-essential files.
* **Workflow:** Extremely restricted. Only successful, automated CI/CD pipelines can **push** to this branch, taking *filtered* and verified code from `main`. Direct human pushes or merges from other branches are forbidden.
* **Rule Gates:** Highest level of protection, ensuring an "untouchable" and pristine state.

## 2. Setting Up Branches and Protection Rules in GitHub

To enforce this workflow, we'll configure branch protection rules in GitHub. You need owner or admin access to the repository.

### 2.1. Create the Branches

1.  Navigate to your GitHub repository.
2.  Click on the **"Code"** tab.
3.  Click on the branch dropdown (usually says `main`).
4.  Type `prod` in the search box and click **"Create branch: prod from main"**.
5.  Repeat this process to create the `non-prod` branch from `main`.

### 2.2. Configure Branch Protection Rules

1.  Go to your GitHub repository.
2.  Click on **"Settings"** (top right).
3.  In the left sidebar, click **"Branches"**.

#### 2.2.1. Branch Protection for `prod` (Highest Restrictions)

Click **"Add rule"** and enter `prod` as the "Branch name pattern."
Configure the following settings:

* **Require a pull request before merging:**
    * `Require approvals`: **1 or 2** (Strongly recommended).
    * `Dismiss stale pull request approvals when new commits are pushed`: **✅ Yes**
    * `Require review from Code Owners`: (Optional, recommended for large teams)
* **Require status checks to pass before merging:**
    * `Require branches to be up to date before merging`: **✅ Yes**
    * `Required status checks`: (Initially empty, but **add your CI/CD build/test statuses here once pipelines are set up**, e.g., "build-success", "tests-pass").
* **Require signed commits:** (Optional, high security, adds overhead).
* **Require linear history:** **✅ Yes** (Crucial for a clean `prod` history).
* **Do not allow bypassing the above settings:** **✅ Yes** (Highly recommended for `prod`).
* **Restrict who can push to matching branches:**
    * **Specify roles that can push:** **Select NONE** or only specific CI/CD bot users. **No human developers should be able to directly push to `prod`.**
    * `Allow force pushes`: **❌ No** (Absolutely forbidden for `prod`).

#### 2.2.2. Branch Protection for `non-prod` (Development Integration)

Click **"Add rule"** and enter `non-prod` as the "Branch name pattern."
Configure the following settings:

* **Require a pull request before merging:**
    * `Require approvals`: **1** (Recommended).
    * `Dismiss stale pull request approvals when new commits are pushed`: **✅ Yes**
    * `Require review from Code Owners`: (Optional).
* **Require status checks to pass before merging:**
    * `Require branches to be up to date before merging`: **✅ Yes**
    * `Required status checks`: (Add your development-level CI checks here, e.g., "lint", "unit-tests").
* **Require linear history:** (Optional, depends on team preference. If enabled, feature branches must rebase before merging. If disabled, merge commits are allowed).
* **Do not allow bypassing the above settings:** **✅ Yes** (Recommended).
* **Restrict who can push to matching branches:**
    * **Specify roles that can push:** Allow your team members with "Write" access. **Direct pushes are generally discouraged; everything should go through a PR.**
    * `Allow force pushes`: **❌ No** (Forbidden).

#### 2.2.3. Branch Protection for `main` (Comprehensive Archive)

Click **"Add rule"** and enter `main` as the "Branch name pattern."
Configure the following settings:

* **Require a pull request before merging:**
    * `Require approvals`: **1** (Recommended).
    * `Dismiss stale pull request approvals when new commits are pushed`: **✅ Yes**
* **Require status checks to pass before merging:** (You might have CI pipelines that run on `main` to ensure overall project health, or just the basic ones).
    * `Require branches to be up to date before merging`: **✅ Yes**
* **Require linear history:** **✅ Yes** (Recommended for a cleaner `main` history).
* **Do not allow bypassing the above settings:** **✅ Yes**
* **Restrict who can push to matching branches:**
    * **Specify roles that can push:** Allow your team members with "Write" access. **Direct pushes are generally discouraged; everything should go through a PR.**
    * `Allow force pushes`: **❌ No** (Forbidden).

## 3. Recommended Workflow for Developers

This section outlines how developers should interact with the new branch structure.

### 3.1. Starting a New Feature or Bug Fix

1.  **Start from `non-prod`:** Always ensure your local `non-prod` branch is up-to-date.
    ```bash
    git checkout non-prod
    git pull origin non-prod
    ```
2.  **Create a new feature branch:**
    ```bash
    git checkout -b feature/your-feature-name
    ```
    (For bug fixes, use `bugfix/your-bug-description`).

### 3.2. Working on Your Feature Branch

1.  **Code and Commit:** Work on your changes, making small, atomic commits with clear messages.
    ```bash
    git add .
    git commit -m "feat: implemented user login"
    ```
2.  **Push your branch:** Push your feature branch to the remote regularly.
    ```bash
    git push origin feature/your-feature-name
    ```
3.  **Keep up-to-date (optional but recommended):** Periodically pull changes from `non-prod` into your feature branch to avoid large merge conflicts later.
    ```bash
    git pull origin non-prod
    # Resolve any conflicts that arise
    ```

### 3.3. Submitting Your Changes to `non-prod`

1.  **Ensure your feature branch is ready:** All code is working, tested locally, and matches coding standards.
2.  **Push your final changes:**
    ```bash
    git push origin feature/your-feature-name
    ```
3.  **Create a Pull Request:** Go to GitHub and create a Pull Request from `feature/your-feature-name` to `non-prod`.
4.  **Review and Checks:** Your PR will go through required approvals and automated status checks (e.g., linter, unit tests). Address any feedback or failing checks.
5.  **Merge:** Once all checks pass and approvals are given, merge your PR into `non-prod`.

## 4. Automation with GitHub Actions (Initial Setup)

GitHub Actions will be used to enforce rules and automate deployments. Workflows are defined in `.github/workflows/*.yml` files.

### 4.1. Basic Code Quality Check (for `non-prod` and `main` PRs)

This workflow runs on Pull Requests targeting `non-prod` and `main` to ensure code style and basic syntax.

**File:** `.github/workflows/code-quality.yml`

```yaml
name: Code Quality Check

on:
  pull_request:
    branches:
      - non-prod
      - main
    types: [opened, synchronize, reopened]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node.js (Example: Adjust for your language/runtime)
        uses: actions/setup-node@v4
        with:
          node-version: '20' # Or Python: '3.10', Java: '17', etc.

      - name: Install dependencies (Adjust command as needed)
        run: npm install # e.g., pip install -r requirements.txt, mvn clean install

      - name: Run Linter (Adjust command as needed)
        run: npm run lint # e.g., flake8 ., dotnet format

      - name: Run Basic Build Check (Optional: Adjust command as needed)
        run: npm run build # e.g., mvn compile, dotnet build
```
**Action:** Once this file is in your repository, go to **Settings > Branches** and **enable this workflow** under "Require status checks to pass before merging" for `non-prod` and `main`.

### 4.2. `prod` Deployment Workflow (Manual Trigger for now)

This workflow is manually triggered to deploy a verified version from `main` to `prod` and your production environment.

**File:** `.github/workflows/deploy-prod.yml`

```yaml
name: Deploy to Prod (Manual Trigger)

on:
  workflow_dispatch: # Allows manual trigger from GitHub Actions tab

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: prod # Link to GitHub Environment for secrets and deployment history
    steps:
      - name: Checkout main branch
        uses: actions/checkout@v4
        with:
          ref: main # We deploy prod-ready code from main

      - name: Filter Prod-Specific Files (Crucial: Implement YOUR logic here)
        # This step ensures only necessary files for prod are included.
        # Examples:
        # - Copy only the 'dist' or 'build' directory.
        # - Use rsync with include/exclude patterns.
        # - Leverage .dockerignore if building a Docker image.
        run: |
          echo "Executing script to filter and prepare prod-specific files..."
          # Example (replace with actual commands):
          # mkdir temp_prod_build
          # cp -r app_source/ temp_prod_build/
          # rm -rf temp_prod_build/docs temp_prod_build/experiments # Remove unwanted dirs

      - name: Build Prod Artifacts (If applicable: Adjust command as needed)
        run: |
          echo "Building production-ready artifacts..."
          # Example (replace with actual commands):
          # npm run build --production
          # mvn clean package -Pprod

      - name: Execute Production Deployment (Crucial: Implement YOUR deployment commands)
        # This is where your code is deployed to your actual production environment.
        run: |
          echo "Deploying filtered and built artifacts to production..."
          # Example (replace with actual commands):
          # aws s3 sync ./temp_prod_build s3://your-prod-bucket
          # kubectl apply -f kubernetes/prod/
          # ssh user@prod-server "cd /var/www/app && git pull && systemctl restart app"

      - name: Push Filtered/Built Code to 'prod' branch (Optional, but aligns with your goal)
        # This step updates the 'prod' branch with the *filtered, deployable* code.
        # This provides a "hard copy" of what was actually deployed.
        # IMPORTANT: Ensure your 'prod' branch protection allows pushes from this bot/user.
        run: |
          git config user.name "GitHub Actions Bot"
          git config user.email "actions@github.com"
          git checkout -b prod_deploy_temp_branch # Create a temporary branch
          git add . # Add all filtered/built files from the action's workspace
          git commit -m "Automated Prod Deployment from Main (filtered)"
          git push origin prod_deploy_temp_branch:prod --force # Force push, use with extreme caution!
          # A safer alternative if 'prod' can always be a fast-forward:
          # git push origin prod_deploy_temp_branch:prod
          # For your use case (filtered code), force push is often necessary if the history isn't perfectly linear.
```
**Action:** Replace the placeholder commands for `Filter Prod-Specific Files`, `Build Prod Artifacts`, and `Execute Production Deployment` with your actual project's commands. Consider carefully if `git push --force` is appropriate for your `prod` branch, given its "untouchable" nature. Often, the `prod` branch just contains the deployable code, and its history is rebuilt by such pushes.

## 5. Merging Strategy

* **Feature Branch to `non-prod`:** Create a PR from your `feature/branch` to `non-prod`.
* **`non-prod` to `main`:** Periodically (e.g., at the end of a sprint or after major features are stable), create a PR from `non-prod` to `main`. This brings all integrated and tested changes from `non-prod` into your comprehensive `main` archive.
* **`main` to `prod`:** This is *not* a direct merge. Instead, it's a **deployment trigger**. When `main` is ready for release, you manually trigger the `Deploy to Prod` GitHub Actions workflow. This workflow takes the *relevant* parts of `main`, processes them (builds, filters), and then deploys to production and updates the `prod` branch.

## 6. Git LFS (Large File Storage) Reminders

Since you mentioned `chess_metrics.db` is an LFS file:

* Ensure your `.gitattributes` file correctly tracks `chess_metrics.db` with LFS (e.g., `chess_metrics.db filter=lfs diff=lfs merge=lfs -text`).
* When performing `git checkout` or `git pull` operations, Git LFS will automatically handle the download/smudging of the actual large file content. Ensure Git LFS is installed on all machines interacting with the repository.

This comprehensive guide will help you maintain a clean, organized, and robust Git repository, minimizing the risk of issues and ensuring a clear path from development to production.