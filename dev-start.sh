#!/bin/bash
# Development startup script - runs Flask backend and React frontend concurrently

echo "🚀 Starting ECE461 Phase 2 Development Environment"
echo "=================================================="
echo ""

# Check if in venv
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: Not in a virtual environment. Activate venv first:"
    echo "   source venv/bin/activate"
    echo ""
fi

# Start Flask backend in background
echo "📦 Starting Flask backend on http://localhost:5000..."
cd "$(dirname "$0")"
python3 -m app.app &
FLASK_PID=$!
echo "   Flask PID: $FLASK_PID"

# Wait a moment for Flask to start
sleep 2

# Start React frontend
echo ""
echo "⚛️  Starting React frontend on http://localhost:5173..."
cd app/react-app
npm run dev &
VITE_PID=$!
echo "   Vite PID: $VITE_PID"

echo ""
echo "✅ Development servers started!"
echo "=================================================="
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop both servers"
echo "=================================================="

# Function to kill both processes on script termination
cleanup() {
    echo ""
    echo "🛑 Stopping servers..."
    kill $FLASK_PID 2>/dev/null
    kill $VITE_PID 2>/dev/null
    echo "✅ Servers stopped"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup INT TERM

# Wait for both processes
wait
