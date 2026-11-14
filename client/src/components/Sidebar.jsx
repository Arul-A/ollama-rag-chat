import React from "react";

/**
 * Sidebar component — displays:
 *  - New Chat button
 *  - Recent chat threads (from SQLite via backend)
 *  - Server connection status footer
 */
export default function Sidebar({
  showSidebar,
  threads,
  activeThreadId,
  serverOnline,
  onNewChat,
  onSelectThread,
  onDeleteThread,
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
          className="flex items-center justify-between w-full px-3 py-2 text-sm font-medium rounded-lg hover:bg-zinc-800 text-zinc-200 border border-zinc-700/60 transition shadow-sm"
        >
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            <span>New chat</span>
          </div>
          <span className="text-xs text-zinc-400">⌘K</span>
        </button>

        {/* Chat Threads History (SQLite) */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-2 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Recent Chats ({threads.length})
            </span>
          </div>

          <div className="overflow-y-auto space-y-1 flex-1 pr-1">
            {threads.length === 0 ? (
              <div className="text-xs text-zinc-500 p-4 text-center">
                No saved chats yet.
              </div>
            ) : (
              threads.map((t) => (
                <div
                  key={t.id}
                  onClick={() => onSelectThread(t)}
                  className={`p-2.5 rounded-xl text-xs flex items-center justify-between cursor-pointer group transition ${
                    activeThreadId === t.id
                      ? "bg-zinc-800 text-zinc-100 font-medium border border-zinc-700/80 shadow-sm"
                      : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate pr-1">
                    <span className="text-xs shrink-0">{t.mode === "chat" ? "💬" : "📄"}</span>
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

