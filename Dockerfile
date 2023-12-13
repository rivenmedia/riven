# Use a base image with Python 3.12 and Node.js 18 on Alpine
FROM nikolaik/python-nodejs:python3.12-nodejs18-alpine

# Set the working directory
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy and install backend dependencies
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend code
COPY backend /app/backend

# Copy and install frontend dependencies
COPY frontend/package.json frontend/pnpm-lock.yaml /app/frontend/
RUN cd /app/frontend && pnpm install

# Copy frontend code
COPY frontend /app/frontend

# Build the frontend
RUN cd /app/frontend && pnpm run build

# Expose the port your backend runs on
EXPOSE 8000

# Start the frontend in preview mode and the backend
CMD sh -c 'cd /app/frontend && pnpm run preview & python /app/backend/main.py'
