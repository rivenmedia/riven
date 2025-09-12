#!/bin/sh
echo "🔧 Starting Dramatiq workers..."

# Default worker configuration
WORKER_PROCESSES=${WORKER_PROCESSES:-2}
WORKER_THREADS=${WORKER_THREADS:-4}

echo "🔧 Worker config: $WORKER_PROCESSES processes, $WORKER_THREADS threads each"

# Test broker connection before starting workers
echo "🔧 Testing broker connection..."
cd src && poetry run python -c "
from program.queue.broker import test_broker_connection
import sys
if not test_broker_connection():
    print('❌ Failed to connect to broker, exiting...')
    sys.exit(1)
print('✅ Broker connection successful')
"

if [ $? -ne 0 ]; then
    echo "❌ Broker connection failed, exiting..."
    exit 1
fi

echo "🔧 Starting workers..."

exec poetry run dramatiq program.queue.workers \
    --processes $WORKER_PROCESSES \
    --threads $WORKER_THREADS
