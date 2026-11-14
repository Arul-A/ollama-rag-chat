import os
import shutil
import uuid
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

import db
from rag_service import (
    DOCS_DIR,
    SUPPORTED_EXTENSIONS,
    list_documents,
    add_document,
    delete_document,
    delete_thread_documents,
    chat_direct,
    chat_rag,
    stream_chat_direct,
    stream_chat_rag,
    get_vectorstore
)

app = FastAPI(
    title="LocalAI-RAG API with SQLite Chat History",
    description="Dual-Mode RAG, Multi-Document Vector DB, and Local Chat History."
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    mode: str = "rag"  # "chat" or "rag"
    thread_id: Optional[str] = None


class ThreadCreateRequest(BaseModel):
    title: Optional[str] = "New Chat"
    mode: Optional[str] = "rag"


@app.get("/")
def health_check():
    docs = list_documents()
    threads = db.get_all_threads()
    return {
        "status": "online",
        "message": "LocalAI-RAG Server is running",
        "total_documents": len(docs),
        "total_threads": len(threads),
        "documents": docs
    }


# ==============================================================================
# THREAD & CHAT HISTORY ENDPOINTS (SQLite)
# ==============================================================================

@app.get("/api/threads")
def list_threads():
    """Returns all past chat conversations ordered by recency."""
    return {
        "status": "success",
        "threads": db.get_all_threads()
    }


@app.post("/api/threads")
def create_new_thread(payload: ThreadCreateRequest):
    """Creates a new conversation thread."""
    thread_id = str(uuid.uuid4())
    thread = db.create_thread(thread_id, payload.title or "New Chat", payload.mode or "rag")
    return {
        "status": "success",
        "thread": thread
    }


@app.get("/api/threads/{thread_id}/messages")
def get_messages(thread_id: str):
    """Retrieves all past messages in a specific thread."""
    messages = db.get_thread_messages(thread_id)
    return {
        "status": "success",
        "thread_id": thread_id,
        "messages": messages
    }


@app.delete("/api/threads/{thread_id}")
def remove_thread(thread_id: str):
    """Deletes a conversation thread, its message history, and associated vectors."""
    delete_thread_documents(thread_id)
    db.delete_thread(thread_id)
    return {
        "status": "success",
        "message": f"Thread '{thread_id}' and its vectors deleted.",
        "threads": db.get_all_threads()
    }


# ==============================================================================
# DOCUMENT MANAGEMENT ENDPOINTS (Chroma DB - Thread-Scoped)
# ==============================================================================

@app.get("/api/documents")
def get_documents(thread_id: Optional[str] = None):
    return {
        "status": "success",
        "documents": list_documents(thread_id=thread_id)
    }


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    thread_id: Optional[str] = Form(None)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported_str = ", ".join(SUPPORTED_EXTENSIONS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Supported formats: {supported_str}"
        )

    # If no thread_id provided, create a new thread for this document
    if not thread_id:
        thread_id = str(uuid.uuid4())
        title = f"Doc: {file.filename[:30]}"
        db.create_thread(thread_id, title, "rag")
    else:
        # If thread exists with 0 messages, name it after the document
        existing_msgs = db.get_thread_messages(thread_id)
        if len(existing_msgs) == 0:
            db.update_thread_title(thread_id, f"Doc: {file.filename[:30]}")

    os.makedirs(DOCS_DIR, exist_ok=True)
    save_path = os.path.join(DOCS_DIR, file.filename)

    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        pages, chunks = add_document(save_path, file.filename, thread_id=thread_id)

        # Record attachment notification in chat thread
        db.add_message(
            thread_id,
            "assistant",
            f"📎 Attached **{file.filename}** ({pages} pages, {chunks} chunks). You can now ask questions about this document!"
        )

        return {
            "status": "success",
            "message": f"'{file.filename}' uploaded and indexed for this chat.",
            "filename": file.filename,
            "pages": pages,
            "chunks": chunks,
            "thread_id": thread_id,
            "documents": list_documents(thread_id=thread_id)
        }
    except Exception as e:
        print(f"[ERROR] Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@app.delete("/api/documents/{filename}")
def remove_document(filename: str, thread_id: Optional[str] = None):
    try:
        delete_document(filename, thread_id=thread_id)
        return {
            "status": "success",
            "message": f"Document '{filename}' and its vectors were removed.",
            "documents": list_documents(thread_id=thread_id)
        }
    except Exception as e:
        print(f"[ERROR] Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


# ==============================================================================
# CHAT ENDPOINT WITH PERSISTENCE (SQLite + Chroma + Ollama)
# ==============================================================================

@app.post("/api/chat")
def handle_chat(request: ChatRequest):
    user_query = request.question.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    thread_id = request.thread_id

    # If no thread_id provided, create a new thread with a title from the first question
    if not thread_id:
        thread_id = str(uuid.uuid4())
        title = (user_query[:35] + "...") if len(user_query) > 35 else user_query
        db.create_thread(thread_id, title, request.mode)
    else:
        existing_msgs = db.get_thread_messages(thread_id)
        if len(existing_msgs) == 0:
            title = (user_query[:35] + "...") if len(user_query) > 35 else user_query
            db.update_thread_title(thread_id, title)

    # 1. Record user's message in SQLite
    db.add_message(thread_id, "user", user_query)

    try:
        # 2. Generate response (scoped by thread_id)
        if request.mode == "chat":
            result = chat_direct(user_query)
        else:
            result = chat_rag(user_query, thread_id=thread_id)

        answer = result["answer"]
        sources = result.get("sources", [])

        # 3. Record assistant's response and citations in SQLite
        db.add_message(thread_id, "assistant", answer, sources=sources)

        return {
            "status": "success",
            "thread_id": thread_id,
            "mode": request.mode,
            "answer": answer,
            "sources": sources
        }
    except Exception as e:
        print(f"[ERROR] Chat generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat generation error: {str(e)}")


# ==============================================================================
# STREAMING CHAT ENDPOINT (Server-Sent Events)
# ==============================================================================

@app.post("/api/chat/stream")
async def handle_chat_stream(request: ChatRequest):
    """
    Streams LLM tokens as Server-Sent Events (SSE).
    Each event is:  data: {"token": "..."}\n\n
    Final event is: data: {"done": true, "thread_id": "...", "sources": [...]}\n\n
    """
    user_query = request.question.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    thread_id = request.thread_id

    # Create or reuse a thread
    if not thread_id:
        thread_id = str(uuid.uuid4())
        title = (user_query[:35] + "...") if len(user_query) > 35 else user_query
        db.create_thread(thread_id, title, request.mode)
    else:
        existing_msgs = db.get_thread_messages(thread_id)
        if len(existing_msgs) == 0:
            title = (user_query[:35] + "...") if len(user_query) > 35 else user_query
            db.update_thread_title(thread_id, title)

    db.add_message(thread_id, "user", user_query)

    import json

    def event_generator():
        full_answer = []
        final_sources = []

        try:
            gen = (
                stream_chat_direct(user_query)
                if request.mode == "chat"
                else stream_chat_rag(user_query, thread_id=thread_id)
            )

            for event in gen:
                # Parse to separate token events from the done event
                if event.startswith("data: "):
                    payload = json.loads(event[6:])
                    if "token" in payload:
                        full_answer.append(payload["token"])
                    elif payload.get("done"):
                        final_sources = payload.get("sources", [])
                yield event

        except Exception as e:
            print(f"[ERROR] Stream generation failed: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Persist the full assembled answer to SQLite after streaming completes
            if full_answer:
                answer_text = "".join(full_answer)
                db.add_message(thread_id, "assistant", answer_text, sources=final_sources)

            # Send final metadata event so the client knows thread_id and sources
            yield f"data: {json.dumps({'done': True, 'thread_id': thread_id, 'sources': final_sources})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables Nginx buffering if proxied
        }
    )


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" >>> Starting LocalAI-RAG Server on http://localhost:8000")
    print(" >>> SQLite Chat History + Chroma Vector Database Enabled")
    print("=" * 60 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
