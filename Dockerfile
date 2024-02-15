# tiktok-challenge
FROM ubuntu:jammy AS tiktok_challenge.build

# Install Python 3.11
RUN apt-get update && apt-get install -y python3.11 && apt-get install -y python3-pip

# Setup directories
RUN mkdir -p /home/tiktok-challenge
WORKDIR /home/tiktok-challenge

# Copying project files
COPY . .

# Install PIP dependencies
RUN pip install -r requirements.txt

# Install Chromium dependencies
RUN playwright install chromium
RUN playwright install-deps

# Start service
EXPOSE 8000
CMD [ "python3", "main.py" ]
# CMD [ "gunicorn", "-w", "1", "-b", "0.0.0.0", "main:app" ]
