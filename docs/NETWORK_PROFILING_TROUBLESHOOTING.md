# Network Profiling Troubleshooting Guide

This guide helps you diagnose and resolve common issues with Riven's network profiling system.

## Quick Diagnostics

### Check Profiling Status

```bash
# Check if profiling is enabled
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:8080/api/v1/debug/network-profiling/status

# Get current statistics
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:8080/api/v1/debug/network-stats
```

### Enable Debug Logging

Add to your settings:
```json
{
  "debug": true,
  "log": true
}
```

## Common Issues

### 1. Profiling Not Working

**Symptoms:**
- No data in `/debug/network-stats`
- Profiling status shows `enabled: false`
- No slow request logs

**Solutions:**

1. **Check Settings:**
   ```json
   {
     "network_profiling": {
       "enabled": true
     }
   }
   ```

2. **Enable via CLI:**
   ```bash
   python main.py --profile-network
   ```

3. **Enable via API:**
   ```bash
   curl -X POST -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/v1/debug/network-profiling/enable
   ```

4. **Check Debug Mode:**
   Profiling auto-enables when `debug: true`

### 2. No Data Showing

**Symptoms:**
- Profiling enabled but no requests recorded
- Empty statistics

**Solutions:**

1. **Make Some Requests:**
   Profiling only tracks actual HTTP requests made by services

2. **Check Memory Limits:**
   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/v1/debug/network-profiling/memory-usage
   ```

3. **Verify Request Handlers:**
   Ensure services are using `BaseRequestHandler`

### 3. High Memory Usage

**Symptoms:**
- Increasing memory consumption
- System slowdown

**Solutions:**

1. **Reduce Storage Limit:**
   ```json
   {
     "network_profiling": {
       "max_stored_requests": 500
     }
   }
   ```

2. **Apply Retention Policy:**
   ```bash
   curl -X POST -H "Authorization: Bearer YOUR_API_KEY" \
     "http://localhost:8080/api/v1/debug/network-profiling/retention-policy?max_age_hours=12"
   ```

3. **Clear Data:**
   ```bash
   curl -X POST -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/v1/debug/network-profiling/clear
   ```

### 4. Alerts Not Working

**Symptoms:**
- No alert notifications
- High error rates but no alerts

**Solutions:**

1. **Enable Alerts:**
   ```json
   {
     "network_profiling": {
       "enable_alerts": true
     }
   }
   ```

2. **Configure Notifications:**
   ```json
   {
     "notifications": {
       "enabled": true,
       "service_urls": ["discord://webhook_id/webhook_token"]
     }
   }
   ```

3. **Test Alerts:**
   ```bash
   curl -X POST -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/v1/debug/network-profiling/alerts/test
   ```

4. **Check Thresholds:**
   ```json
   {
     "network_profiling": {
       "alert_slow_request_threshold": 10.0,
       "alert_error_rate_threshold": 15.0
     }
   }
   ```

### 5. Performance Issues

**Symptoms:**
- Slower response times
- High CPU usage

**Solutions:**

1. **Disable Profiling:**
   ```bash
   curl -X POST -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/v1/debug/network-profiling/disable
   ```

2. **Reduce Data Collection:**
   ```json
   {
     "network_profiling": {
       "max_stored_requests": 100,
       "log_slow_requests": false
     }
   }
   ```

3. **Monitor Impact:**
   ```bash
   # Check memory usage
   curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/v1/debug/network-profiling/memory-usage
   ```

## Error Messages

### "Network profiling not available"

**Cause:** Import error or module not found

**Solution:**
1. Restart Riven
2. Check for Python import errors in logs
3. Verify file permissions on `src/program/utils/network_profiler.py`

### "Failed to retrieve network statistics"

**Cause:** Internal error in profiler

**Solution:**
1. Check logs for detailed error messages
2. Clear profiling data: `POST /debug/network-profiling/clear`
3. Restart profiling: `POST /debug/network-profiling/disable` then `POST /debug/network-profiling/enable`

### "Rate limit exceeded"

**Cause:** Too many API requests

**Solution:**
1. Reduce API polling frequency
2. Use webhooks instead of polling where possible

## Performance Optimization

### Recommended Settings

For **production environments:**
```json
{
  "network_profiling": {
    "enabled": false,
    "max_stored_requests": 500,
    "log_slow_requests": true,
    "enable_alerts": true,
    "alert_slow_request_threshold": 15.0
  }
}
```

For **development environments:**
```json
{
  "network_profiling": {
    "enabled": true,
    "max_stored_requests": 1000,
    "log_slow_requests": true,
    "slow_request_threshold": 2.0,
    "enable_alerts": false
  }
}
```

For **debugging issues:**
```json
{
  "debug": true,
  "network_profiling": {
    "enabled": true,
    "max_stored_requests": 2000,
    "log_slow_requests": true,
    "slow_request_threshold": 1.0
  }
}
```

## Monitoring Commands

### Health Check Script

```bash
#!/bin/bash
API_KEY="your_api_key"
BASE_URL="http://localhost:8080/api/v1/debug"

# Get health status
health=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/network-profiling/health")
echo "Health: $health"

# Get memory usage
memory=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/network-profiling/memory-usage")
echo "Memory: $memory"

# Get recent error rate
stats=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/network-stats")
error_rate=$(echo "$stats" | jq '.error_percentage')
echo "Error rate: $error_rate%"
```

### Log Analysis

```bash
# Find slow request logs
grep "Slow request detected" /path/to/riven.log

# Find profiling errors
grep "network profiling" /path/to/riven.log | grep -i error

# Monitor memory usage
grep "NetworkProfiler" /path/to/riven.log | grep -i memory
```

## Getting Help

If you're still experiencing issues:

1. **Check Logs:** Look for error messages in Riven logs
2. **GitHub Issues:** Search existing issues or create a new one
3. **Discord:** Join the [Riven Discord](https://discord.gg/rivenmedia) for community support
4. **Documentation:** Review the full [Network Profiling Documentation](NETWORK_PROFILING.md)

### Information to Include

When reporting issues, please include:

- Riven version
- Operating system
- Configuration settings (redacted)
- Error messages from logs
- Steps to reproduce
- Expected vs actual behavior

### Debug Information Export

```bash
# Export current profiling data for analysis
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "http://localhost:8080/api/v1/debug/network-profiling/export/json" \
  -o debug_export.json

# Get comprehensive statistics
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "http://localhost:8080/api/v1/debug/network-profiling/advanced-stats" \
  -o advanced_stats.json
```
