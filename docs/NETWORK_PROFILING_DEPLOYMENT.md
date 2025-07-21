# Network Profiling Deployment Guide

This guide provides step-by-step instructions for deploying the network profiling feature to production environments.

## Pre-Deployment Checklist

### Code Review
- [ ] All code changes reviewed and approved
- [ ] Unit tests passing (100% coverage for core functionality)
- [ ] Integration tests passing
- [ ] Performance benchmarks completed
- [ ] Security review completed

### Environment Preparation
- [ ] Backup current configuration
- [ ] Verify system resources (CPU, memory, disk)
- [ ] Check notification system configuration
- [ ] Prepare rollback plan
- [ ] Set up monitoring and alerting

## Deployment Phases

### Phase 1: Development Environment

**Objective**: Validate functionality in development environment

**Steps**:
1. Deploy code changes to development environment
2. Enable network profiling with debug settings
3. Run comprehensive test suite
4. Validate API endpoints
5. Test alerting functionality

**Configuration**:
```json
{
  "debug": true,
  "network_profiling": {
    "enabled": true,
    "feature_flag_enabled": true,
    "slow_request_threshold": 1.0,
    "max_stored_requests": 2000,
    "log_slow_requests": true,
    "enable_alerts": false,
    "graceful_degradation": true,
    "performance_monitoring": true
  }
}
```

**Validation**:
```bash
# Test basic functionality
curl -H "Authorization: Bearer $API_KEY" \
  http://dev.example.com/api/v1/debug/network-stats

# Test profiling control
curl -X POST -H "Authorization: Bearer $API_KEY" \
  http://dev.example.com/api/v1/debug/network-profiling/enable

# Test export functionality
curl -H "Authorization: Bearer $API_KEY" \
  "http://dev.example.com/api/v1/debug/network-profiling/export/json" \
  -o test_export.json
```

**Success Criteria**:
- All API endpoints respond correctly
- Profiling data is collected and stored
- Export functionality works
- No performance degradation > 5%
- Memory usage < 10MB

### Phase 2: Staging Environment

**Objective**: Test with realistic load and data

**Steps**:
1. Deploy to staging environment
2. Configure production-like settings
3. Run load tests
4. Monitor performance impact
5. Test alerting with real notification services

**Configuration**:
```json
{
  "debug": false,
  "network_profiling": {
    "enabled": true,
    "feature_flag_enabled": true,
    "slow_request_threshold": 2.0,
    "max_stored_requests": 1000,
    "log_slow_requests": true,
    "enable_alerts": true,
    "alert_slow_request_threshold": 15.0,
    "alert_error_rate_threshold": 10.0,
    "graceful_degradation": true,
    "performance_monitoring": true,
    "max_memory_mb": 50.0
  }
}
```

**Load Testing**:
```bash
# Run load test script
python scripts/load_test.py --duration 3600 --concurrent 50

# Monitor during load test
python scripts/monitor_network_profiling.py \
  --url http://staging.example.com \
  --api-key $API_KEY \
  --continuous \
  --interval 30
```

**Success Criteria**:
- Performance overhead < 1ms per request
- Memory usage stable < 50MB
- No memory leaks detected
- Alerting system functional
- System remains stable under load

### Phase 3: Production Canary Deployment

**Objective**: Limited production deployment for validation

**Steps**:
1. Deploy to subset of production instances (10-20%)
2. Enable profiling with conservative settings
3. Monitor closely for 48 hours
4. Gradually increase coverage if stable

**Configuration**:
```json
{
  "network_profiling": {
    "enabled": false,
    "feature_flag_enabled": true,
    "slow_request_threshold": 3.0,
    "max_stored_requests": 500,
    "log_slow_requests": false,
    "enable_alerts": true,
    "alert_slow_request_threshold": 20.0,
    "alert_error_rate_threshold": 15.0,
    "graceful_degradation": true,
    "performance_monitoring": true,
    "max_memory_mb": 25.0,
    "auto_disable_on_error": true
  }
}
```

**Monitoring**:
```bash
# Set up continuous monitoring
python scripts/monitor_network_profiling.py \
  --url https://api.example.com \
  --api-key $PROD_API_KEY \
  --continuous \
  --interval 300 > monitoring.log 2>&1 &

# Set up alerting
# Configure your monitoring system to alert on:
# - Memory usage > 30MB
# - Error rate > 5%
# - Performance overhead > 2ms
# - Auto-disable events
```

**Success Criteria**:
- Zero production incidents
- Performance metrics within acceptable range
- No customer complaints
- System auto-recovery functional

### Phase 4: Full Production Rollout

