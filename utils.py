# utils.py
import os
import time
import queue
import threading
import json
import requests
from pathlib import Path
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
from gradio_client import Client, handle_file

# ================= CONFIG =================

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)

GEMMA_PROMPT_TEMPLATE = """
You are a vision-language model designed to analyze and summarize figures from scientific documents.

You will be given one or more images (figures) extracted from a PDF. Your task is to analyze each figure carefully and generate a structured report in the following format:

## Image Analysis Report

**Figure 1**:
- Visual Description: [What is visually depicted?]
- Methodology (if inferred): [Any process or setup shown?]
- Inferred Insight: [What can be interpreted or concluded from the figure?]

**Figure 2**:
...

Focus on clarity, relevance, and scientific interpretation. Avoid guessing without evidence in the image.

Start your response with `## Image Analysis Report`.
"""

DEEPSEEK_PROMPT_TEMPLATE = """
You are an AI research assistant specialized in analyzing and summarizing scientific documents.

You are provided with:
1. Extracted text from a scientific PDF.
2. A detailed image analysis report summarizing the figures.

Your task is to write a comprehensive and coherent summary of the document that:

- Identifies the core research question or hypothesis
- Summarizes the methodology and experiment(s) conducted
- Describes the findings and outcomes in technical terms
- Integrates figure insights from the image analysis into the text appropriately (i.e., correlate visual results with related textual descriptions)
- Maintains technical terminology, using layman-friendly phrases only where necessary
- Avoids repeating the image analysis but *uses* it to reinforce or clarify textual content

**Your output should be structured and complete.**
Avoid generalizations, and prefer technical accuracy.
"""

# ================= PDF TEXT + IMAGE EXTRACTION =================

def extract_text_and_images(pdf_path):
    doc = fitz.open(pdf_path)
    text_content = ""
    image_paths = []

    for i, page in enumerate(doc):
        text_content += page.get_text()
        image_list = page.get_images(full=True)

        for j, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            img_ext = base_image["ext"]
            img_path = IMAGES_DIR / f"page_{i+1}_img_{j+1}.{img_ext}"

            with open(img_path, "wb") as f:
                f.write(image_bytes)
            image_paths.append(str(img_path))

    return text_content, image_paths

# ================= GEMMA ANALYSIS =================

def analyze_images_with_gemma(image_files: list[str]) -> str:
    client = Client("prithivMLmods/Gemma-3-Multimodal")
    #client = Client("prithivMLmods/Gemma-3-Multimodal") hf token

    print("🔍 Sending all images to Gemma-3-Multimodal...")
    uploaded_files = [handle_file(img_path) for img_path in image_files]

    try:
        result = client.predict(
            message={
                "text": GEMMA_PROMPT_TEMPLATE,
                "files": uploaded_files
            },
            param_2=1024,
            param_3=0.6,
            param_4=0.9,
            param_5=50,
            param_6=1.2,
            api_name="/chat"
        )
        print("✅ Image analysis completed.")
        return result
    except Exception as e:
        print("❌ Gemma image analysis failed:", e)
        return "Image analysis failed due to an error."

# ================= GENERAL HELPERS =================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ================= STREAMING MANAGER =================

class StreamingManager:
    def __init__(self):
        self.message_queue = queue.Queue()
        self.running = True
        self.start_time = None

    def get_elapsed_seconds(self):
        if self.start_time is None:
            return 0
        return int(time.time() - self.start_time)

    def add_message(self, message_type, content):
        self.message_queue.put({
            "type": message_type,
            "content": content,
            "elapsed_seconds": self.get_elapsed_seconds()
        })

    def process_pdf(self, pdf_path):
        try:
            self.start_time = time.time()
            self.add_message("status", "Extracting text and images from PDF...")
            text, image_files = extract_text_and_images(pdf_path)
            self.add_message("status", f"Extracted {len(image_files)} images from the PDF")

            if image_files:
                self.add_message("status", f"Starting image analysis for {len(image_files)} images...")
                image_analysis_thread = threading.Thread(target=self.run_image_analysis, args=(image_files,))
                image_analysis_thread.start()
                while image_analysis_thread.is_alive():
                    self.add_message("progress", f"Processing images... ({self.get_elapsed_seconds()} seconds)")
                    time.sleep(2)
                image_analysis_thread.join()
                image_analysis = getattr(self, 'image_analysis_result', "Image analysis failed")
                self.add_message("image_analysis", image_analysis)
                combined_input = f"""
                    # Extracted Text

                    {text}

                    # Image Analysis

                    {image_analysis}
                """
                prompt = f"""
                {DEEPSEEK_PROMPT_TEMPLATE}

                You are given text and image analysis from a scientific document.

                {combined_input}

                Generate a summary using both image analysis and extracted text.
                """
            else:
                self.add_message("status", "No images found. Proceeding with text-only summarization.")
                prompt = f"""
                {DEEPSEEK_PROMPT_TEMPLATE}

                Summarize the following text:

                {text}
                """
            self.add_message("status", "Starting final summarization process...")
            summarization_thread = threading.Thread(target=self.call_ollama_directly, args=(prompt,))
            summarization_thread.start()
            while summarization_thread.is_alive():
                self.add_message("progress", f"Generating final summary... ({self.get_elapsed_seconds()} seconds)")
                time.sleep(3)
            summarization_thread.join()
            final_result = getattr(self, 'summarization_result', "Summarization failed")
            self.add_message("final_summary", final_result)
            self.add_message("complete", f"Process completed in {self.get_elapsed_seconds()} seconds")
        except Exception as e:
            self.add_message("error", f"Error in processing: {str(e)}")
        finally:
            self.running = False

    def run_image_analysis(self, image_files):
        try:
            result = analyze_images_with_gemma(image_files)
            self.image_analysis_result = result
        except Exception as e:
            self.image_analysis_result = f"Image analysis failed: {str(e)}"

    def call_ollama_directly(self, prompt):
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "deepseek-r1", "prompt": prompt, "stream": False}
            )
            if response.status_code == 200:
                self.summarization_result = response.json().get("response", "")
            else:
                self.summarization_result = f"API call failed with status code: {response.status_code}"
        except Exception as e:
            self.summarization_result = f"Summarization failed: {str(e)}"
