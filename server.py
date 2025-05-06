from flask import Flask, request, Response, jsonify
import os
import threading
import json
import time
import hashlib
from flask_cors import CORS
from utils import StreamingManager, allowed_file, UPLOAD_FOLDER
import redis
from pinecone import Pinecone
from pinecone_plugins.assistant.models.chat import Message
import tempfile
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)

# Initialize Pinecone client
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
pc = Pinecone(api_key=PINECONE_API_KEY)

# Default assistant name
DEFAULT_ASSISTANT_NAME = "pdf-chat-assistant"

# Redis key prefix for tracking uploaded files
FILE_HASH_PREFIX = "pinecone:file:hash:"

def get_file_hash(file_path):
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def is_file_uploaded(file_hash, assistant_name=DEFAULT_ASSISTANT_NAME):
    """Check if file with this hash is already uploaded to the assistant"""
    redis_key = f"{FILE_HASH_PREFIX}{assistant_name}:{file_hash}"
    return redis_client.exists(redis_key)

def mark_file_as_uploaded(file_hash, file_id, assistant_name=DEFAULT_ASSISTANT_NAME):
    """Mark a file as uploaded by storing its hash in Redis"""
    redis_key = f"{FILE_HASH_PREFIX}{assistant_name}:{file_hash}"
    redis_client.set(redis_key, file_id)

def get_uploaded_file_id(file_hash, assistant_name=DEFAULT_ASSISTANT_NAME):
    """Get the Pinecone file ID for an already uploaded file"""
    redis_key = f"{FILE_HASH_PREFIX}{assistant_name}:{file_hash}"
    file_id = redis_client.get(redis_key)
    if file_id:
        return file_id.decode('utf-8')
    return None

def get_or_create_assistant(assistant_name=DEFAULT_ASSISTANT_NAME):
    """Get existing assistant or create a new one if it doesn't exist"""
    try:
        assistant = pc.assistant.Assistant(assistant_name=assistant_name)
        return assistant
    except Exception:
        # Create new assistant
        pc.assistant.create_assistant(
            assistant_name=assistant_name,
            instructions="Use uploaded documents to answer questions about PDFs. Be clear and concise.",
            region="us"
        )
        return pc.assistant.Assistant(assistant_name=assistant_name)

@app.route('/process-pdf', methods=['POST'])
def process_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        from werkzeug.utils import secure_filename  # Imported here for clarity
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Check if this file has already been uploaded to Pinecone
        assistant_name = request.form.get('assistant_name', DEFAULT_ASSISTANT_NAME)
        file_hash = get_file_hash(file_path)
        pinecone_file_id = None
        
        try:
            # Get or create assistant
            assistant = get_or_create_assistant(assistant_name)
            
            # Check if file is already uploaded
            if is_file_uploaded(file_hash, assistant_name):
                # File already exists, get its ID
                pinecone_file_id = get_uploaded_file_id(file_hash, assistant_name)
                print(f"File already uploaded (ID: {pinecone_file_id}), skipping re-upload to Pinecone")
            else:
                # File not yet uploaded, upload to Pinecone assistant
                pinecone_response = assistant.upload_file(
                    file_path=file_path,
                    metadata={"source": filename}
                )
                
                # Store file hash and ID in Redis
                pinecone_file_id = pinecone_response.get("id", "unknown")
                mark_file_as_uploaded(file_hash, pinecone_file_id, assistant_name)
                print(f"File uploaded to Pinecone with ID: {pinecone_file_id}")
                
        except Exception as e:
            # Log the error but continue with normal processing
            print(f"Error with Pinecone: {str(e)}")

        # Continue with the normal processing
        manager = StreamingManager()
        processing_thread = threading.Thread(target=manager.process_pdf, args=(file_path,))
        processing_thread.daemon = True
        processing_thread.start()

        def generate():
            # # First yield a message about Pinecone status if available
            # if pinecone_file_id:
            #     if is_file_uploaded(file_hash, assistant_name):
            #         yield f"data: {json.dumps({'type': 'info', 'content': f'File already exists in Pinecone (ID: {pinecone_file_id})'})}\n\n"
            #     else:
            #         yield f"data: {json.dumps({'type': 'info', 'content': f'File uploaded to Pinecone (ID: {pinecone_file_id})'})}\n\n"
                
            while manager.running or not manager.message_queue.empty():
                try:
                    if not manager.message_queue.empty():
                        message = manager.message_queue.get()
                        yield f"data: {json.dumps(message)}\n\n"
                    else:
                        time.sleep(0.1)
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                    break

        return Response(generate(), mimetype='text/event-stream')

    return jsonify({"error": "File type not allowed"}), 400

