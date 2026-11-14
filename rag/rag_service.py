import os
import json
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    CSVLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_community.vectorstores import Chroma

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
EMBEDDING_MODEL = "nomic-embed-text"
LLM_MODEL = "llama3.2:3b"

# Ensure docs directory exists
os.makedirs(DOCS_DIR, exist_ok=True)

# Shared embedding and vectorstore instance
embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)
_vectorstore = None


def get_vectorstore():
    """Initializes and returns a persistent Chroma DB collection."""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            collection_name="user_documents",
            persist_directory=CHROMA_DIR,
            embedding_function=embeddings
        )
    return _vectorstore


SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF",
    ".txt": "Text",
    ".md": "Markdown",
    ".docx": "Word Document",
    ".csv": "CSV"
}


def get_loader(file_path: str, filename: str):
    """Selects the appropriate LangChain document loader based on file extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return PyPDFLoader(file_path)
    elif ext in [".txt", ".md"]:
        return TextLoader(file_path, encoding="utf-8")
    elif ext == ".docx":
        return Docx2txtLoader(file_path)
    elif ext == ".csv":
        return CSVLoader(file_path, encoding="utf-8")
    else:
        supported = ", ".join(SUPPORTED_EXTENSIONS.keys())
        raise ValueError(f"Unsupported file format '{ext}'. Supported formats: {supported}")


def list_documents(thread_id: str = None):
    """Returns a list of all distinct documents and their chunk counts in Chroma DB, optionally filtered by thread_id."""
    vstore = get_vectorstore()
    count = vstore._collection.count()
    if count == 0:
        return []

    if thread_id:
        data = vstore._collection.get(where={"thread_id": thread_id}, include=["metadatas"])
    else:
        data = vstore._collection.get(include=["metadatas"])

    metadatas = data.get("metadatas", [])

    summary = {}
    for meta in metadatas:
        if not meta:
            continue
        source = meta.get("source", "Unknown")
        raw_page = meta.get("page")
        page = raw_page if isinstance(raw_page, int) else 0

        if source not in summary:
            summary[source] = {
                "filename": source,
                "chunks": 0,
                "pages": 0,
                "thread_id": meta.get("thread_id")
            }
        summary[source]["chunks"] += 1
        summary[source]["pages"] = max(summary[source]["pages"], page + 1)

    return list(summary.values())


def add_document(file_path: str, filename: str, thread_id: str = None):
    """
    Chunks a new document (PDF, TXT, MD, DOCX, CSV), tags every chunk with the filename and thread_id in metadata,
    and appends the vectors into Chroma DB.
    """
    vstore = get_vectorstore()

    print(f"\n[*] Processing document: {filename} (Thread: {thread_id})")
    loader = get_loader(file_path, filename)
    pages = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        add_start_index=True
    )
    chunks = text_splitter.split_documents(pages)

    # Ensure metadata has the exact clean filename, thread_id, and a default page/section number
    for chunk in chunks:
        chunk.metadata["source"] = filename
        if thread_id:
            chunk.metadata["thread_id"] = thread_id
        if "page" not in chunk.metadata or chunk.metadata["page"] is None:
            chunk.metadata["page"] = 0

    print(f"[*] Embedding and adding {len(chunks)} chunks to Chroma DB...")
    vstore.add_documents(chunks)
    print(f"[✓] Added '{filename}' successfully to thread '{thread_id}'!")

    return len(pages), len(chunks)


def delete_document(filename: str, thread_id: str = None):
    """
    Deletes all vectors belonging to a specific document (and thread if provided) from Chroma DB
    and removes the file from the docs folder if no other thread uses it.
    """
    vstore = get_vectorstore()

    print(f"[*] Deleting vectors for: '{filename}' from Chroma DB (thread={thread_id})...")
    if thread_id:
        vstore._collection.delete(where={"$and": [{"source": filename}, {"thread_id": thread_id}]})
    else:
        vstore._collection.delete(where={"source": filename})

    # Delete physical file if no other thread references it
    remaining = vstore._collection.get(where={"source": filename}, include=["metadatas"])
    if not remaining.get("metadatas"):
        target_file = os.path.join(DOCS_DIR, filename)
        if os.path.exists(target_file):
            os.remove(target_file)
            print(f"[✓] Removed file from disk: {target_file}")

    print(f"[✓] Document '{filename}' deleted from knowledge base.")
    return True


def delete_thread_documents(thread_id: str):
    """Deletes all vectors associated with a specific thread from Chroma DB."""
    if not thread_id:
        return
    vstore = get_vectorstore()
    try:
        print(f"[*] Deleting all vectors for thread: '{thread_id}' from Chroma DB...")
        # Check files referenced
        data = vstore._collection.get(where={"thread_id": thread_id}, include=["metadatas"])
        metadatas = data.get("metadatas", [])
        sources = {m.get("source") for m in metadatas if m and m.get("source")}

        vstore._collection.delete(where={"thread_id": thread_id})

        # Remove physical files if not used by any other thread
        for src in sources:
            remaining = vstore._collection.get(where={"source": src}, include=["metadatas"])
            if not remaining.get("metadatas"):
                target_file = os.path.join(DOCS_DIR, src)
                if os.path.exists(target_file):
                    os.remove(target_file)
                    print(f"[✓] Removed file from disk: {target_file}")
    except Exception as e:
        print(f"[!] Note on thread vector cleanup: {e}")


def format_history(history):
    """Formats the last few conversation turns for prompt memory context."""
    if not history:
        return ""
    lines = []
    # Take up to last 6 messages to preserve context without overflowing tokens
    for msg in history[-6:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def chat_direct(query: str, history=None):
    """Direct chat with Llama 3.2."""
    print(f"[*] Direct chat with Llama 3.2: '{query}'")
    llm = ChatOllama(model=LLM_MODEL, temperature=0.7)
    
    prompt = f"""You are a helpful, intelligent, and friendly AI assistant.
