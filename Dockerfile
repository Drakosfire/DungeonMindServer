# Use an official Python runtime as a parent image
FROM python:3.10-slim

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

# Copy the current directory contents into the container at $HOME/app
COPY --chown=user . $HOME/app

# Debug: Check Python installation
RUN which python && \
	python --version && \
	echo $PATH

# Upgrade pip and install dependencies
RUN python -m pip install --upgrade pip && \
	python -m pip install --no-cache-dir -r requirements.txt

# Expose port 7860 for the FastAPI app
EXPOSE 7860

# Define the command to run the FastAPI app with Uvicorn, define host to dev.dungeonmind.net and port to 7860
CMD ["python", "app.py", "--host", "dev.dungeonmind.net", "--port", "7860"]