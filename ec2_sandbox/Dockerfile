FROM python:3.11-slim

# Minimal runner image — no unnecessary packages
RUN pip install --no-cache-dir pip --upgrade

WORKDIR /app

# Copy the runner script
COPY runner.py /runner.py

# The user project is mounted at /app (read-only)
# /tmp is writable for pip installs and temp files
ENTRYPOINT ["python", "/runner.py"]
