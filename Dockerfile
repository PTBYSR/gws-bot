FROM python:3.11-slim

# Install Node.js
RUN apt-get update && apt-get install -y curl
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
RUN apt-get install -y nodejs

# Create app directory
WORKDIR /app

# Copy requirements and package files
COPY requirements.txt ./
COPY whatsapp/package*.json ./whatsapp/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN cd whatsapp && npm install

# Copy application source
COPY . .

# Expose port (Render sets $PORT dynamically)
EXPOSE 8080

# Make start script executable
RUN chmod +x start.sh

# Start command
CMD ["./start.sh"]
