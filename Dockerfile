# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH

# Install dependencies and tools
RUN apt-get update && apt-get install -y iputils-ping && \
    python -m pip install --upgrade pip && \
    pip install uv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create user and app directory
RUN useradd -m -u 1000 user && \
    mkdir -p /home/user/app/saved_data && \
    chown -R user:user /home/user

WORKDIR /home/user/app

# Copy dependency files
COPY --chown=user pyproject.toml .

# Install dependencies using uv without virtual environment
RUN uv pip compile --quiet --no-emit-index-url --no-emit-find-links pyproject.toml > requirements.txt && \
    uv pip install --system -r requirements.txt

# Switch to non-root user
USER user

# Copy the rest of the application
COPY --chown=user . .

# Expose port for the app
EXPOSE 7860

# Run the FastAPI app with Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

