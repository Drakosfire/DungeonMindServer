# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install necessary networking tools
RUN apt-get update && apt-get install -y iputils-ping

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Create the saved_data directory and set correct permissions
RUN mkdir -p /home/user/app/saved_data && chown user:user /home/user/app/saved_data

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
	PATH=/home/user/.local/bin:/usr/local/bin:$PATH

# Set the working directory in the container
WORKDIR $HOME/app

# Install uv
RUN python -m pip install --upgrade pip && \
    pip install uv

# Copy dependency files first for better caching
COPY --chown=user pyproject.toml .
COPY --chown=user uv.lock .

# Install dependencies using uv
RUN uv venv && uv pip install -r uv.lock

# Copy the rest of the application
COPY --chown=user . .

# Expose port 7860 for the FastAPI app
EXPOSE 7860

# Define the command to run the FastAPI app with Uvicorn
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]