Answer the following question clearly and concisely:

{query}"""
    
    response = llm.invoke(prompt)
    return {
        "answer": response.content,
        "sources": []
    }


def chat_rag(query: str, thread_id: str = None, history=None):
    """RAG mode: searches across uploaded documents for the active thread with general knowledge fallback."""
    vstore = get_vectorstore()

    # Determine vector count for this thread (or globally if no thread_id)
    if thread_id:
        existing = vstore._collection.get(where={"thread_id": thread_id}, include=["metadatas"])
        total_vectors = len(existing.get("ids", []))
    else:
        total_vectors = vstore._collection.count()

    if total_vectors == 0:
        print(f"[*] No documents attached to thread {thread_id}, falling back to direct LLM response...")
        direct_res = chat_direct(query)
        return {
            "answer": f"*(Note: No document attached to this chat — answering from general knowledge)*\n\n" + direct_res["answer"],
            "sources": []
        }

    print(f"[*] Searching Chroma DB across {total_vectors} vectors for query: '{query}' (thread: {thread_id})")
    search_filter = {"thread_id": thread_id} if thread_id else None
    results = vstore.similarity_search_with_score(query, k=4, filter=search_filter)

    sources = []
    context_chunks = []
    for doc, score in results:
        source_name = doc.metadata.get("source", "Document")
        raw_page = doc.metadata.get("page")
        page_num = (raw_page if isinstance(raw_page, int) else 0) + 1
        snippet = doc.page_content.strip().replace("\n", " ")[:200]

        sources.append({
            "source": source_name,
            "page": page_num,
            "preview": snippet,
            "score": round(float(score), 4)
        })
        context_chunks.append(f"[{source_name} - Page {page_num}]\n{doc.page_content}")

    context_text = "\n\n---\n\n".join(context_chunks)

    prompt = f"""You are a helpful AI assistant answering questions about uploaded documents.

