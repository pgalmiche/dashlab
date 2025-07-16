FROM python:3.10-slim


# use poetry for dependencies management
COPY pyproject.toml ./
RUN pip3 install poetry
RUN poetry config virtualenvs.create false
RUN poetry install -n --no-ansi

WORKDIR /usr/src/app


