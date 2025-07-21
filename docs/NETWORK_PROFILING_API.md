# Network Profiling API Reference

Complete API reference for Riven's network profiling endpoints.

## Base URL

All endpoints are under `/api/v1/debug/` and require API authentication.

```
Base URL: http://localhost:8080/api/v1/debug/
Authentication: Bearer token in Authorization header
```

## Authentication

Include your API key in the Authorization header:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:8080/api/v1/debug/network-stats
```

## Endpoints

### Basic Statistics

#### GET /network-stats

Get comprehensive network profiling statistics.

**Response:**
```json
{
  "enabled": true,
  "total_requests": 1250,
  "average_duration": 1.85,
  "slow_requests_count": 45,
  "error_count": 12,
  "slow_requests_percentage": 3.6,
  "error_percentage": 0.96,
  "stored_requests": 1000,
  "max_stored_requests": 1000,
  "slow_threshold": 2.0
}
```

### Profiling Control

#### GET /network-profiling/status

Get current profiling status.

**Response:**
```json
{
  "enabled": true,
  "message": "Network profiling is enabled"
}
```

#### POST /network-profiling/enable

Enable network profiling.

**Response:**
```json
{
  "enabled": true,
  "message": "Network profiling enabled successfully"
}
```

#### POST /network-profiling/disable

Disable network profiling.

**Response:**
```json
{
  "enabled": false,
  "message": "Network profiling disabled successfully"
}
```

### Request Data

#### GET /network-profiling/slow-requests

Get recent slow requests.

**Parameters:**
- `limit` (optional): Maximum number of requests to return (1-1000, default: 50)

**Example:**
```bash
GET /network-profiling/slow-requests?limit=20
```

**Response:**
```json
{
  "slow_requests": [
    {
      "url": "https://api.example.com/slow-endpoint",
      "method": "GET",
      "status_code": 200,
      "duration": 5.23,
      "timestamp": "2024-01-15T10:30:45.123456",
      "success": true,
      "error_message": null,
      "service_name": "scraper_service",
      "domain": "api.example.com"
    }
  ],
  "total_count": 1,
  "threshold": 2.0
}
```

#### GET /network-profiling/summary

Get text summary of profiling statistics.

**Response:**
```json
{
  "message": "Network Profiling Summary:\n• Total requests: 1250\n• Average duration: 1.85s\n• Slow requests: 45 (3.6%)\n• Errors: 12 (0.96%)\n• Stored requests: 1000/1000\n• Slow threshold: 2.0s"
}
```

### Advanced Analytics

#### GET /network-profiling/advanced-stats

Get advanced statistics with percentiles and rates.

**Response:**
```json
{
  "enabled": true,
  "total_requests": 1250,
  "average_duration": 1.85,
  "percentiles": {
    "p50": 1.2,
    "p95": 4.8,
    "p99": 8.1
  },
  "recent_percentiles": {
    "p50": 1.1,
    "p95": 3.9,
    "p99": 6.2
  },
  "request_rate_per_second": 0.347,
  "recent_requests_count": 23,
  "slow_requests_count": 45,
  "error_count": 12,
  "slow_requests_percentage": 3.6,
  "error_percentage": 0.96
}
```

#### GET /network-profiling/domains

Get statistics grouped by domain.

**Response:**
```json
{
  "domain_stats": {
    "api.example.com": {
      "total_requests": 850,
      "average_duration": 1.65,
      "slow_requests": 25,
      "error_requests": 8,
      "slow_percentage": 2.94,
      "error_percentage": 0.94,
      "percentiles": {
        "p50": 1.1,
        "p95": 4.2,
        "p99": 7.8
      }
    }
  },
  "total_domains": 1
}
```

#### GET /network-profiling/services

Get statistics grouped by service.

**Response:**
```json
{
  "service_stats": {
    "scraper_service": {
      "total_requests": 650,
      "average_duration": 2.1,
      "slow_requests": 35,
      "error_requests": 5,
      "slow_percentage": 5.38,
      "error_percentage": 0.77,
      "percentiles": {
        "p50": 1.8,
        "p95": 5.2,
        "p99": 9.1
      }
    }
  },
  "total_services": 1
}
```

#### GET /network-profiling/patterns

Get statistics grouped by URL pattern.

**Response:**
```json
{
  "pattern_stats": {
    "api.example.com/users/{id}": {
      "total_requests": 320,
      "average_duration": 1.45,
      "slow_requests": 8,
      "error_requests": 2,
      "slow_percentage": 2.5,
      "error_percentage": 0.625,
      "percentiles": {
        "p50": 1.2,
        "p95": 3.8,
        "p99": 6.1
      }
    }
  },
  "total_patterns": 1
}
```

### Export

#### GET /network-profiling/export/json

Export profiling data as JSON.

**Parameters:**
- `include_requests` (optional): Include individual request data (default: true)

**Response:** JSON file download

#### GET /network-profiling/export/csv

Export profiling data as CSV.

**Response:** CSV file download with columns:
- timestamp
- url
- method
- status_code
- duration
- success
- error_message
- service_name
- domain
- url_pattern

### Health and Maintenance

#### GET /network-profiling/health

Get network health status.

**Response:**
```json
{
  "health_check_enabled": true,
  "status": "healthy",
  "recent_requests": 23,
  "recent_error_rate": 2.1,
  "recent_slow_rate": 4.3,
  "average_duration": 1.65
}
```

#### GET /network-profiling/memory-usage

Get memory usage information.

**Response:**
```json
{
  "requests_count": 1000,
  "estimated_bytes": 350000,
  "estimated_mb": "0.33"
}
```

#### POST /network-profiling/clear

Clear all stored profiling data.

**Response:**
```json
{
  "message": "Network profiling data cleared successfully"
}
```

#### POST /network-profiling/retention-policy

Apply retention policy to remove old data.

**Parameters:**
- `max_age_hours` (optional): Maximum age in hours (1-8760, default: 24)

**Example:**
```bash
POST /network-profiling/retention-policy?max_age_hours=12
```

**Response:**
```json
{
  "removed_count": 150,
  "remaining_count": 850,
  "message": "Removed 150 requests older than 12 hours"
}
```

### Alerting

#### GET /network-profiling/alerts/status

Get alert status and configuration.

**Response:**
```json
{
  "alerts_enabled": true,
  "last_alerts": {
    "slow_request": "2024-01-15T10:25:30.123456",
    "high_error_rate": null
  },
  "alert_settings": {
    "enable_alerts": true,
    "alert_slow_request_threshold": 10.0,
    "alert_error_rate_threshold": 15.0,
    "alert_cooldown_minutes": 60
  }
}
```

#### POST /network-profiling/alerts/test

Send a test alert.

**Response:**
```json
{
  "message": "Test alert sent successfully"
}
```

## Error Responses

All endpoints may return these error responses:

### 503 Service Unavailable
```json
{
  "detail": "Network profiling not available"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to retrieve network statistics"
}
```

### 400 Bad Request
```json
{
  "detail": "Limit must be between 1 and 1000"
}
```

### 401 Unauthorized
```json
{
  "detail": "Invalid API key"
}
```

## Rate Limits

- No specific rate limits for profiling endpoints
- General API rate limits apply
- Avoid excessive polling; use reasonable intervals

## Examples

### Monitor Error Rate

```bash
#!/bin/bash
API_KEY="your_api_key"
BASE_URL="http://localhost:8080/api/v1/debug"

while true; do
  stats=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/network-stats")
  error_rate=$(echo "$stats" | jq '.error_percentage')
  echo "$(date): Error rate: $error_rate%"
  
  if (( $(echo "$error_rate > 5" | bc -l) )); then
    echo "High error rate detected!"
  fi
  
  sleep 60
done
```

### Export Weekly Data

```bash
# Export data and apply retention policy
curl -H "Authorization: Bearer $API_KEY" \
  "$BASE_URL/network-profiling/export/json" \
  -o "weekly_data_$(date +%Y%m%d).json"

curl -X POST -H "Authorization: Bearer $API_KEY" \
  "$BASE_URL/network-profiling/retention-policy?max_age_hours=168"
```
