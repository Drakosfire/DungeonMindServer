#!/bin/bash
# Runner script for OpenAI image generation comparison tests

set -e

echo "🚀 Starting OpenAI Image Generation Model Comparison"
echo "   Comparing: gpt-image-1 vs gpt-image-1-mini"
echo ""

# Check if we're in the right directory
if [ ! -f "test_image_generation_comparison.py" ]; then
    echo "❌ Error: Must be run from DungeonMindServer/tests/ directory"
    exit 1
fi

# Check for required environment variables
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY environment variable not set"
    exit 1
fi

echo "✅ Environment variables verified"
echo ""

# Install dependencies if needed
echo "📦 Checking dependencies..."
pip install -q openai httpx pillow

echo ""
echo "🎨 Running OpenAI model comparison tests..."
echo ""

# Run the test script
python test_image_generation_comparison.py

echo ""
echo "✅ Tests complete! Check the output directory for results."
