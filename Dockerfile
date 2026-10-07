# Polaris: one Next.js site in front of four Python engines.
#
# The engines need conflicting library versions, so they share two virtual
# environments rather than four: SCOPE and netzero-ai are built against
# pandas 3, Task3 and task1 against pandas 2. Every version here matches the
# one each project is developed and tested against, because the committed
# models are pickles and will refuse to load against a different scikit-learn.

FROM node:22-bookworm-slim AS web
WORKDIR /src/Polaris/web
COPY Polaris/web/package.json Polaris/web/package-lock.json ./
RUN npm ci
COPY Polaris/web ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build


FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production

# Node for the web server; the Python base image already provides the interpreter.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

WORKDIR /app
COPY deploy/requirements-a.txt deploy/requirements-b.txt /app/deploy/
RUN python -m venv /venvs/a && /venvs/a/bin/pip install --no-cache-dir -r /app/deploy/requirements-a.txt \
 && python -m venv /venvs/b && /venvs/b/bin/pip install --no-cache-dir -r /app/deploy/requirements-b.txt

# The engines resolve their project directories relative to this layout, so keep it.
COPY SCOPE /app/SCOPE
COPY Task3 /app/Task3
COPY task1 /app/task1
COPY netzero-ai /app/netzero-ai
COPY Polaris/engines /app/Polaris/engines

# The microgrid's dataset and forecasters are regenerable, so they are built here
# instead of being committed. The generator is seeded, so this reproduces the
# same synthetic day the project is developed against.
RUN cd /app/netzero-ai \
 && /venvs/a/bin/python -m src.data.generate_demo_data \
 && /venvs/a/bin/python -m src.forecasting.train_all
COPY --from=web /src/Polaris/web/.next /app/Polaris/web/.next
COPY --from=web /src/Polaris/web/node_modules /app/Polaris/web/node_modules
COPY Polaris/web/package.json Polaris/web/next.config.ts /app/Polaris/web/

ENV SCOPE_PYTHON=/venvs/a/bin/python \
    NETZERO_PYTHON=/venvs/a/bin/python \
    TASK3_PYTHON=/venvs/b/bin/python \
    TASK1_PYTHON=/venvs/b/bin/python \
    SCOPE_DIR=/app/SCOPE \
    TASK3_DIR=/app/Task3 \
    TASK1_DIR=/app/task1 \
    NETZERO_DIR=/app/netzero-ai

WORKDIR /app/Polaris/web
EXPOSE 3100
# Railway supplies PORT; 3100 keeps `docker run` matching the local site.
CMD ["sh", "-c", "exec npx next start -p ${PORT:-3100} -H 0.0.0.0"]
