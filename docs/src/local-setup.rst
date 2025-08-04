Local Setup
===========

Requirements
------------

- `Docker <https://docs.docker.com/get-docker/>`_
- `Docker Compose <https://docs.docker.com/compose/install/>`_
- Python 3.11 or higher (if running locally without Docker)

Starting Development
====================

To start the DashLab development environment, simply run the provided script:

.. code-block:: bash

   bash ./scripts/dev-start.sh

This will launch the necessary services (including the dashboard and database) using Docker Compose with live reloads for development.


Running Locally with Python
---------------------------

To run DashLab locally without Docker, follow these steps:

1. Create and activate a virtual environment:

   .. code-block:: bash

      python3 -m venv venv
      source venv/bin/activate  # On Windows: venv\Scripts\activate

2. Install dependencies using `uv` (a fast pip wrapper):

   .. code-block:: bash

      uv pip install ".[docs, tests]" --system

3. Run the application:

   .. code-block:: bash

      python3 -m app.main


Running Documentation Locally
=============================

To build and serve the documentation locally, you can use the provided script:

.. code-block:: bash

   bash ./scripts/docs-serve.sh

This script launches a dedicated Docker Compose service that handles all documentation dependencies and builds the docs automatically.

Once running, the documentation will be available in your browser at:

.. code-block:: text

   http://0.0.0.0:8000

Notes
-----

- Configure environment variables for AWS Cognito and MongoDB as needed from the .env.template file.
- Docker Compose includes MongoDB, so no separate installation is necessary if using Docker.
