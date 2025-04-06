import fitz  # PyMuPDF
import os
from pathlib import Path
from gradio_client import Client
from praisonaiagents import Agent, Task, PraisonAIAgents

# ================= CONFIG =================

IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)

PROMPT_TEMPLATE = """
You are an AI research assistant specialized in creating comprehensive summaries of scientific papers.
You have been provided with:
1. The extracted text from a research paper
2. An analysis of the figures/images in the paper

Make sure the output is in two sections - Explaining content and image in correlation and detailed as well.
Your task is to create a technical yet detailed summary that:
- Captures the main research question or hypothesis
- Summarizes the methodology used
- Highlights key findings and their significance
- Incorporates relevant information from the figures/images
- Maintains technical accuracy while being accessible
- Retains most of the technical terms and explanations in brackets

Here is the combined input:
{combined_input}

Please provide a comprehensive technical summary:
"""

# ================= IMAGE ANALYSIS WITH LLAMA =================

def analyze_images_with_llama(files: list[str]) -> str:
    """Use LLaMA 3.2 Vision model via Gradio client to analyze all images."""
    client = Client("huggingface-projects/llama-3.2-vision-11B")
    response = client.predict(
        message={"text": "Analyze these scientific figures in detail and number them.", "files": files},
        max_new_tokens=250,
        api_name="/chat"
    )
    return response

# ================= EXTRACT TEXT + IMAGES =================

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

# ================= FINAL AGENT =================

doc_agent = Agent(
    name="FinalSummarizer",
    role="Document Summarization Expert",
    goal="Generate a concise and informative summary from combined image and text content",
    llm="ollama/deepseek-r1",
    backstory=PROMPT_TEMPLATE
)

# ================= PIPELINE =================

def run_summary_pipeline(pdf_path):
    text, image_files = extract_text_and_images(pdf_path)
    tasks = []

    if image_files:
        print("🔍 Sending all images to LLaMA-3.2 Vision for analysis...")
        image_analysis = analyze_images_with_llama(image_files)

        combined_input = f"""
# Extracted Text

{text}

# Image Analysis

{image_analysis}
"""
        doc_task = Task(
            name="document_summary",
            description="Generate a summary using both image analysis and extracted text.",
            expected_output="A complete technical summary of the document and figures.",
            agent=doc_agent,
            inputs={"combined_input": combined_input}
        )
    else:
        print("ℹ️ No images found in the document. Proceeding with text-only summarization.")
        doc_task = Task(
            name="document_summary_text_only",
            description=f"Summarize the following text:\n\n{text}",
            expected_output="A concise summary of the text content.",
            agent=doc_agent
        )

    tasks.append(doc_task)

    summarizer_system = PraisonAIAgents(
        agents=[doc_agent],
        tasks=tasks,
        process="sequential",
        verbose=True
    )

    results = summarizer_system.start()
    return results

# ================= RUN =================

if __name__ == "__main__":
    pdf_file = "/workspaces/ArcMCP/2307.06435v10.pdf"
    final_output = run_summary_pipeline(pdf_file)
    print("\n📄 Final Summary:\n", final_output)