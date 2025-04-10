# server.py
from flask import Flask, request, Response, jsonify
import os
import threading
import json
import time
from flask_cors import CORS
from utils import StreamingManager, allowed_file, UPLOAD_FOLDER

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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

        manager = StreamingManager()
        processing_thread = threading.Thread(target=manager.process_pdf, args=(file_path,))
        processing_thread.daemon = True
        processing_thread.start()

        def generate():
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

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "PDF processing service is running"}), 200

if __name__ == '__main__':
    app.run(debug=True, threaded=True, host='0.0.0.0', port=5000)
