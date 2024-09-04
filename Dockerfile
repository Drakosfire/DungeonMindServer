# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set up a new user named "user" with user ID 1000
RUN useradd -m -u 1000 user

# Switch to the "user" user
USER user

# Set home to the user's home directory
ENV HOME=/home/user \
	PATH=/home/user/.local/bin:$PATH

# Set the working directory in the container
WORKDIR $HOME/app

# Copy the current directory contents into the container at $HOME/app setting the owner to the user
COPY --chown=user . $HOME/app
# Copy the current directory contents into the container at $HOME/app setting the owner to the user
COPY --chown=user storegenerator $HOME/app/storegenerator

# Install any necessary dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt


# Expose port 5000 for the Flask app
EXPOSE 7860

# Define environment variable to ensure Flask runs the correct application
ENV FLASK_APP=app.py
ENV FLASK_ENV=production  

# Command to run the Flask app
CMD ["flask", "run", "--host=0.0.0.0", "--port=7860"]