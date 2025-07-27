# Network Profiling

Network profiling system to monitor HTTP request performance and identify bottlenecks.

## Configuration

Add to your settings:

```python
network_profiling:
  enabled: true
  slow_request_threshold: 2.0  # seconds
  max_stored_requests: 1000
```

## Usage

### CLI Commands

```bash
# Enable profiling
riven profiling enable

# View stats
riven profiling stats

# Disable profiling
riven profiling disable
```

### API Endpoints

All endpoints require API authentication and are under `/api/v1/debug/`:

- `GET /network-stats` - Get profiling statistics
- `GET /network-profiling/status` - Check profiling status
- `POST /network-profiling/enable` - Enable profiling
- `POST /network-profiling/disable` - Disable profiling

Example:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:8080/api/v1/debug/network-stats
```


