# ============================================================
# AEGIS backend API image. This runs the FastAPI app only.
#
# It does NOT run MT5 workers - those require Windows + the real
# MT5 terminal (see requirements-worker.txt and app/worker/mt5_worker.py)
# and are deployed separately, pointed at this same Redis instance.
# ============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# opencv-python-headless avoids needing libGL, but still needs a couple
# of shared libs on a bare debian-slim image - without these, `import cv2`
# fails at container startup with an ImportError, not at build time, so
# it's easy to miss until you actually run the container.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY admin_dashboard ./admin_dashboard
COPY client_portal ./client_portal
COPY docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Run as a non-root user - limits the blast radius if the container is
# ever compromised. Needs write access to backend/data (SQLite files)
# and backend/uploads, so those are chowned explicitly.
RUN useradd --create-home --uid 1000 aegis \
    && mkdir -p backend/data backend/uploads \
    && chown -R aegis:aegis /app
USER aegis

WORKDIR /app/backend

EXPOSE 8000

# IMPORTANT: keep --workers 1 (set in entrypoint.sh) / run exactly one
# container replica. WorkerPoolManager spawns MT5 worker subprocesses
# tracked partly in this process's own memory - see worker_pool_manager.py's
# module docstring for the full explanation of what is and isn't safe to
# scale horizontally yet.
ENTRYPOINT ["/app/entrypoint.sh"]
