# ArcMCP PDF Analysis Backend

A comprehensive system for PDF document processing, analysis, and text-based interaction with document content using Ollama local models and Pinecone vector database.

## Overview

This backend service provides several key functionalities:

1. PDF text and image extraction
2. Image analysis using Gemma multimodal model via Ollama
3. Document summarization using DeepSeek model via Ollama
4. Pinecone vector database integration for semantic search and chat capabilities
5. File deduplication using hash-based tracking
6. Notebook state persistence using Redis

## Architecture

The system consists of several key components:

- **Flask API Server**: Main entry point for all requests
- **PDF Processing Module**: Extracts text and images from PDFs
- **Image Analysis Pipeline**: Uses Gemma multimodal model to analyze figures
- **Text Summarization**: Uses DeepSeek to create comprehensive document summaries
- **Pinecone Integration**: Provides semantic search and chat capabilities with uploaded documents
- **Redis Cache**: Stores state and handles file deduplication

## Prerequisites

- Python 3.8+
- Redis
- Ollama (with DeepSeek-r1:1.5b model)
- Pinecone API Key

## Installation

### Quick Setup (Automated Installation)

For a quick setup, you can use our installation script which will handle all dependencies and configuration:

```bash
# Download the setup script
git clone https://github.com/AyushTripathi07/ArcMCP.git

# Change Directory
cd ArcMCP

# Make it executable
chmod +x setup.sh

# Run the setup script
./setup.sh
```

The script will:
1. Install required Python packages
2. Create necessary directories
3. Install Ollama and pull the DeepSeek model
4. Set up Redis using Docker
5. Prompt for your Pinecone API key and create a .env file

Here's the complete setup script for reference:

```bash
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

```

### Manual Installation

If you prefer to install components manually:

#### 1. Clone the repository and set up environment

```bash
git clone https://github.com/AyushTripathi07/ArcMCP.git
cd arcmcp-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Install Ollama and required models

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull required model
ollama pull deepseek-r1:1.5b
```

#### 3. Set up Redis

Using Docker:
```bash
docker pull redis
docker run -d --name redis-server -p 6379:6379 redis
```

Or install Redis directly:
```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
```

#### 4. Environment Configuration

Create a `.env` file with the following variables:
```
PINECONE_API_KEY=your_pinecone_api_key
```

## API Endpoints

### PDF Processing

#### `POST /process-pdf`
Processes a PDF file, extracting text, analyzing images, and generating a summary.

**Request:**
- Form data with `file` field containing the PDF

**Response:**
- SSE stream with real-time updates on processing status

#### `POST /upload-to-pinecone`
Uploads a PDF file to Pinecone for semantic search and chat capabilities.

**Request:**
- Form data with:
  - `file`: The PDF file
  - `assistant_name` (optional): Custom name for the assistant

**Response:**
```json
{
  "success": true,
  "message": "File uploaded and indexed successfully",
  "file_id": "file_id",
  "duplicate": false
}
```

### Chat and Search

#### `POST /chat-with-pdf`
Interacts with uploaded PDFs using natural language.

**Request:**
```json
{
  "assistant_name": "pdf-chat-assistant",
  "message": "What is the main finding in this paper?",
  "chat_history": []
}
```

**Response:**
```json
{
  "success": true,
  "response": "The main finding is...",
  "message": {
    "role": "assistant",
    "content": "The main finding is..."
  },
  "citations": [...]
}
```

### File Management

#### `GET /list-assistant-files`
Lists all files uploaded to a specific assistant.

**Request:**
- Query param: `assistant_name` (optional)

**Response:**
```json
{
  "success": true,
  "files": [...]
}
```

#### `DELETE /delete-assistant-file`
Deletes a file from an assistant.

**Request:**
```json
{
  "assistant_name": "pdf-chat-assistant",
  "file_id": "file_id"
}
```

**Response:**
```json
{
  "success": true,
  "message": "File file_id deleted successfully"
}
```

#### `DELETE /delete-assistant`
Deletes an entire assistant and its files.

**Request:**
```json
{
  "assistant_name": "pdf-chat-assistant"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Assistant 'pdf-chat-assistant' deleted successfully"
}
```

### State Management

#### `POST /save-state`
Saves notebook state to Redis.

**Request:**
```json
{
  "notebookId": "unique-notebook-id",
  "data": {}
}
```

**Response:**
```json
{
  "success": true,
  "message": "Saved state for notebook ID 'unique-notebook-id'"
}
```

#### `POST /get-state`
Retrieves notebook state from Redis.

**Request:**
```json
{
  "notebookId": "unique-notebook-id"
}
```

**Response:**
```json
{
  "success": true,
  "data": {}
}
```

### Health Check

#### `GET /health`
Simple health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "message": "PDF processing service is running"
}
```

## Technical Details

### PDF Processing Pipeline

1. **Text Extraction**: Uses PyMuPDF to extract all text content from the PDF
2. **Image Extraction**: Extracts all images from the PDF
3. **Image Analysis**: Uses Gemma multimodal model to analyze extracted figures
4. **Document Summarization**: Combines text and image analysis to generate a comprehensive summary using DeepSeek

### File Deduplication

The system uses MD5 hashing to identify and prevent duplicate file uploads:

1. When a file is uploaded, its MD5 hash is calculated
2. If the hash exists in Redis, the existing file ID is returned
3. Otherwise, the file is uploaded and its hash is stored

### Streaming Updates

The `/process-pdf` endpoint uses Server-Sent Events (SSE) to provide real-time updates during processing, including:

- Status messages
- Progress updates
- Error notifications
- Intermediate results
- Final summary

## Development and Extension

### Adding New Models

To add support for new models in the image analysis or summarization pipeline:

1. Update the corresponding template in `utils.py`
2. Modify the relevant processing functions
3. Pull the new model with Ollama: `ollama pull model_name`

### Customizing Prompts

The system uses two main prompts defined in `utils.py`:

- `GEMMA_PROMPT_TEMPLATE`: Controls image analysis behavior
- `DEEPSEEK_PROMPT_TEMPLATE`: Controls document summarization

Modify these templates to adjust the system's analysis style and output format.

### Running in Development Mode

To start the Flask server in development mode:

```bash
export FLASK_APP=app.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5000
```

For production deployment, consider using Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Troubleshooting

### Common Issues

1. **Redis Connection Error**
   - Ensure Redis is running on localhost:6379
   - Check Redis connection string in the code

2. **PDF Processing Fails**
   - Verify the PDF is not corrupt or password-protected
   - Check available disk space for image extraction

3. **Ollama Model Issues**
   - Ensure Ollama service is running: `systemctl status ollama`
   - Verify model is downloaded: `ollama list`
   - Try pulling the model again: `ollama pull deepseek-r1:1.5b`

4. **Pinecone API Issues**
   - Verify API key is correct in .env file
   - Check Pinecone service status
   - Ensure your Pinecone plan allows the operations you're attempting

## License

[MIT License](LICENSE)

## Acknowledgments

- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) for PDF processing
- [Ollama](https://ollama.ai/) for local model inferencing
- [Pinecone](https://www.pinecone.io/) for vector database capabilities
- [Flask](https://flask.palletsprojects.com/) for API server