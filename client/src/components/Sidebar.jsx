import React from "react";

/**
 * Sidebar component — displays:
 *  - New Chat button
 *  - Recent chat threads (from SQLite via backend)
 *  - Knowledge Base documents (indexed in Chroma DB)
 *  - Server connection status footer
 */
export default function Sidebar({
  showSidebar,
  threads,
  activeThreadId,
  documents,
  uploading,
  serverOnline,
  fileInputRef,
  onNewChat,
  onSelectThread,
  onDeleteThread,
  onDeleteDocument,
}) {
  return (
    <aside
      className={`${
        showSidebar ? "w-72" : "w-0"
      } transition-all duration-300 ease-in-out bg-[#171717] border-r border-zinc-800 flex flex-col justify-between overflow-hidden shrink-0`}
    >
      <div className="p-3 flex flex-col gap-3 h-[calc(100vh-60px)]">
        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="flex items-center justify-between w-full px-3 py-2 text-sm font-medium rounded-lg hover:bg-zinc-800 text-zinc-200 border border-zinc-700/60 transition"
        >
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            <span>New chat</span>
          </div>
          <span className="text-xs text-zinc-400">⌘K</span>
        </button>

        {/* Section 1: Chat Threads History (SQLite) */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-2 mb-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Recent Chats ({threads.length})
            </span>
          </div>

          <div className="overflow-y-auto space-y-1 flex-1 pr-1">
            {threads.length === 0 ? (
              <div className="text-xs text-zinc-500 p-2 text-center">
                No saved chats yet.
              </div>
            ) : (
              threads.map((t) => (
                <div
                  key={t.id}
                  onClick={() => onSelectThread(t)}
                  className={`p-2 rounded-lg text-xs flex items-center justify-between cursor-pointer group transition ${
                    activeThreadId === t.id
                      ? "bg-zinc-800 text-zinc-100 font-medium border border-zinc-700/80"
                      : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate pr-1">
                    <span className="text-xs">{t.mode === "chat" ? "💬" : "📄"}</span>
                    <span className="truncate" title={t.title}>
                      {t.title}
                    </span>
                  </div>

                  <button
                    onClick={(e) => onDeleteThread(e, t.id)}
                    className="p-1 rounded text-zinc-500 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition shrink-0"
                    title="Delete chat thread"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Section 2: Knowledge Base Documents (Chroma DB) */}
        <div className="pt-2 border-t border-zinc-800/80 flex flex-col max-h-48">
          <div className="flex items-center justify-between px-2 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Knowledge Base ({documents.length})
            </span>
          </div>

          {/* Hidden file input — triggered by the Upload PDF button */}
          <input
            type="file"
            ref={fileInputRef}
            accept=".pdf"
            className="hidden"
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition shrink-0 mb-2"
          >
            {uploading ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin text-emerald-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                </svg>
                <span>Indexing...</span>
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                <span>Upload PDF</span>
              </>
            )}
          </button>

          <div className="overflow-y-auto space-y-1 pr-1">
            {documents.length === 0 ? (
              <div className="text-[11px] text-zinc-500 text-center py-1">
                No documents in Chroma DB
              </div>
            ) : (
              documents.map((doc, idx) => (
                <div
                  key={idx}
                  className="p-1.5 rounded-md bg-zinc-800/40 border border-zinc-700/40 text-[11px] flex items-center justify-between group"
                >
                  <div className="truncate pr-1">
                    <div className="text-zinc-300 font-medium truncate" title={doc.filename}>
                      {doc.filename}
                    </div>
                    <div className="text-zinc-500 text-[10px]">
                      {doc.pages}p • {doc.chunks}c
                    </div>
                  </div>

                  <button
                    onClick={() => onDeleteDocument(doc.filename)}
                    className="p-1 text-zinc-500 hover:text-rose-400 opacity-60 group-hover:opacity-100 transition shrink-0"
                    title="Delete document"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Sidebar Footer — server connection status */}
      <div className="p-3 border-t border-zinc-800 flex items-center justify-between text-xs text-zinc-400 shrink-0">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${serverOnline ? "bg-emerald-400" : "bg-rose-500"}`}></span>
          <span>{serverOnline ? "Connected" : "Offline"}</span>
        </div>
        <span className="text-[11px] text-zinc-500 font-mono">SQLite + Chroma</span>
      </div>
    </aside>
  );
}

