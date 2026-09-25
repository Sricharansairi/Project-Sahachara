import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles,
  ArrowUp,
  Mic,
  Plus,
  Copy,
  Check,
  Volume2,
  Paperclip,
  Eye,
} from "lucide-react";
import {
  UndoActionCard,
  MeetingDossierCard,
  GhostRadarCard,
  ClipboardAugmenterCard,
} from "./ActionCards";
import { useMitraStore } from "../store/useMitraStore";

export interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

interface GeminiChatViewProps {
  onSwitchToVoice: () => void;
}

export const GeminiChatView: React.FC<GeminiChatViewProps> = ({
  onSwitchToVoice,
}) => {
  const {
    activeAction,
    setActiveAction,
    dossier,
    setDossier,
    commitments,
    clipboardData,
    setClipboardData,
  } = useMitraStore();

  const [inputPrompt, setInputPrompt] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);

  // Initial seed messages reflecting Gemini desktop experience
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "msg_01",
      sender: "user",
      content: "Draft a follow-up email to Sarah Chen about our Q3 review.",
      timestamp: "10:14 AM",
    },
    {
      id: "msg_02",
      sender: "assistant",
      content:
        "I've drafted the reply for Sarah Chen confirming our Friday sync at 3:00 PM and attached the Q3 project milestone review. You can review the draft below or hit Ctrl+Z to undo.",
      timestamp: "10:14 AM",
    },
  ]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeAction, dossier, commitments]);

  const handleSendMessage = () => {
    if (!inputPrompt.trim()) return;

    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}`,
      sender: "user",
      content: inputPrompt,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt("");

    // Simulate streaming assistant response
    setTimeout(() => {
      const assistantMsg: ChatMessage = {
        id: `msg_${Date.now() + 1}`,
        sender: "assistant",
        content: `I've processed "${userMsg.content}". Checking relevant project documents in Drive and local workspace...`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    }, 450);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="w-full flex flex-col h-[460px] text-[#f1f3f4] relative">
      {/* ─── 1. CONVERSATION STREAM (SCROLLABLE) ─────────────────────── */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3.5 custom-scrollbar">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${
              msg.sender === "user" ? "items-end" : "items-start"
            }`}
          >
            {msg.sender === "user" ? (
              /* User Message Bubble */
              <div className="max-w-[85%] bg-[#282a2c] text-[#f1f3f4] px-3.5 py-2.5 rounded-2xl rounded-tr-sm text-xs leading-relaxed border border-white/[0.04]">
                {msg.content}
              </div>
            ) : (
              /* Assistant Message Block */
              <div className="w-full space-y-1.5">
                <div className="flex items-center gap-1.5 text-[11px] text-[#9aa0a6] font-medium">
                  <Sparkles size={13} className="text-[#8ab4f8]" />
                  <span>Mitra</span>
                  <span className="text-[10px] text-[#5f6368]">• {msg.timestamp}</span>
                </div>
                <div className="text-xs text-[#f1f3f4] leading-relaxed pl-5 whitespace-pre-wrap">
                  {msg.content}
                </div>
                {/* Action Toolbar */}
                <div className="flex items-center gap-2 pl-5 pt-1 text-[#9aa0a6]">
                  <button
                    onClick={() => handleCopy(msg.content, msg.id)}
                    className="p-1 hover:text-white rounded hover:bg-white/[0.05] transition-colors"
                    title="Copy response"
                  >
                    {copiedId === msg.id ? (
                      <Check size={12} className="text-[#34a853]" />
                    ) : (
                      <Copy size={12} />
                    )}
                  </button>
                  <button
                    className="p-1 hover:text-white rounded hover:bg-white/[0.05] transition-colors"
                    title="Listen to response"
                  >
                    <Volume2 size={12} />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* ─── EMBEDDED ACTION CARDS / EXTENSION CHIPS ─────────────────── */}
        <div className="w-full space-y-2 pt-1">
          <AnimatePresence>
            {activeAction && (
              <UndoActionCard
                key={activeAction.actionId}
                action={activeAction}
                onApprove={() => {
                  setActiveAction({
                    ...activeAction,
                    status: "in_undo_window",
                    expiresAt: Date.now() + 10000,
                  });
                }}
                onReject={() => setActiveAction(null)}
              />
            )}

            {dossier && (
              <MeetingDossierCard
                key={dossier.eventId}
                dossier={dossier}
                onDismiss={() => setDossier(null)}
              />
            )}

            {commitments.map((com) => (
              <GhostRadarCard key={com.id} commitment={com} />
            ))}

            {clipboardData && (
              <ClipboardAugmenterCard
                key="clipboard-card"
                data={clipboardData}
                onFormatTable={() => setClipboardData(null)}
                onSummarize={() => setClipboardData(null)}
                onDismiss={() => setClipboardData(null)}
              />
            )}
          </AnimatePresence>
        </div>

        <div ref={chatBottomRef} />
      </div>

      {/* ─── 2. FLOATING PROMPT INPUT BAR (DESKTOP GEMINI STYLE) ────────── */}
      <div className="p-2 border-t border-white/[0.06] bg-[#000000] relative">
        {/* Attachment Flyout */}
        <AnimatePresence>
          {showAttachMenu && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              className="absolute left-3 bottom-14 z-20 w-44 p-1 bg-[#1e1f20] border border-white/[0.1] rounded-2xl shadow-xl flex flex-col gap-0.5 text-xs text-[#9aa0a6]"
            >
              <button
                onClick={() => setShowAttachMenu(false)}
                className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/[0.06] hover:text-white flex items-center gap-2"
              >
                <Eye size={13} className="text-[#8ab4f8]" />
                <span>Glance at Screen</span>
              </button>
              <button
                onClick={() => setShowAttachMenu(false)}
                className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-white/[0.06] hover:text-white flex items-center gap-2"
              >
                <Paperclip size={13} className="text-[#8ab4f8]" />
                <span>Add Local File</span>
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="w-full bg-[#1e1f20] border border-white/[0.08] focus-within:border-white/[0.18] rounded-full px-3 py-1.5 flex items-center gap-2 transition-all shadow-sm">
          {/* Plus / Attachment button */}
          <button
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className="w-7 h-7 rounded-full text-[#9aa0a6] hover:text-white hover:bg-white/[0.06] flex items-center justify-center transition-colors flex-shrink-0"
            title="Attach or Glance"
          >
            <Plus size={15} />
          </button>

          {/* Prompt Textarea */}
          <textarea
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Mitra..."
            rows={1}
            className="flex-1 bg-transparent text-xs text-[#f1f3f4] placeholder-[#5f6368] focus:outline-none resize-none max-h-20 py-1 font-sans"
          />

          {/* Mic Button — Switches to Voice Live Mode */}
          <button
            onClick={onSwitchToVoice}
            className="w-7 h-7 rounded-full text-[#9aa0a6] hover:text-[#8ab4f8] hover:bg-white/[0.06] flex items-center justify-center transition-colors flex-shrink-0"
            title="Start Voice Live Conversation"
          >
            <Mic size={15} />
          </button>

          {/* Send Button */}
          <button
            onClick={handleSendMessage}
            disabled={!inputPrompt.trim()}
            className={`w-7 h-7 rounded-full flex items-center justify-center transition-all flex-shrink-0 ${
              inputPrompt.trim()
                ? "bg-[#8ab4f8] text-[#000000] hover:bg-[#8ab4f8]/90"
                : "bg-white/[0.04] text-[#5f6368] cursor-not-allowed"
            }`}
            title="Send Message"
          >
            <ArrowUp size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};
