# Screenshot Implementation Documentation

## Overview
This document describes the implementation of screenshot capture and display functionality in the AuroQA automation platform. Screenshots are captured during test execution and displayed in the test results UI.

## Database Structure
Screenshots are stored in the `screenshots` table with the following schema:

```sql
CREATE TABLE screenshots (
    id SERIAL PRIMARY KEY,
    test_step_id INTEGER NOT NULL REFERENCES test_steps(id) ON DELETE CASCADE,
    screenshot BYTEA NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

CREATE INDEX idx_screenshots_test_step_id ON screenshots(test_step_id);
```

## Backend Implementation

### Screenshot Capture
During test execution, screenshots are captured at key points:
- After each UI action is performed
- When errors occur
- When assertions are made

The screenshot data is stored as binary (BYTEA) in the database, linked to the corresponding test step.

### Screenshot Retrieval API
The `/api/test_step_screenshot/{step_id}` endpoint handles screenshot retrieval:

1. Verifies user permissions for the requested test step
2. Checks for file-based screenshots (legacy path-based approach)
3. If no file exists, retrieves binary data from the `screenshots` table
4. Returns either:
   - `FileResponse` with the image data (Content-Type: image/png)
   - `JSONResponse` with `{"screenshot_available": false, "message": "..."}` if no screenshot exists

## Frontend Implementation

### Screenshot Display
The TestCaseSteps component includes a modal for displaying screenshots:

1. The `handleViewScreenshot` function fetches screenshot data:
   - Makes a request to `/api/test_step_screenshot/{step_id}`
   - Checks the response content-type header
   - Handles both binary image data and JSON responses

2. For binary responses:
   - Creates a blob URL from the response data
   - Sets `currentScreenshot.imageUrl` for display

3. For JSON responses:
   - Displays error message if no screenshot is available

### UI Components
- Screenshot button in test step list
- Modal dialog for displaying screenshots
- Zoom functionality for detailed inspection
- Error handling for missing screenshots

## Usage
1. Screenshots are automatically captured during test execution
2. Users can view screenshots by clicking the screenshot icon in the test steps list
3. The screenshot modal displays the image with zoom capabilities

## Error Handling
- Missing screenshots show a user-friendly error message
- Permission errors are properly handled
- Legacy screenshots (file path) and new screenshots (database) are both supported
