FROM python:3.9-slim

WORKDIR /project
RUN pip install poetry
COPY poetry.lock .
COPY pyproject.toml .
RUN poetry install
COPY mock_api/* ./
RUN chmod 500 *.sh

CMD ["/project/startup.sh"]