**Objective**: Complete deployment to all production instances

**Steps**:
1. Deploy to all production instances
2. Enable profiling gradually (25%, 50%, 75%, 100%)
3. Monitor each step for 24 hours
4. Enable alerting after stable operation

**Final Configuration**:
```json
{
  "network_profiling": {
    "enabled": true,
    "feature_flag_enabled": true,
    "slow_request_threshold": 2.0,
    "max_stored_requests": 1000,
    "log_slow_requests": true,
    "enable_alerts": true,
    "alert_slow_request_threshold": 15.0,
    "alert_error_rate_threshold": 10.0,
    "graceful_degradation": true,
    "performance_monitoring": true,
    "max_memory_mb": 50.0,
    "auto_disable_on_error": true
  }
}
```

## Rollback Procedures

### Immediate Rollback (Emergency)

If critical issues are detected:

```bash
# Disable profiling immediately via API
curl -X POST -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/disable

# Or via feature flag
# Set feature_flag_enabled: false in configuration
```

### Gradual Rollback

For non-critical issues:

1. Reduce profiling scope (decrease max_stored_requests)
2. Disable alerting
3. Disable logging
4. Finally disable profiling entirely

### Code Rollback

If code-level issues are found:

1. Revert to previous version
2. Restart services
3. Verify system stability
4. Investigate issues in development

## Monitoring and Alerting

### Key Metrics to Monitor

**Performance Metrics**:
- Average request response time
- 95th percentile response time
- CPU usage
- Memory usage
- Error rates

**Profiling Metrics**:
- Profiling overhead (target: < 1ms)
- Memory usage (target: < 50MB)
- Consecutive errors (alert: > 3)
- Auto-disable events (alert: any)

**Business Metrics**:
- User satisfaction scores
- Service availability
- Feature adoption rates

### Alerting Configuration

```yaml
# Example alerting rules (Prometheus/AlertManager format)
groups:
  - name: network_profiling
    rules:
      - alert: NetworkProfilingHighMemory
        expr: network_profiling_memory_mb > 75
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Network profiling memory usage high"
          
      - alert: NetworkProfilingAutoDisabled
        expr: increase(network_profiling_auto_disables[5m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Network profiling auto-disabled"
          
      - alert: NetworkProfilingHighOverhead
        expr: network_profiling_overhead_ms > 2
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Network profiling overhead too high"
```

## Post-Deployment Tasks

### Week 1: Intensive Monitoring
- [ ] Daily review of metrics and logs
- [ ] Performance impact analysis
- [ ] User feedback collection
- [ ] Fine-tune thresholds if needed

### Week 2-4: Optimization
- [ ] Analyze collected data for insights
- [ ] Optimize configuration based on usage patterns
- [ ] Document lessons learned
- [ ] Plan feature enhancements

### Month 1+: Ongoing Operations
- [ ] Regular performance reviews
- [ ] Quarterly configuration reviews
- [ ] Feature usage analysis
- [ ] Capacity planning updates

## Troubleshooting Common Issues

### High Memory Usage
```bash
# Check current usage
curl -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/memory-usage

# Force cleanup if needed
curl -X POST -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/force-cleanup

# Apply retention policy
curl -X POST -H "Authorization: Bearer $API_KEY" \
  "https://api.example.com/api/v1/debug/network-profiling/retention-policy?max_age_hours=12"
```

### Performance Issues
```bash
# Check production metrics
curl -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/production-metrics

# Disable if overhead too high
curl -X POST -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/disable
```

### Error Recovery
```bash
# Reset error state
curl -X POST -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/reset-errors

# Re-enable profiling
curl -X POST -H "Authorization: Bearer $API_KEY" \
  https://api.example.com/api/v1/debug/network-profiling/enable
```

## Success Metrics

### Technical Success
- [ ] Zero production incidents caused by profiling
- [ ] Performance overhead < 1ms average
- [ ] Memory usage < 50MB stable
- [ ] 99.9% uptime maintained
- [ ] All tests passing

### Business Success
- [ ] Improved incident response time
- [ ] Better performance visibility
- [ ] Reduced MTTR for network issues
- [ ] Positive user feedback
- [ ] Cost savings from optimization

## Conclusion

The network profiling feature deployment should be approached with careful planning and gradual rollout. The feature flags and graceful degradation ensure that any issues can be quickly mitigated without affecting core functionality.

For questions or issues during deployment, refer to:
- [Troubleshooting Guide](NETWORK_PROFILING_TROUBLESHOOTING.md)
- [API Documentation](NETWORK_PROFILING_API.md)
- [Main Documentation](NETWORK_PROFILING.md)
