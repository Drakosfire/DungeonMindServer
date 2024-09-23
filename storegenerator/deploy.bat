@echo off

REM Stop the Docker container
echo Stopping Docker container 'storegenerator-container'...
docker stop storegenerator-container

REM Remove the Docker container
echo Removing Docker container 'storegenerator-container'...
docker rm storegenerator-container

REM Remove the Docker image
echo Removing Docker image 'storegenerator-image'...
docker rmi storegenerator-image

REM Build the Docker image
echo Building Docker image 'storegenerator-image'...
docker build -t storegenerator-image .

REM Run the Docker container with the specified environment file and port mapping
echo Running Docker container 'storegenerator-container'...
docker run --name storegenerator-container -d -p 7860:7860 -v "%cd%\.env:/app/.env" storegenerator-image

echo Script execution completed.
