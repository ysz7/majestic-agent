import { useState, useRef, useEffect, useCallback } from "react";
import { Send, ChevronRight, ChevronLeft } from "lucide-react";
import { tasksApi } from "@shared/api/client";
import { wsClient } from "@shared/ws/client";
import type { ChatMessage, WsEvent } from "@shared/api/types";
import { cn } from "@shared/lib/cn";

const SLASH_COMMANDS = ["/research", "/briefing", "/pains", "/ideas", "/predict"];

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput]       = useState("");
  const [streaming, setStreaming] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const bottomRef      = useRef<HTMLDivElement>(null);
  const activeTaskRef  = useRef<string | null>(null);
  const inputRef       = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const off = wsClient.on((event: WsEvent) => {
      if (event.type === "token") {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + event.content },
            ];
          }
          return prev;
        });
      } else if (event.type === "done") {
        if (activeTaskRef.current === null || event.task_id === activeTaskRef.current) {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              // The final answer is authoritative; streamed tokens were only
              // the reasoning preamble (everything before FINAL_ANSWER:).
              const content = event.result?.trim() || last.content;
              return [...prev.slice(0, -1), { ...last, content, streaming: false }];
            }
            return prev;
          });
          setStreaming(false);
          activeTaskRef.current = null;
        }
      } else if (event.type === "error") {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content || event.message, streaming: false },
            ];
          }
          return prev;
        });
        setStreaming(false);
        activeTaskRef.current = null;
      }
    });
    return off;
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || streaming) return;
      const msg = text.trim();
      setInput("");
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user",      content: msg },
        { id: crypto.randomUUID(), role: "assistant", content: "", streaming: true },
      ]);
      setStreaming(true);
      try {
        const { task_id } = await tasksApi.submit(msg);
        activeTaskRef.current = task_id;
      } catch {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: "Connection error", streaming: false },
            ];
          }
          return prev;
        });
        setStreaming(false);
      }
    },
    [streaming],
  );

  if (collapsed) {
    return (
      <div className="flex flex-col items-center pt-3 w-7 h-full">
        <button
          onClick={() => setCollapsed(false)}
          className="text-text-faint hover:text-text-sub transition-colors"
          title="Open chat"
        >
          <ChevronLeft size={13} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full rounded-[12px] border border-border bg-node-gradient overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-[9px] border-b border-border flex-shrink-0">
        <div className="flex items-center gap-[6px]">
          <span className="w-[5px] h-[5px] rounded-full bg-text-bright flex-shrink-0" />
          <span className="text-base text-text-sub">Chat</span>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="text-text-faint hover:text-text-sub transition-colors"
          title="Collapse"
        >
          <ChevronRight size={13} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-2 min-h-0">
        {messages.length === 0 && (
          <div className="text-xs text-text-muted-3 text-center mt-6 leading-5">
            Send a message<br />or use a slash command
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={cn(
              "text-xs rounded-[8px] px-[9px] py-[6px] break-words whitespace-pre-wrap",
              m.role === "user"
                ? "bg-bg-selected text-text-sub self-end ml-6 max-w-full"
                : "text-text-dim self-start mr-2 max-w-full",
            )}
          >
            {m.content}
            {m.streaming && !m.content && (
              <span className="inline-block w-[6px] h-[11px] bg-text-muted-2 animate-pulse align-middle ml-[2px]" />
            )}
            {m.streaming && m.content && (
              <span className="inline-block w-[5px] h-[10px] bg-text-muted-3 animate-pulse align-middle ml-[2px]" />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Slash command chips */}
      <div className="flex flex-wrap gap-1 px-3 py-[6px] border-t border-border flex-shrink-0">
        {SLASH_COMMANDS.map((cmd) => (
          <button
            key={cmd}
            onClick={() => {
              setInput(cmd + " ");
              inputRef.current?.focus();
            }}
            className="text-[9px] text-text-muted-2 hover:text-text-dim border border-border hover:border-border-strong rounded-[5px] px-[6px] py-[3px] transition-colors"
          >
            {cmd}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex items-center gap-[6px] px-3 pb-3 flex-shrink-0">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(input);
            }
          }}
          disabled={streaming}
          placeholder="Message agent..."
          className="flex-1 bg-bg-elevated border border-border rounded-[8px] px-[9px] py-[6px] text-xs text-text-sub placeholder:text-text-muted-3 outline-none focus:border-border-strong disabled:opacity-50 transition-colors"
        />
        <button
          onClick={() => void send(input)}
          disabled={!input.trim() || streaming}
          className="w-7 h-7 flex items-center justify-center rounded-[7px] border border-border hover:border-border-strong text-text-faint hover:text-text-sub disabled:opacity-30 transition-colors flex-shrink-0"
        >
          <Send size={11} />
        </button>
      </div>
    </div>
  );
}
