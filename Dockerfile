# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV HOME=/home/user \
    PATH=$HOME/.local/bin:/usr/local/bin:$PATH \
    UV_CACHE_DIR=/tmp/uv-cache

# Install dependencies and tools
RUN apt-get update && apt-get install -y iputils-ping && \
    python -m pip install --upgrade pip && \
    pip install uv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a non-root user and app directory with correct permissions
RUN useradd -m -u 1000 user && \
    mkdir -p $HOME/app/saved_data /tmp/uv-cache && \
    chown -R user:user $HOME /tmp/uv-cache

# Set working directory before switching user
ENV UV_CACHE_DIR=/tmp/uv-cache \
    PATH=/home/user/.local/bin:/usr/local/bin:$PATH

WORKDIR /home/user/app

COPY --chown=user pyproject.toml .

RUN uv pip compile --quiet --no-emit-index-url --no-emit-find-links pyproject.toml > requirements.txt && \
    uv pip install --system -r requirements.txt


# Switch to non-root user
USER user

# Copy the rest of the application
COPY --chown=user . .

# Expose port for the app
EXPOSE 7860

# Default command to run the FastAPI app with Uvicorn via uv
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
