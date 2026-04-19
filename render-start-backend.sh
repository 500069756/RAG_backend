#!/bin/bash
# Render Start Script - Backend

echo "🚀 Starting WealthWise Backend (Waitress on port ${PORT:-5000})..."
cd backend || exit 1

# Verify GROQ_API_KEY is set
if [ -z "$GROQ_API_KEY" ]; then
    echo "❌ ERROR: GROQ_API_KEY environment variable is not set"
    echo "Set it in Render Dashboard → Environment Variables"
    exit 1
fi

echo "✅ GROQ_API_KEY is configured"
echo "🔧 Environment: $FLASK_ENV"
echo "📡 Port: ${PORT:-5000}"

# Start Flask app with Gunicorn
gunicorn --workers 4 --worker-class sync --timeout 120 --bind 0.0.0.0:${PORT:-5000} app:app
