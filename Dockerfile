FROM python:3.13-alpine

# Keep Python output unbuffered and avoid writing .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory in the container
WORKDIR /app

# Adjust packages if your requirements need additional system libs (e.g. libssl-dev, libxml2-dev).
RUN apk add --no-cache ca-certificates

# Install Python dependencies (no cache).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# Copy the rest of the application code
COPY . .

# Copy Reticulum config into the runtime user's home so it is available at ~/.reticulum/config
# (we will set secure permissions and chown after creating the runtime user below)
COPY config /home/appuser/.reticulum/config

# Create a non-root user and set ownership of the application directory and config
RUN adduser -D -u 1000 appuser || true && \
    chown -R appuser:appuser /app /home/appuser/.reticulum || true && \
    chmod 600 /home/appuser/.reticulum/config || true
USER appuser

# Expose the port the app runs on
EXPOSE 5000

# Use waitress to serve the app with 8 threads (expects Flask app object `app` in rBrowser.py)
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=8", "rBrowser:app"]
