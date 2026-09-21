FROM python:3.11-slim

# Create app directory
WORKDIR /app

# Copy requirements
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose port (Render sets $PORT dynamically)
EXPOSE 8080

# Make start script executable
RUN chmod +x start.sh

# Start command
CMD ["./start.sh"]
