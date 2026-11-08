import os
import json
from langchain_community.document_loaders import PyPDFLoader
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


def list_documents():
    """Returns a list of all distinct documents and their chunk counts in Chroma DB."""
    vstore = get_vectorstore()
    count = vstore._collection.count()
    if count == 0:
        return []

    data = vstore._collection.get(include=["metadatas"])
    metadatas = data.get("metadatas", [])

    summary = {}
    for meta in metadatas:
        if not meta:
            continue
        source = meta.get("source", "Unknown")
        page = meta.get("page", 0)

        if source not in summary:
            summary[source] = {
                "filename": source,
                "chunks": 0,
                "pages": 0
            }
        summary[source]["chunks"] += 1
        summary[source]["pages"] = max(summary[source]["pages"], page + 1)

    return list(summary.values())


def add_document(file_path: str, filename: str):
    """
    Chunks a new PDF, tags every chunk with the filename in metadata,
    and appends the vectors into Chroma DB.
    """
    vstore = get_vectorstore()

    print(f"\n[*] Processing document: {filename}")
    loader = PyPDFLoader(file_path)
    pages = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        add_start_index=True
    )
    chunks = text_splitter.split_documents(pages)

    # Ensure metadata has the exact clean filename
    for chunk in chunks:
        chunk.metadata["source"] = filename

    print(f"[*] Embedding and adding {len(chunks)} chunks to Chroma DB...")
    vstore.add_documents(chunks)
    print(f"[✓] Added '{filename}' successfully!")

    return len(pages), len(chunks)


def delete_document(filename: str):
    """
    Deletes all vectors belonging to a specific document from Chroma DB
    and removes the file from the docs folder.
    """
    vstore = get_vectorstore()

    print(f"[*] Deleting vectors for: '{filename}' from Chroma DB...")
    vstore._collection.delete(where={"source": filename})

    # Delete physical file
    target_file = os.path.join(DOCS_DIR, filename)
    if os.path.exists(target_file):
        os.remove(target_file)
        print(f"[✓] Removed file from disk: {target_file}")

    print(f"[✓] Document '{filename}' deleted from knowledge base.")
    return True


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
    """Direct chat with Llama 3.2 with multi-turn memory."""
    print(f"[*] Direct chat with Llama 3.2: '{query}'")
    llm = ChatOllama(model=LLM_MODEL, temperature=0.7)
    
    history_text = format_history(history)
    if history_text:
        prompt = f"""You are a helpful, intelligent, and friendly AI assistant.
Previous conversation history:
{history_text}

User: {query}
Assistant:"""
    else:
        prompt = f"""You are a helpful, intelligent, and friendly AI assistant.
Answer the following question clearly and concisely:

{query}"""
    
    response = llm.invoke(prompt)
    return {
        "answer": response.content,
        "sources": []
    }


def chat_rag(query: str, history=None):
    """RAG mode: searches across uploaded documents with multi-turn memory."""
    vstore = get_vectorstore()
    total_vectors = vstore._collection.count()

    if total_vectors == 0:
        return {
            "answer": "No documents have been uploaded yet. Please upload a PDF in the sidebar to ask questions in RAG mode, or switch to Direct Chat mode.",
            "sources": []
        }

    print(f"[*] Searching Chroma DB across {total_vectors} vectors for query: '{query}'")
    results = vstore.similarity_search_with_score(query, k=4)

    sources = []
    context_chunks = []
    for doc, score in results:
        source_name = doc.metadata.get("source", "Document")
        page_num = doc.metadata.get("page", 0) + 1
        snippet = doc.page_content.strip().replace("\n", " ")[:200]

        sources.append({
            "source": source_name,
            "page": page_num,
            "preview": snippet,
            "score": round(float(score), 4)
        })
        context_chunks.append(f"[{source_name} - Page {page_num}]\n{doc.page_content}")

    context_text = "\n\n---\n\n".join(context_chunks)
    history_text = format_history(history)
    history_section = f"CONVERSATION HISTORY:\n{history_text}\n\n" if history_text else ""

    prompt = f"""You are an expert AI assistant answering questions based on the user's uploaded documents.
Answer the question based STRICTLY and ONLY on the following retrieved context.
If the context does not contain enough information to answer, state clearly: "The uploaded documents do not contain information to answer this question."

{history_section}CONTEXT:
{context_text}

QUESTION:
{query}

ANSWER:"""

    print("[*] Generating grounded response with Llama 3.2...")
    llm = ChatOllama(model=LLM_MODEL, temperature=0)
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

    history_text = format_history(history)
    if history_text:
        prompt = f"""You are a helpful, intelligent, and friendly AI assistant.
Previous conversation history:
{history_text}

User: {query}
Assistant:"""
    else:
        prompt = f"""You are a helpful, intelligent, and friendly AI assistant.
Answer the following question clearly and concisely:

{query}"""

    for chunk in llm.stream(prompt):
        token = chunk.content
        if token:
            yield f"data: {json.dumps({'token': token})}\n\n"

    # Signal completion (no sources in direct chat)
    yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"


def stream_chat_rag(query: str, history=None):
    """Generator: retrieves context from Chroma, then streams tokens for RAG mode."""
    vstore = get_vectorstore()
    total_vectors = vstore._collection.count()

    if total_vectors == 0:
        msg = "No documents have been uploaded yet. Please upload a PDF in the sidebar to ask questions in RAG mode, or switch to Direct Chat mode."
        yield f"data: {json.dumps({'token': msg})}\n\n"
        yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
        return

    print(f"[*] Searching Chroma DB across {total_vectors} vectors for query: '{query}'")
    results = vstore.similarity_search_with_score(query, k=4)

    sources = []
    context_chunks = []
    for doc, score in results:
        source_name = doc.metadata.get("source", "Document")
        page_num = doc.metadata.get("page", 0) + 1
        snippet = doc.page_content.strip().replace("\n", " ")[:200]

        sources.append({
            "source": source_name,
            "page": page_num,
            "preview": snippet,
            "score": round(float(score), 4)
        })
        context_chunks.append(f"[{source_name} - Page {page_num}]\n{doc.page_content}")

    context_text = "\n\n---\n\n".join(context_chunks)
    history_text = format_history(history)
    history_section = f"CONVERSATION HISTORY:\n{history_text}\n\n" if history_text else ""

    prompt = f"""You are an expert AI assistant answering questions based on the user's uploaded documents.
Answer the question based STRICTLY and ONLY on the following retrieved context.
If the context does not contain enough information to answer, state clearly: "The uploaded documents do not contain information to answer this question."

{history_section}CONTEXT:
{context_text}

QUESTION:
{query}

ANSWER:"""

    llm = ChatOllama(model=LLM_MODEL, temperature=0)
    for chunk in llm.stream(prompt):
        token = chunk.content
        if token:
            yield f"data: {json.dumps({'token': token})}\n\n"

    # Signal completion with source citations
    yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"
