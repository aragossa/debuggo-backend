# Google OAuth Setup Guide for AuroQA

This guide will walk you through the process of setting up Google OAuth credentials for your AuroQA application.

## Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top of the page
3. Click on "New Project"
4. Enter a project name (e.g., "AuroQA")
5. Click "Create"

## Step 2: Enable the Google OAuth API

1. In your new project, go to "APIs & Services" > "Library" from the navigation menu
2. Search for "Google OAuth API" or "Google Identity"
3. Click on "Google Identity Services" or "OAuth 2.0 API"
4. Click "Enable"

## Step 3: Configure the OAuth Consent Screen

1. Go to "APIs & Services" > "OAuth consent screen" from the navigation menu
2. Select "External" as the user type (unless you have a Google Workspace account)
3. Click "Create"
4. Fill in the required information:
   - App name: "AuroQA"
   - User support email: Your email address
   - Developer contact information: Your email address
5. Click "Save and Continue"
6. On the "Scopes" page, click "Add or Remove Scopes"
7. Add the following scopes:
   - `https://www.googleapis.com/auth/userinfo.email`
   - `https://www.googleapis.com/auth/userinfo.profile`
   - `openid`
8. Click "Save and Continue"
9. Add any test users if needed (your email address)
10. Click "Save and Continue"
11. Review your settings and click "Back to Dashboard"

## Step 4: Create OAuth Client ID

1. Go to "APIs & Services" > "Credentials" from the navigation menu
2. Click "Create Credentials" and select "OAuth client ID"
3. Select "Web application" as the application type
4. Name: "AuroQA Web Client"
5. Add authorized JavaScript origins:
   - `http://localhost:3000` (for development)
   - Your production URL if available
6. Add authorized redirect URIs:
   - `http://localhost:9000/api/auth/google/callback` (for development)
   - Your production callback URL if available
7. Click "Create"
8. A popup will display your client ID and client secret. Save these values securely.

## Step 5: Configure Environment Variables

Add the following environment variables to your AuroQA backend:

```
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:9000/api/auth/google/callback
```

For production, update the redirect URI to your production URL.

## Step 6: Verify Configuration

1. Start your AuroQA backend
2. Navigate to `/api/login/google` in your browser
3. You should be redirected to Google's login page
4. After logging in, you should be redirected back to your application with a valid token

## Troubleshooting

- **Error: redirect_uri_mismatch**: Ensure the redirect URI in your Google Cloud Console matches exactly with the one in your environment variables
- **Error: invalid_client**: Double-check your client ID and client secret
- **Error: access_denied**: Ensure you've enabled the necessary scopes in the OAuth consent screen
