import React, { useState, useEffect, useRef } from "react";
import { BACKEND_URL } from "./config";
import Sidebar from "./components/Sidebar";

// ── Starter prompts shown on the empty-state screen ──────────────────────────
const directChatPrompts = [
  "Write a Python script to scrape a webpage.",
  "Explain how Docker containers work under the hood.",
  "What are the SOLID principles in software engineering?",
  "Give me 5 architectural tips for microservices.",
];

const ragPrompts = [
  "Summarize the main topics in my uploaded documents.",
  "What key conclusions or recommendations are mentioned?",
  "Find specific definitions or formulas described in the text.",
  "What are the main technical requirements listed?",
];

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  // Modes: "chat" (Direct Llama) or "rag" (Document Knowledge Base)
  const [mode, setMode] = useState("rag");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [serverOnline, setServerOnline] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // ── Data fetching ───────────────────────────────────────────────────────────

  const fetchData = async () => {
    try {
      const threadRes = await fetch(`${BACKEND_URL}/api/threads`);
      if (threadRes.ok) {
        const threadData = await threadRes.json();
        setThreads(threadData.threads || []);
      }
      setServerOnline(true);
    } catch {
      setServerOnline(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // ── Thread & Mode management ────────────────────────────────────────────────

  const handleSelectThread = async (thread) => {
    setActiveThreadId(thread.id);
    setMode(thread.mode || "rag");
    setLoading(true);

    try {
      const [msgRes, docRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/threads/${thread.id}/messages`),
        fetch(`${BACKEND_URL}/api/documents?thread_id=${thread.id}`),
      ]);

      if (msgRes.ok) {
        const data = await msgRes.json();
        setMessages(data.messages || []);
      }
      if (docRes.ok) {
        const docData = await docRes.json();
        setDocuments(docData.documents || []);
      } else {
        setDocuments([]);
      }
    } catch (err) {
      console.error("Failed to load thread details:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = (forcedMode) => {
    setActiveThreadId(null);
    setMessages([]);
    setDocuments([]);
    if (forcedMode) setMode(forcedMode);
  };

  const handleSwitchMode = (newMode) => {
    if (newMode === mode) return;
    handleNewChat(newMode);
  };

  const handleDeleteThread = async (e, threadId) => {
    e.stopPropagation();
    if (!window.confirm("Delete this conversation history and its attached files?")) return;

    try {
      const res = await fetch(`${BACKEND_URL}/api/threads/${threadId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        const data = await res.json();
        setThreads(data.threads || []);
        if (activeThreadId === threadId) handleNewChat();
      }
    } catch (err) {
      console.error("Failed to delete thread:", err);
    }
  };

  // ── Document management (Thread-scoped) ──────────────────────────────────────

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowed = [".pdf", ".txt", ".md", ".docx", ".csv"];
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!allowed.includes(ext)) {
      alert("Please upload a supported file (.pdf, .txt, .md, .docx, .csv).");
      return;
    }

    setMode("rag");
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    if (activeThreadId) {
      formData.append("thread_id", activeThreadId);
    }

    try {
      const res = await fetch(`${BACKEND_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();

      // If a new thread was created on upload, set it active
      if (data.thread_id && data.thread_id !== activeThreadId) {
        setActiveThreadId(data.thread_id);
      }

      setDocuments(data.documents || []);

      // Reload thread messages to include attachment notice
      if (data.thread_id) {
        const msgRes = await fetch(`${BACKEND_URL}/api/threads/${data.thread_id}/messages`);
        if (msgRes.ok) {
          const msgData = await msgRes.json();
          setMessages(msgData.messages || []);
        }
      }

      // Refresh threads list in sidebar
      const threadRes = await fetch(`${BACKEND_URL}/api/threads`);
      if (threadRes.ok) {
        const threadData = await threadRes.json();
        setThreads(threadData.threads || []);
      }
    } catch (err) {
      console.error(err);
      alert("Error uploading file. Make sure your FastAPI server is running on port 8000.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteDocument = async (filename) => {
    if (!window.confirm(`Remove "${filename}" from this chat?`)) return;

    try {
      const url = activeThreadId
        ? `${BACKEND_URL}/api/documents/${encodeURIComponent(filename)}?thread_id=${activeThreadId}`
        : `${BACKEND_URL}/api/documents/${encodeURIComponent(filename)}`;

      const res = await fetch(url, { method: "DELETE" });
      if (!res.ok) throw new Error("Delete failed");
      const data = await res.json();

      setDocuments(data.documents || []);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `🗑️ Removed document **${filename}** from this chat.`,
        },
      ]);
    } catch (err) {
      console.error(err);
      alert(`Failed to delete "${filename}".`);
    }
  };

  // ── Chat ────────────────────────────────────────────────────────────────────

  const handleSend = async (customPrompt) => {
    const textToSend = customPrompt || input.trim();
    if (!textToSend || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: textToSend }]);
    setInput("");
    setLoading(true);

    // Append a blank assistant message that we'll fill token-by-token
    setMessages((prev) => [...prev, { role: "assistant", content: "", sources: [] }]);

    try {
      const res = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: textToSend, mode, thread_id: activeThreadId }),
      });

      if (!res.ok) throw new Error("Stream request failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE lines are separated by "\n\n"
        const parts = buffer.split("\n\n");
        buffer = parts.pop(); // keep any incomplete chunk

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data: ")) continue;

          const payload = JSON.parse(line.slice(6));

          if (payload.token) {
            // Append token to the last (streaming) assistant message
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = {
                ...last,
                content: last.content + payload.token,
              };
              return updated;
            });
          }

          if (payload.done) {
            // Finalise: attach sources and store thread_id
            if (payload.thread_id) setActiveThreadId(payload.thread_id);
            if (payload.sources?.length) {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  sources: payload.sources,
                };
                return updated;
              });
            }
            // Refresh threads sidebar
            const threadRes = await fetch(`${BACKEND_URL}/api/threads`);
            if (threadRes.ok) {
              const threadData = await threadRes.json();
              setThreads(threadData.threads || []);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: "⚠️ Failed to get answer. Please check if your FastAPI backend is running.",
          sources: [],
        };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen bg-[#212121] text-zinc-100 font-sans overflow-hidden">
      {/* ── Sidebar ── */}
      <Sidebar
        showSidebar={showSidebar}
        threads={threads}
        activeThreadId={activeThreadId}
        serverOnline={serverOnline}
        onNewChat={() => handleNewChat()}
        onSelectThread={handleSelectThread}
        onDeleteThread={handleDeleteThread}
      />

      {/* ── Main Chat Container ── */}
      <main className="flex-1 flex flex-col h-full bg-[#212121] relative overflow-hidden">
        {/* Top Header with Mode Toggle */}
        <header className="h-14 border-b border-zinc-800/80 flex items-center justify-between px-4 text-sm text-zinc-300">
          <div className="flex items-center gap-3">
            {/* Sidebar toggle */}
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition"
              title="Toggle Sidebar"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            {/* Mode Switcher */}
            <div className="flex items-center bg-zinc-800/90 p-1 rounded-xl border border-zinc-700/60">
              <button
                onClick={() => handleSwitchMode("chat")}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                  mode === "chat"
                    ? "bg-zinc-700 text-zinc-100 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <span>💬</span>
                <span>Direct Chat</span>
              </button>
              <button
                onClick={() => handleSwitchMode("rag")}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                  mode === "rag"
                    ? "bg-emerald-700/80 text-emerald-100 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <span>📄</span>
                <span>RAG Mode</span>
              </button>
            </div>

            {/* Attached Document Pill (in RAG mode) */}
            {mode === "rag" && documents.length > 0 && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-950/60 border border-emerald-800/40 rounded-xl text-xs text-emerald-300">
                <span>📎</span>
                <span className="font-medium truncate max-w-[150px]" title={documents.map((d) => d.filename).join(", ")}>
                  {documents[0].filename}
                </span>
                {documents.length > 1 && (
                  <span className="text-[10px] bg-emerald-900/80 px-1.5 py-0.5 rounded-full text-emerald-200">
                    +{documents.length - 1}
                  </span>
                )}
                <button
                  onClick={() => handleDeleteDocument(documents[0].filename)}
                  className="ml-1 text-emerald-500 hover:text-rose-400 transition"
                  title="Remove document from this chat"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}
          </div>

          <div className="text-xs text-zinc-400 hidden sm:flex items-center gap-2">
            <span>Model:</span>
            <span className="text-zinc-200 font-mono font-medium">llama3.2:3b</span>
          </div>
        </header>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto px-4 md:px-0">
          {messages.length === 0 ? (
            /* Empty State */
            <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center px-4">
              <div className="w-12 h-12 rounded-2xl bg-zinc-800 border border-zinc-700 flex items-center justify-center mb-4 text-emerald-400">
                <span className="text-2xl">{mode === "chat" ? "💬" : "📄"}</span>
              </div>
              <h1 className="text-2xl font-semibold text-zinc-100 mb-2">
                {mode === "chat" ? "Direct Chat with Llama 3.2" : "Document Q&A (RAG)"}
              </h1>
              <p className="text-sm text-zinc-400 mb-6 max-w-md">
                {mode === "chat"
                  ? "Chat freely with the local model. All messages are stored in your local SQLite database."
                  : documents.length > 0
                  ? `Chatting with ${documents[0].filename}${documents.length > 1 ? ` (+${documents.length - 1} more)` : ""}.`
                  : "Attach a document to this chat to ask questions with exact citations."}
              </p>

              {/* RAG Mode: Prompt to attach document if none attached */}
              {mode === "rag" && documents.length === 0 && (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full max-w-md p-5 border-2 border-dashed border-zinc-700 hover:border-emerald-500/60 rounded-2xl bg-zinc-800/30 hover:bg-zinc-800/60 cursor-pointer transition flex flex-col items-center justify-center gap-2.5 mb-6 group shadow-sm"
                >
                  <div className="w-10 h-10 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center group-hover:scale-110 transition">
                    {uploading ? (
                      <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                      </svg>
                    ) : (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                      </svg>
                    )}
                  </div>
                  <div className="text-center">
                    <div className="text-xs font-medium text-zinc-200 group-hover:text-emerald-300 transition">
                      {uploading ? "Indexing document..." : "Click to attach a document to this chat"}
                    </div>
                    <div className="text-[11px] text-zinc-500 mt-0.5">
                      Supports PDF, TXT, Markdown, DOCX, CSV
                    </div>
                  </div>
                </div>
              )}

              {/* Starter Prompt Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 w-full">
                {(mode === "chat" ? directChatPrompts : ragPrompts).map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(prompt)}
                    className="p-3 text-left text-xs bg-zinc-800/40 hover:bg-zinc-800 border border-zinc-700/50 rounded-xl text-zinc-300 hover:text-zinc-100 transition flex items-center justify-between group"
                  >
                    <span>{prompt}</span>
                    <svg className="w-4 h-4 text-zinc-400 group-hover:text-zinc-200 shrink-0 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Active Messages List */
            <div className="max-w-3xl mx-auto py-6 space-y-6">
              {messages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex gap-4 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-full bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center shrink-0 text-sm font-semibold">
                      AI
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-[#2f2f2f] text-zinc-100 rounded-tr-sm"
                        : "bg-transparent text-zinc-200 pl-0"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>

                    {/* Source Citations */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-4 pt-3 border-t border-zinc-800/80">
                        <div className="text-[11px] uppercase tracking-wider text-zinc-400 font-semibold mb-2 flex items-center gap-1.5">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          <span>Retrieved Sources</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {msg.sources.map((src, i) => (
                            <div
                              key={i}
                              className="px-2.5 py-1 rounded-md bg-zinc-800/80 border border-zinc-700/60 text-[11px] text-zinc-300"
                              title={src.preview}
                            >
                              <span className="font-medium text-emerald-400">{src.source}</span>
                              <span className="text-zinc-400 mx-1">•</span>
                              <span>Page {src.page}</span>
                              <span className="text-zinc-400 ml-1">({src.score})</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {msg.role === "user" && (
                    <div className="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center shrink-0 text-xs font-semibold text-zinc-300">
                      U
                    </div>
                  )}
                </div>
              ))}

              {/* Loading indicator — shown only before the first token arrives */}
              {loading && messages[messages.length - 1]?.content === "" && (
                <div className="flex gap-4 items-center">
                  <div className="w-8 h-8 rounded-full bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center shrink-0 text-sm font-semibold">
                    AI
                  </div>
                  <div className="flex items-center gap-1.5 py-2">
                    <span className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse"></span>
                    <span className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse [animation-delay:200ms]"></span>
                    <span className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse [animation-delay:400ms]"></span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Floating Bottom Input Bar ── */}
        <div className="p-4 bg-gradient-to-t from-[#212121] via-[#212121] to-transparent">
          <div className="max-w-3xl mx-auto">
            <div className="relative flex items-center bg-[#2f2f2f] rounded-2xl border border-zinc-700/80 shadow-lg px-3 py-2">
              {/* Attach / upload button */}
              <button
                onClick={() => {
                  if (mode === "chat") setMode("rag");
                  fileInputRef.current?.click();
                }}
                disabled={uploading}
                className={`p-2 rounded-lg transition mr-1 ${
                  mode === "rag" && documents.length > 0
                    ? "text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50"
                }`}
                title={mode === "chat" ? "Attach document (switches to RAG Mode)" : "Attach document to this chat"}
              >
                {uploading ? (
                  <svg className="w-5 h-5 animate-spin text-emerald-400" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                )}
              </button>

              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  uploading
                    ? "Indexing document into this chat..."
                    : mode === "chat"
                    ? "Message Llama 3.2 directly..."
                    : documents.length > 0
                    ? `Ask about ${documents[0].filename}...`
                    : "Attach a document using 📎 or ask a question..."
                }
                disabled={loading}
                className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-400 focus:outline-none px-2 py-1"
              />

              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                className={`p-2 rounded-xl transition ${
                  input.trim() && !loading
                    ? "bg-zinc-100 text-zinc-900 hover:bg-white"
                    : "bg-zinc-700/60 text-zinc-400 cursor-not-allowed"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
              </button>
            </div>

            <div className="text-center mt-2 text-[11px] text-zinc-400">
              {mode === "chat"
                ? "Direct Chat Mode: Instant responses saved locally in SQLite."
                : documents.length > 0
                ? `RAG Mode: Scoped to ${documents[0].filename}${documents.length > 1 ? ` (+${documents.length - 1} more)` : ""}.`
                : "RAG Mode: Attach a document below to scope this chat's knowledge base."}
            </div>
          </div>
        </div>
      </main>

      {/* Hidden file input (used by sidebar and input bar's attach button) */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".pdf,.txt,.md,.docx,.csv"
        className="hidden"
      />
    </div>
  );
}
