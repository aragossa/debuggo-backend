#!/bin/bash

# Google OAuth environment variables
export GOOGLE_CLIENT_ID="your_client_id_here"
export GOOGLE_CLIENT_SECRET="your_client_secret_here"
export GOOGLE_REDIRECT_URI="http://localhost:9000/api/auth/google/callback"

echo "Google OAuth environment variables set!"
echo "To use these variables, run: source set_oauth_env.sh"
echo ""
echo "Then start the backend server: python3 main.py"