CONTEXT FROM UPLOADED DOCUMENTS:
{context_text}

QUESTION:
{query}

INSTRUCTIONS:
- First, check the CONTEXT above. If the CONTEXT contains information related to the question, answer the question using the facts, details, and source citations from the CONTEXT.
- Only if the CONTEXT has no information about the question at all, fall back to answering using your general knowledge, and mention that the topic was not found in the uploaded documents.

ANSWER:"""

    print("[*] Generating response with Llama 3.2...")
    llm = ChatOllama(model=LLM_MODEL, temperature=0.0)
    response = llm.invoke(prompt)

    return {
        "answer": response.content,
        "sources": sources
    }


# ==============================================================================
# STREAMING VARIANTS
# Each generator yields SSE-formatted lines:
#   data: {"token": "..."}\n\n   — incremental text token
#   data: {"done": true, "sources": [...]}\n\n  — final event with metadata
# ==============================================================================

def stream_chat_direct(query: str, history=None):
    """Generator: streams tokens for direct chat mode."""
    llm = ChatOllama(model=LLM_MODEL, temperature=0.7)

    prompt = f"""You are a helpful, intelligent, and friendly AI assistant.
Answer the following question clearly and concisely:

{query}"""

    for chunk in llm.stream(prompt):
        token = chunk.content
        if token:
            yield f"data: {json.dumps({'token': token})}\n\n"

    # Signal completion (no sources in direct chat)
    yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"


def stream_chat_rag(query: str, thread_id: str = None, history=None):
    """Generator: retrieves context from Chroma for the active thread, then streams tokens for RAG mode."""
    vstore = get_vectorstore()

    # Determine vector count for this thread (or globally if no thread_id)
    if thread_id:
        existing = vstore._collection.get(where={"thread_id": thread_id}, include=["metadatas"])
        total_vectors = len(existing.get("ids", []))
    else:
        total_vectors = vstore._collection.count()

    if total_vectors == 0:
        print(f"[*] No documents attached to thread {thread_id}, falling back to direct LLM stream...")
        fallback_notice = json.dumps({"token": "*(Note: No document attached to this chat — answering from general knowledge)*\n\n"})
        yield f"data: {fallback_notice}\n\n"
        for chunk in stream_chat_direct(query):
            yield chunk
        return

    print(f"[*] Searching Chroma DB across {total_vectors} vectors for query: '{query}' (thread: {thread_id})")
    search_filter = {"thread_id": thread_id} if thread_id else None
    results = vstore.similarity_search_with_score(query, k=4, filter=search_filter)

    sources = []
    context_chunks = []
    for doc, score in results:
        source_name = doc.metadata.get("source", "Document")
        raw_page = doc.metadata.get("page")
        page_num = (raw_page if isinstance(raw_page, int) else 0) + 1
        snippet = doc.page_content.strip().replace("\n", " ")[:200]

        sources.append({
            "source": source_name,
            "page": page_num,
            "preview": snippet,
            "score": round(float(score), 4)
        })
        context_chunks.append(f"[{source_name} - Page {page_num}]\n{doc.page_content}")

    context_text = "\n\n---\n\n".join(context_chunks)

    prompt = f"""You are a helpful AI assistant answering questions about uploaded documents.

CONTEXT FROM UPLOADED DOCUMENTS:
{context_text}

QUESTION:
{query}

INSTRUCTIONS:
- First, check the CONTEXT above. If the CONTEXT contains information related to the question, answer the question using the facts, details, and source citations from the CONTEXT.
- Only if the CONTEXT has no information about the question at all, fall back to answering using your general knowledge, and mention that the topic was not found in the uploaded documents.

ANSWER:"""

    llm = ChatOllama(model=LLM_MODEL, temperature=0.0)
    for chunk in llm.stream(prompt):
        token = chunk.content
        if token:
            yield f"data: {json.dumps({'token': token})}\n\n"

    # Signal completion with source citations
    yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"
