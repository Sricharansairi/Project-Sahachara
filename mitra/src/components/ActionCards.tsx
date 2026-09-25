import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Mail,
  Calendar,
  Zap,
  Check,
  X,
  Undo2,
  Clock,
  CheckCheck,
  FileSpreadsheet,
  FileText,
} from "lucide-react";
import {
  ActionCardData,
  CommitmentData,
  MeetingDossierData,
  ClipboardData,
  useMitraStore,
} from "../store/useMitraStore";

// ─────────────────────────────────────────────────────────────────────────────
// 1. Tier-1 Approval & 10-Second Undo Action Card (Google Gemini Style)
// ─────────────────────────────────────────────────────────────────────────────

interface UndoCardProps {
  action: ActionCardData;
  onApprove?: () => void;
  onReject?: () => void;
}

export const UndoActionCard: React.FC<UndoCardProps> = ({
  action,
  onApprove,
  onReject,
}) => {
  const rollbackAction = useMitraStore((s) => s.rollbackAction);
  const [secondsRemaining, setSecondsRemaining] = useState<number>(10.0);

  useEffect(() => {
    if (action.status !== "in_undo_window") return;

    const interval = setInterval(() => {
      const remaining = Math.max(0, (action.expiresAt - Date.now()) / 1000);
      setSecondsRemaining(remaining);
      if (remaining <= 0) {
        clearInterval(interval);
      }
    }, 50);

    return () => clearInterval(interval);
  }, [action.expiresAt, action.status]);

  const getActionIcon = () => {
    switch (action.actionType) {
      case "draft_email":
        return <Mail size={15} className="text-[#8ab4f8]" />;
      case "create_calendar":
        return <Calendar size={15} className="text-[#8ab4f8]" />;
      case "trigger_n8n":
        return <Zap size={15} className="text-[#fdd663]" />;
      default:
        return <CheckCheck size={15} className="text-[#34a853]" />;
    }
  };

  const progressPercent = Math.max(0, Math.min(100, (secondsRemaining / 10.0) * 100));

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="w-full bg-[#1e1f20] border border-white/[0.08] rounded-2xl p-3.5 shadow-md relative overflow-hidden"
    >
      {/* 10-Second Undo Flat Minimal Progress Bar */}
      {action.status === "in_undo_window" && (
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-white/[0.06]">
          <motion.div
            className="h-full bg-[#8ab4f8]"
            style={{ width: `${progressPercent}%` }}
            transition={{ ease: "linear", duration: 0.05 }}
          />
        </div>
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center flex-shrink-0">
            {getActionIcon()}
          </div>
          <div>
            <div className="text-xs font-medium text-[#f1f3f4] flex items-center gap-2">
              <span>{action.title}</span>
              {action.status === "in_undo_window" && (
                <span className="text-[10px] font-mono text-[#9aa0a6] bg-white/[0.04] px-1.5 py-0.2 rounded border border-white/[0.05]">
                  {secondsRemaining.toFixed(1)}s
                </span>
              )}
            </div>
            <div className="text-[11px] text-[#9aa0a6] mt-0.5 line-clamp-2 leading-relaxed">
              {action.description}
            </div>
          </div>
        </div>

        {/* Status / Buttons */}
        {action.status === "in_undo_window" && (
          <button
            onClick={() => rollbackAction(action.actionId)}
            className="flex items-center gap-1.5 px-3 py-1 bg-white/[0.08] hover:bg-white/[0.12] active:bg-white/[0.16] border border-white/[0.1] rounded-full text-xs font-medium text-[#f1f3f4] transition-colors flex-shrink-0"
            title="Press Ctrl+Z to undo"
          >
            <Undo2 size={12} className="text-[#8ab4f8]" />
            <span>Undo</span>
          </button>
        )}

        {action.status === "pending_approval" && (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              onClick={onReject}
              className="w-7 h-7 rounded-full bg-white/[0.06] hover:bg-rose-500/20 text-[#9aa0a6] hover:text-rose-400 border border-white/[0.08] flex items-center justify-center transition-colors"
            >
              <X size={13} />
            </button>
            <button
              onClick={onApprove}
              className="w-7 h-7 rounded-full bg-[#8ab4f8]/15 hover:bg-[#8ab4f8]/25 text-[#8ab4f8] border border-[#8ab4f8]/30 flex items-center justify-center transition-colors"
            >
              <Check size={13} />
            </button>
          </div>
        )}

        {action.status === "rolled_back" && (
          <div className="flex items-center gap-1 text-xs text-[#9aa0a6] font-medium flex-shrink-0">
            <Check size={13} className="text-[#34a853]" />
            <span>Undone</span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// 2. Pre-Meeting Executive Dossier Card
// ─────────────────────────────────────────────────────────────────────────────

interface DossierCardProps {
  dossier: MeetingDossierData;
  onDismiss?: () => void;
}

export const MeetingDossierCard: React.FC<DossierCardProps> = ({
  dossier,
  onDismiss,
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      className="w-full bg-[#1e1f20] border border-white/[0.08] rounded-2xl p-3.5 shadow-md"
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Calendar size={14} className="text-[#8ab4f8]" />
          <span className="text-xs font-medium text-[#f1f3f4]">
            Pre-Meeting Briefing
          </span>
          <span className="text-[10px] text-[#8ab4f8] bg-[#8ab4f8]/10 px-2 py-0.5 rounded-full border border-[#8ab4f8]/20">
            In 2 mins
          </span>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-[#9aa0a6] hover:text-[#f1f3f4] transition-colors"
          >
            <X size={13} />
          </button>
        )}
      </div>

      <div className="text-xs font-medium text-[#f1f3f4] mb-2">
        {dossier.title}
      </div>

      <div className="flex flex-wrap gap-1 mb-2.5">
        {dossier.attendees.map((att, idx) => (
          <span
            key={idx}
            className="text-[10px] text-[#9aa0a6] bg-white/[0.04] px-2 py-0.5 rounded-md border border-white/[0.05]"
          >
            {att}
          </span>
        ))}
      </div>

      <div className="space-y-1.5">
        {dossier.bullets.map((bullet, idx) => (
          <div key={idx} className="flex items-start gap-2 text-[11px] text-[#bdc1c6]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#8ab4f8] mt-1.5 flex-shrink-0" />
            <span className="leading-relaxed">{bullet.replace(/^[-*•]\s*/, "")}</span>
          </div>
        ))}
      </div>
    </motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// 3. Ghost Radar Commitment Card
// ─────────────────────────────────────────────────────────────────────────────

interface CommitmentCardProps {
  commitment: CommitmentData;
}

export const GhostRadarCard: React.FC<CommitmentCardProps> = ({ commitment }) => {
  const resolveCommitment = useMitraStore((s) => s.resolveCommitment);
  const snoozeCommitment = useMitraStore((s) => s.snoozeCommitment);

  const isOutbound = commitment.direction === "outbound";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      className="w-full bg-[#1e1f20] border border-white/[0.08] rounded-2xl p-3.5 shadow-md"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] font-medium tracking-wide px-2 py-0.5 rounded-full border ${
              isOutbound
                ? "bg-[#8ab4f8]/10 text-[#8ab4f8] border-[#8ab4f8]/20"
                : "bg-[#fdd663]/10 text-[#fdd663] border-[#fdd663]/20"
            }`}
          >
            {isOutbound ? "Outbound" : "Inbound"}
          </span>
          <span className="text-[11px] text-[#9aa0a6] truncate max-w-[170px]">
            {commitment.party}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => snoozeCommitment(commitment.id)}
            className="flex items-center gap-1 px-2 py-0.5 bg-white/[0.04] hover:bg-white/[0.08] rounded-full text-[10px] text-[#9aa0a6] hover:text-[#f1f3f4] transition-colors border border-white/[0.06]"
            title="Snooze for 2 hours"
          >
            <Clock size={10} />
            <span>2h</span>
          </button>
          <button
            onClick={() => resolveCommitment(commitment.id)}
            className="flex items-center gap-1 px-2 py-0.5 bg-[#34a853]/10 hover:bg-[#34a853]/20 rounded-full text-[10px] text-[#34a853] transition-colors border border-[#34a853]/20"
            title="Mark as done"
          >
            <Check size={10} />
            <span>Done</span>
          </button>
        </div>
      </div>

      <div className="text-xs text-[#f1f3f4] leading-relaxed">
        {commitment.description}
      </div>
    </motion.div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// 4. Intelligent Clipboard Augmenter Card
// ─────────────────────────────────────────────────────────────────────────────

interface ClipboardCardProps {
  data: ClipboardData;
  onFormatTable: () => void;
  onSummarize: () => void;
  onDismiss: () => void;
}

export const ClipboardAugmenterCard: React.FC<ClipboardCardProps> = ({
  data,
  onFormatTable,
  onSummarize,
  onDismiss,
}) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.98 }}
      className="w-full bg-[#1e1f20] border border-white/[0.08] rounded-2xl p-3.5 shadow-md"
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium text-[#9aa0a6] bg-white/[0.04] px-2 py-0.5 rounded-full border border-white/[0.06]">
            Clipboard: {data.type}
          </span>
        </div>
        <button onClick={onDismiss} className="text-[#9aa0a6] hover:text-[#f1f3f4] transition-colors">
          <X size={13} />
        </button>
      </div>

      <div className="text-[11px] text-[#bdc1c6] truncate mb-2.5 font-mono bg-black/40 p-2 rounded-lg border border-white/[0.05]">
        {data.rawText.slice(0, 80)}...
      </div>

      <div className="flex items-center gap-2">
        {data.type === "table" && (
          <button
            onClick={onFormatTable}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-[#8ab4f8]/10 hover:bg-[#8ab4f8]/20 border border-[#8ab4f8]/25 rounded-full text-xs font-medium text-[#8ab4f8] transition-colors"
          >
            <FileSpreadsheet size={13} />
            <span>Format Table</span>
          </button>
        )}
        <button
          onClick={onSummarize}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] rounded-full text-xs font-medium text-[#f1f3f4] transition-colors"
        >
          <FileText size={13} />
          <span>Summarize</span>
        </button>
      </div>
    </motion.div>
  );
};