@app.route('/upload-to-pinecone', methods=['POST'])
def upload_to_pinecone():
    """Endpoint to upload a PDF file to Pinecone assistant"""
    try:
        # Get assistant name from request or use default
        assistant_name = request.form.get('assistant_name', DEFAULT_ASSISTANT_NAME)
        
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file part"}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No selected file"}), 400
            
        if file and allowed_file(file.filename):
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name
            
            # Get or create assistant
            assistant = get_or_create_assistant(assistant_name)
            
            # Calculate file hash
            file_hash = get_file_hash(tmp_path)
            
            # Check if file already exists
            if is_file_uploaded(file_hash, assistant_name):
                # Get existing file ID
                file_id = get_uploaded_file_id(file_hash, assistant_name)
                
                # Clean up temp file
                os.unlink(tmp_path)
                
                return jsonify({
                    "success": True, 
                    "message": "File already exists in Pinecone, skipped re-upload",
                    "file_id": file_id,
                    "duplicate": True
                }), 200
            
            # File doesn't exist, upload it
            response = assistant.upload_file(
                file_path=tmp_path,
                metadata={"source": file.filename}
            )
            
            # Store file hash in Redis
            file_id = response.get("id", "unknown")
            mark_file_as_uploaded(file_hash, file_id, assistant_name)
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            return jsonify({
                "success": True, 
                "message": "File uploaded and indexed successfully",
                "file_id": file_id,
                "duplicate": False
            }), 200
        
        return jsonify({"success": False, "error": "File type not allowed"}), 400
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/chat-with-pdf', methods=['POST'])
def chat_with_pdf():
    """Endpoint to chat with the PDF documents via Pinecone assistant"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON payload received"}), 400
            
        # Get assistant name or use default
        assistant_name = data.get('assistant_name', DEFAULT_ASSISTANT_NAME)
        
        # Get message content
        message_content = data.get('message')
        if not message_content:
            return jsonify({"success": False, "error": "No message content provided"}), 400
            
        # Get chat history if provided
        chat_history = data.get('chat_history', [])
        
        # Get or create assistant
        assistant = get_or_create_assistant(assistant_name)
        
        # Create message object
        msg = Message(role="user", content=message_content)
        
        # Get response from assistant
        response = assistant.chat(messages=chat_history + [msg])
        
        # Extract response data
        result = {
            "success": True,
            "response": response.message.content,
            "message": {
                "role": response.message.role,
                "content": response.message.content
            },
        }
        
        # Add citations if available
        if hasattr(response, "citations") and response.citations:
            result["citations"] = response.citations
            
        return jsonify(result), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/list-assistant-files', methods=['GET'])
def list_assistant_files():
    """Endpoint to list files uploaded to an assistant"""
    try:
        # Get assistant name from query params or use default
        assistant_name = request.args.get('assistant_name', DEFAULT_ASSISTANT_NAME)
        
        # Get assistant
        assistant = get_or_create_assistant(assistant_name)
        
        # List files
        files = assistant.list_files()
        
        return jsonify({
            "success": True,
            "files": files
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/delete-assistant-file', methods=['DELETE'])
def delete_assistant_file():
    """Endpoint to delete a file from an assistant"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON payload received"}), 400
            
        # Get assistant name and file id
        assistant_name = data.get('assistant_name', DEFAULT_ASSISTANT_NAME)
        file_id = data.get('file_id')
        
        if not file_id:
            return jsonify({"success": False, "error": "No file ID provided"}), 400
            
        # Get assistant
        assistant = get_or_create_assistant(assistant_name)
        
        # Delete file from Pinecone
        assistant.delete_file(file_id=file_id)
        
        # Also remove file hash from Redis (find and delete by file ID)
        pattern = f"{FILE_HASH_PREFIX}{assistant_name}:*"
        for key in redis_client.scan_iter(match=pattern):
            if redis_client.get(key).decode('utf-8') == file_id:
                redis_client.delete(key)
                break
        
        return jsonify({
            "success": True,
            "message": f"File {file_id} deleted successfully"
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/delete-assistant', methods=['DELETE'])
def delete_assistant():
    """Endpoint to delete an assistant"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON payload received"}), 400
            
        # Get assistant name
        assistant_name = data.get('assistant_name', DEFAULT_ASSISTANT_NAME)
            
        # Delete assistant
        pc.assistant.delete_assistant(assistant_name=assistant_name)
        
        # Clean up Redis entries for this assistant
        pattern = f"{FILE_HASH_PREFIX}{assistant_name}:*"
        for key in redis_client.scan_iter(match=pattern):
            redis_client.delete(key)
        
        return jsonify({
            "success": True,
            "message": f"Assistant '{assistant_name}' deleted successfully"
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "PDF processing service is running"}), 200

@app.route('/save-state', methods=['POST'])
def save_state():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No JSON payload received"}), 400

        # Extract notebookId
        notebook_id = data.get("notebookId")
        if not notebook_id:
            return jsonify({"success": False, "error": "Missing notebookId in payload"}), 400

        # Save to Redis using notebookId as the key
        redis_client.set(notebook_id, json.dumps(data, ensure_ascii=False))

        return jsonify({"success": True, "message": f"Saved state for notebook ID '{notebook_id}'"}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/get-state', methods=['POST'])
def get_state_post():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No JSON payload received"}), 400

        notebook_id = data.get("notebookId")
        if not notebook_id:
            return jsonify({"success": False, "error": "Missing notebookId in payload"}), 400

        saved_data = redis_client.get(notebook_id)

        if not saved_data:
            return jsonify({"success": False, "error": f"No state found for notebook ID '{notebook_id}'"}), 404

        state = json.loads(saved_data)

        return jsonify({"success": True, "data": state}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, threaded=True, host='0.0.0.0', port=5000)