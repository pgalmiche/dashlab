# 🧪 DashLab

[![pipeline status](https://gitlab.com/pgalmiche/dashlab/badges/main/pipeline.svg)](https://gitlab.com/pgalmiche/dashlab/-/pipelines)

[![coverage report](https://gitlab.com/pgalmiche/dashlab/badges/main/coverage.svg)](https://gitlab.com/pgalmiche/dashlab/-/commits/main)

[📘 View Documentation](https://pgalmiche.gitlab.io/dashlab/)

---

## 🧭 Overview

**DashLab** is a unified and interactive dashboard designed to interface with various APIs.
It serves as a developer-centric tool to **run**, **test**, and **visualize** multiple API endpoints from a centralized UI.

My personal and daily used instance of **DashLab** is available at [https://dashlab.pierregalmiche.link/](https://dashlab.pierregalmiche.link/)
Feel free to explore it !

For more insights into the project and its dependencies, check out [my wiki](https://wiki.pierregalmiche.link/Projects/DashLab/).

👤 Want to know more about me and other things I build?  
Check out my personal website at 👉 [https://pierregalmiche.link](https://pierregalmiche.link)

---

## 📦 Usage

These helper scripts ensure consistent usage across environments:

- **Development start**

  ```bash
  bash ./scripts/dev-start.sh
  ```

  Launches the dashboard in a local development environment.
  Then, open your browser and visit: [http://0.0.0.0:7777](http://0.0.0.0:7777)

- **Build production image** (for local test if you want)

  ```bash
  bash ./scripts/prod-build.sh
  ```

  Builds the production-ready Docker image.

- **Run tests**

  ```bash
  bash ./scripts/test-run.sh
  ```

  Executes the test suite (unit/integration depending on setup).

- **Serve documentation locally**

  ```bash
  bash ./scripts/docs-serve.sh
  ```

  Builds and serves the Sphinx documentation at [http://0.0.0.0:8000](http://0.0.0.0:8000)

---

## 🚀 CI/CD Pipeline (GitLab):w

The CI/CD pipeline is configured via GitLab and is automatically triggered on the `main` branch.

It performs the following steps:

1. **Build the production Docker image**:
   The latest commit is used to build the image using the `docker/Dockerfile` and tag it appropriately.

1. **Push and deploy to EC2**:
   The image is pushed to AWS ECR and automatically deployed to the EC2 instance via SSH. The container is restarted with the new image version.

1. **Generate and publish documentation**:
   The Sphinx documentation is built and published to GitLab Pages.
   📄 View it here: [https://pgalmiche.gitlab.io/dashlab/](https://pgalmiche.gitlab.io/dashlab/)

---

## 🧷 Pre-commit Hook Setup

To enable pre-commit hooks (run via Docker for consistency):

```bash
bash ./scripts/precommit-hook-install.sh
```

This installs hooks that enforce code quality (e.g., linting, formatting) before any commit. The hooks run inside a containerized environment, ensuring all contributors use the same tooling.

---

## 📁 .env Configuration

This project relies on environment variables to manage secrets and configuration.

- Use `.env.template` as a reference
- Copy it to `.env` and fill in your values:

```bash
cp .env.template .env
```

Ensure you complete the required fields before starting the dashboard or running builds/tests.

---

## ✅ Best Practices

- Use the provided scripts for all operations to avoid inconsistent environments.
- Keep `.env` up to date and **never commit secrets**.
- Always run tests before pushing changes.
- Use pre-commit hooks to catch issues early.

---

## 🛠️ Tech Stack

- Python / FastAPI / Flask / etc. _(adapt based on your backend)_
- Docker
- GitLab CI/CD
- AWS ECR & EC2
- [Sphinx](https://www.sphinx-doc.org/en/master/) for documentation

---

## 🧳 License

MIT License. See `LICENSE` for details.
