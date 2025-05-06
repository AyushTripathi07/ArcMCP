#!/bin/bash

echo "🔧 Starting ArcMCP environment setup..."

# === 1. Install or Upgrade Python Dependencies ===
echo "📦 Installing required Python packages..."
pip install --upgrade \
    flask flask-cors pymupdf gradio gradio-client redis \
    pinecone pinecone-plugin-assistant

# === 2. Install Ollama ===
echo "🤖 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

# === 3. Pull DeepSeek model ===
echo "📥 Pulling DeepSeek R1 model..."
ollama pull deepseek-r1:1.5b

# === 4. Install ngrok ===
echo "🌐 Installing ngrok..."
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null

echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list

sudo apt update && sudo apt install -y ngrok

# === 5. Prompt for ngrok auth token ===
echo ""
read -p "🔐 Enter your ngrok authtoken: " NGROK_TOKEN
ngrok config add-authtoken "$NGROK_TOKEN"
echo "✅ Ngrok authtoken configured."

# === 6. Install and run Redis using Docker ===
echo "🐳 Pulling Redis Docker image..."
docker pull redis

echo "🚀 Starting Redis container on port 6379..."
docker run -d --name redis-server -p 6379:6379 redis

echo ""
echo "✅ ArcMCP environment setup complete!"
