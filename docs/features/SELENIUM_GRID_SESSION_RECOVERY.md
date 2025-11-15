# Selenium Grid Session Recovery

## Problem

During test generation, the system encountered session loss errors:

```
WARNING:urllib3.connectionpool:Connection pool is full, discarding connection: localhost. Connection pool size: 1
ERROR:BrowserAutomation:[PID:66760] WebDriver error getting page source: Message: Unable to find handler for (POST) /session/c16d8cf750c04621d151802de0741e96/execute/sync
```

### Root Causes

1. **Session Loss**: Selenium Grid sessions can become invalid due to:
   - Grid node crashes or restarts
   - Session timeouts
   - Network interruptions
   - Grid resource exhaustion

2. **Connection Pool Exhaustion**: urllib3 HTTP connection pool to Selenium Grid was too small (default: 1 connection)

3. **No Recovery Mechanism**: When a session was lost, the system would fail completely instead of attempting recovery

## Solution Implemented

### 1. Session Validation and Recovery Methods

Added helper methods to `BrowserAutomation` class:

```python
def _is_session_valid(self):
    """Check if the current WebDriver session is valid."""
    try:
        if not self.driver:
            return False
        # Try a simple command to check if session is alive
        self.driver.current_url
        return True
    except:
        return False

def _recover_session(self, current_url=None):
    """
    Attempt to recover a lost WebDriver session.
    
    Args:
        current_url (str, optional): URL to navigate to after recovery
        
    Returns:
        bool: True if recovery successful, False otherwise
    """
    try:
        self.logger.warning(f"[PID:{self.pid}] Attempting to recover lost session...")
        
        # Close the old driver if it exists
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        # Recreate the driver connection
        self.setup_driver(headless=True)
        
        # Navigate back to the URL if provided
        if current_url:
            self.logger.info(f"[PID:{self.pid}] Navigating back to: {current_url}")
            self.driver.get(current_url)
        
        self.logger.info(f"[PID:{self.pid}] Session recovered successfully")
        return True
    except Exception as e:
        self.logger.error(f"[PID:{self.pid}] Failed to recover session: {str(e)}")
        return False
```

### 2. Enhanced get_page_source() with Recovery

Modified `get_page_source()` to detect and recover from session loss:

```python
except WebDriverException as e:
    # Check if this is a session loss error
    error_msg = str(e)
    if "Unable to find handler" in error_msg or "invalid session id" in error_msg.lower() or "Session timed out" in error_msg:
        self.logger.warning(f"[PID:{self.pid}] Session lost during get_page_source. Error: {error_msg}")
        self.logger.warning(f"[PID:{self.pid}] Attempting to recreate session...")
        try:
            # Close the old driver if it exists
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            
            # Recreate the driver connection
            self.setup_driver(headless=True)
            
            # Retry getting page source
            self.logger.info(f"[PID:{self.pid}] Session recreated, retrying get_page_source...")
            WebDriverWait(self.driver, self.timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            return self.driver.page_source
        except Exception as retry_error:
            self.logger.error(f"[PID:{self.pid}] Failed to recover session: {str(retry_error)}")
            raise
```

### 3. Increased Connection Pool Size

Added urllib3 connection pool configuration:

```python
import urllib3
import requests.adapters

# Increase urllib3 connection pool size for Selenium Grid
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Configure connection pool manager with larger pool size
requests.adapters.DEFAULT_POOLSIZE = 50
requests.adapters.DEFAULT_POOLBLOCK = False
```

## Error Detection Patterns

The system now detects these session loss patterns:
- `"Unable to find handler"`
- `"invalid session id"` (case-insensitive)
- `"Session timed out"`

## Recovery Flow

```
1. User action triggers get_page_source()
2. WebDriver executes command
3. Session lost → WebDriverException raised
4. System detects session loss pattern
5. Log warning about session loss
6. Quit old driver (if exists)
7. Create new driver session
8. Retry the operation
9. If retry succeeds → Continue normally
10. If retry fails → Raise exception
```

## Benefits

1. **Automatic Recovery**: Tests continue running even if Grid sessions are lost
2. **Better Logging**: Clear warnings when sessions are lost and recovered
3. **Reduced Failures**: Transient Grid issues don't cause complete test failures
4. **Scalability**: Larger connection pool supports more concurrent tests
5. **User Experience**: Tests are more reliable and resilient

## Monitoring

### Check Selenium Grid Status

```bash
curl -s http://localhost:4444/status | python3 -m json.tool
```

### Check Active Sessions

Look for `"session"` objects in the Grid status output to see active session IDs.

### Log Patterns to Watch

**Session Loss**:
```
WARNING: Session lost during get_page_source. Error: Unable to find handler...
WARNING: Attempting to recreate session...
INFO: Session recreated, retrying get_page_source...
```

**Connection Pool Warning**:
```
WARNING:urllib3.connectionpool:Connection pool is full, discarding connection: localhost
```

**Recovery Success**:
```
INFO: Session recovered successfully
```

**Recovery Failure**:
```
ERROR: Failed to recover session: [error details]
```

## Configuration

### Selenium Grid

Grid is running with 4 Chrome nodes, 4 slots each (16 total):
```bash
docker-compose up -d
```

### Connection Pool

Default pool size increased from 1 to 50:
```python
requests.adapters.DEFAULT_POOLSIZE = 50
requests.adapters.DEFAULT_POOLBLOCK = False
```

## Troubleshooting

### Issue: Sessions Still Timing Out

**Solution**: Increase Grid session timeout in docker-compose.yml:
```yaml
environment:
  - SE_SESSION_REQUEST_TIMEOUT=300
  - SE_SESSION_TIMEOUT=300
```

### Issue: Connection Pool Still Full

**Solution**: Increase pool size further:
```python
requests.adapters.DEFAULT_POOLSIZE = 100
```

### Issue: Grid Nodes Crashing

**Solution**: 
1. Check Docker resources (CPU, memory)
2. Reduce concurrent test execution
3. Check Grid logs: `docker-compose logs selenium-hub`

### Issue: Recovery Fails Repeatedly

**Solution**:
1. Restart Selenium Grid: `docker-compose restart`
2. Check Grid health: `curl http://localhost:4444/status`
3. Verify network connectivity
4. Check system resources

## Best Practices

1. **Monitor Grid Health**: Regularly check Grid status endpoint
2. **Limit Concurrency**: Don't exceed Grid capacity (16 slots)
3. **Clean Up Sessions**: Ensure `driver.quit()` is called in finally blocks
4. **Use Timeouts**: Set reasonable timeouts for operations
5. **Log Everything**: Enable detailed logging for debugging

## Files Modified

- `/auroqa/Utils/BrowserAutomation/BrowserAutomation.py`:
  - Added `_is_session_valid()` method
  - Added `_recover_session()` method
  - Enhanced `get_page_source()` with recovery logic
  - Increased urllib3 connection pool size

## Future Improvements

1. **Retry Decorator**: Create a decorator for automatic retry on session loss
2. **Health Checks**: Periodic session validation before operations
3. **Circuit Breaker**: Temporarily stop using Grid if too many failures
4. **Metrics**: Track session loss rate and recovery success rate
5. **Alerting**: Notify admins when Grid health degrades

## Summary

**Problem**: Session loss errors causing test failures
**Solution**: Automatic session recovery with increased connection pool
**Impact**: More reliable test execution with better resilience to Grid issues
**Status**: ✅ Implemented and ready for testing
