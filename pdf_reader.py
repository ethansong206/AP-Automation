import pdfplumber
import logging

def extract_text_data_from_pdfs(pdf_paths):
    all_documents = []

    for pdf_path in pdf_paths:
        document_words = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
                    for word in words:
                        word_info = {
                            "text": word["text"],
                            "x0": float(word["x0"]),
                            "top": float(word["top"]),
                            "x1": float(word["x1"]),
                            "bottom": float(word["bottom"]),
                            "page_num": page_num
                        }
                        document_words.append(word_info)

            logging.debug("Extracted %d words from %s", len(document_words), pdf_path)
            all_documents.append({
                "file_name": pdf_path,
                "words": document_words
            })

        except Exception as e:
            logging.error("Failed to read %s: %s", pdf_path, e)
            all_documents.append({
                "file_name": pdf_path,
                "words": [],
                "error": str(e)
            })

    return all_documents
