# Selenium Grid Integration for Debuggo

This document explains how Debuggo now uses Selenium Grid with containerized browsers for test automation.

## Overview

Instead of running Selenium browser instances directly within the application, Debuggo now uses Selenium Grid in Docker containers. This approach provides several benefits:

- **Isolation**: Browser tests run in isolated containers
- **Scalability**: Multiple browser instances can run in parallel
- **Cross-browser testing**: Easily switch between Chrome and Firefox
- **Resource management**: Better control over resource allocation

## Architecture

The system consists of:

1. **Selenium Hub**: Central manager for test distribution
2. **Browser Nodes**: Container instances of Chrome and Firefox
3. **GridManager**: Ensures the Selenium Grid is running before tests execute
4. **BrowserAutomation**: Modified to connect to remote Selenium Grid

## Setup and Usage

### Prerequisites

- Docker and Docker Compose installed on the host system

### Starting the Grid

The system will automatically start the Selenium Grid when needed, but you can also manually control it:

```bash
# Start the grid
cd /Users/aragossa/dzrprj/auroqa
docker-compose up -d

# Check status
docker-compose ps

# Stop the grid
docker-compose down
```

### Running Tests with Different Browsers

When running a test case, you can now specify the browser type:

```json
POST /api/run_test_case/{id}
{
  "environment_id": 1,
  "browser_type": "chrome"  // or "firefox"
}
```

If no browser type is specified, Chrome will be used by default.

## Implementation Details

### Docker Compose Configuration

The `docker-compose.yml` file defines:
- Selenium Hub on port 4444
- Chrome node with VNC on port 5900
- Firefox node with VNC on port 5901

### Code Changes

1. **BrowserAutomation.py**: Modified to connect to Selenium Grid instead of launching local browsers
2. **TestRunner.py**: Updated to ensure Grid is running and support browser type selection
3. **GridManager.py**: New class to manage the Selenium Grid containers
4. **main.py**: Updated API endpoint to accept browser type parameter

## Troubleshooting

If you encounter issues with the Selenium Grid:

1. Check if containers are running: `docker-compose ps`
2. View container logs: `docker-compose logs selenium-hub`
3. Restart the grid: `docker-compose restart`
4. Check network connectivity between application and Selenium Hub

## Viewing Test Execution

You can view test execution in real-time using VNC:
- Chrome: VNC to localhost:5900
- Firefox: VNC to localhost:5901

Password: `secret`

## Future Improvements

- Add more browser types (Edge, Safari)
- Implement dynamic scaling of browser nodes
- Add browser version selection
- Integrate with cloud-based Selenium Grid providers
