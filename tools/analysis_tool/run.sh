#!/bin/bash

# CapEx Intelligence Analysis Tool - Quick Start Script

echo "================================================"
echo "  CapEx Intelligence Analysis Tool"
echo "================================================"
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama not found. Please install it first:"
    echo "   brew install ollama"
    echo "   Or download from https://ollama.ai"
    exit 1
fi

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "🔄 Starting Ollama server..."
    ollama serve &
    sleep 3
fi

# Check if llama3.1 is available
if ! ollama list | grep -q "llama3.1"; then
    echo "📥 Downloading llama3.1 model (this may take a while)..."
    ollama pull llama3.1
fi

echo "✅ Ollama is ready"
echo ""

# Check Python dependencies
echo "🔍 Checking Python dependencies..."
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

echo ""
echo "🚀 Starting the Analysis Tool..."
echo "   Dashboard will open at: http://localhost:8501"
echo ""
echo "   Press Ctrl+C to stop"
echo ""

# Run Streamlit
streamlit run app.py
