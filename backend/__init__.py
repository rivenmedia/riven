
import os
import time

if 'TZ' not in os.environ:
    os.environ['TZ'] = 'UTC'
    time.tzset()
