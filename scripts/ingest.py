import sys
from mind.chroma_manager import ChromaManager

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/ingest.py <doc_id> <path_to_pdf>")
        return
    doc_id = sys.argv[1]
    path = sys.argv[2]
    cm = ChromaManager()
    cm.ingest_document(doc_id, path)
    print("Done.")

if __name__ == "__main__":
    main()

