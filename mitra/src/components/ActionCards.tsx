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
// 1. Tier-1 Approval & 10-Second Undo Action Card
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
        return <Mail size={16} className="text-sky-400" />;
      case "create_calendar":
        return <Calendar size={16} className="text-indigo-400" />;
      case "trigger_n8n":
        return <Zap size={16} className="text-amber-400" />;
      default:
        return <CheckCheck size={16} className="text-emerald-400" />;
    }
  };

  const progressPercent = Math.max(0, Math.min(100, (secondsRemaining / 10.0) * 100));

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 420, damping: 28 }}
      className="w-full bg-neutral-950/90 border border-white/10 rounded-2xl p-4 shadow-2xl backdrop-blur-2xl relative overflow-hidden"
    >
      {/* 10-Second Undo Progress Bar */}
      {action.status === "in_undo_window" && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-white/5">
          <motion.div
            className="h-full bg-gradient-to-r from-sky-400 via-indigo-500 to-purple-500"
            style={{ width: `${progressPercent}%` }}
            transition={{ ease: "linear", duration: 0.05 }}
          />
        </div>
      )}

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
            {getActionIcon()}
          </div>
          <div>
            <div className="text-xs font-semibold text-white tracking-wide flex items-center gap-2">
              {action.title}
              {action.status === "in_undo_window" && (
                <span className="text-[10px] font-mono text-neutral-400 bg-white/5 px-1.5 py-0.5 rounded border border-white/5">
                  {secondsRemaining.toFixed(1)}s
                </span>
              )}
            </div>
            <div className="text-[11px] text-neutral-400 mt-0.5 line-clamp-2">
              {action.description}
            </div>
          </div>
        </div>

        {/* Status / Buttons */}
        {action.status === "in_undo_window" && (
          <button
            onClick={() => rollbackAction(action.actionId)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/15 active:bg-white/20 border border-white/15 rounded-xl text-xs font-medium text-white transition-all"
            title="Press Ctrl+Z to undo"
          >
            <Undo2 size={13} />
            <span>Undo</span>
          </button>
        )}

        {action.status === "pending_approval" && (
          <div className="flex items-center gap-1.5">
            <button
              onClick={onReject}
              className="w-7 h-7 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 flex items-center justify-center transition-all"
            >
              <X size={14} />
            </button>
            <button
              onClick={onApprove}
              className="w-7 h-7 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 flex items-center justify-center transition-all"
            >
              <Check size={14} />
            </button>
          </div>
        )}

        {action.status === "rolled_back" && (
          <div className="flex items-center gap-1.5 text-xs text-neutral-400 font-medium">
            <Check size={13} className="text-emerald-400" />
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
      initial={{ opacity: 0, y: 12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.96 }}
      className="w-full bg-neutral-950/90 border border-white/10 rounded-2xl p-4 shadow-2xl backdrop-blur-2xl"
    >
      <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Calendar size={15} className="text-indigo-400" />
          <span className="text-xs font-semibold text-white tracking-wide">
            Pre-Meeting Briefing
          </span>
          <span className="text-[10px] text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/20">
            In 2 mins
          </span>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-neutral-500 hover:text-white transition-colors"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="text-xs font-medium text-neutral-200 mb-2">
        {dossier.title}
      </div>

      <div className="flex flex-wrap gap-1 mb-3">
        {dossier.attendees.map((att, idx) => (
          <span
            key={idx}
            className="text-[10px] text-neutral-400 bg-white/5 px-2 py-0.5 rounded-md border border-white/5"
          >
            {att}
          </span>
        ))}
      </div>

      <div className="space-y-1.5">
        {dossier.bullets.map((bullet, idx) => (
          <div key={idx} className="flex items-start gap-2 text-[11px] text-neutral-300">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1 flex-shrink-0" />
            <span className="leading-snug">{bullet.replace(/^[-*•]\s*/, "")}</span>
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
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.97 }}
      className="w-full bg-neutral-950/85 border border-white/10 rounded-2xl p-3.5 shadow-xl backdrop-blur-xl"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-md uppercase border ${
              isOutbound
                ? "bg-sky-500/10 text-sky-400 border-sky-500/20"
                : "bg-amber-500/10 text-amber-400 border-amber-500/20"
            }`}
          >
            {isOutbound ? "Outbound" : "Inbound"}
          </span>
          <span className="text-[11px] font-medium text-neutral-300 truncate max-w-[160px]">
            {commitment.party}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => snoozeCommitment(commitment.id)}
            className="flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 rounded-lg text-[10px] text-neutral-400 hover:text-white transition-colors border border-white/5"
            title="Snooze for 2 hours"
          >
            <Clock size={11} />
            <span>2h</span>
          </button>
          <button
            onClick={() => resolveCommitment(commitment.id)}
            className="flex items-center gap-1 px-2 py-1 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-lg text-[10px] text-emerald-400 transition-colors border border-emerald-500/20"
            title="Mark as done"
          >
            <Check size={11} />
            <span>Done</span>
          </button>
        </div>
      </div>

      <div className="text-xs text-neutral-200 leading-snug">
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
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.97 }}
      className="w-full bg-neutral-950/90 border border-white/10 rounded-2xl p-3.5 shadow-2xl backdrop-blur-2xl"
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold text-neutral-400 bg-white/5 px-2 py-0.5 rounded uppercase border border-white/5">
            Clipboard: {data.type}
          </span>
        </div>
        <button onClick={onDismiss} className="text-neutral-500 hover:text-white transition-colors">
          <X size={13} />
        </button>
      </div>

      <div className="text-[11px] text-neutral-300 truncate mb-3 font-mono bg-white/[0.03] p-1.5 rounded-lg border border-white/5">
        {data.rawText.slice(0, 80)}...
      </div>

      <div className="flex items-center gap-2">
        {data.type === "table" && (
          <button
            onClick={onFormatTable}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 rounded-xl text-xs font-medium text-sky-300 transition-all"
          >
            <FileSpreadsheet size={13} />
            <span>Format Table</span>
          </button>
        )}
        <button
          onClick={onSummarize}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-white/10 hover:bg-white/15 border border-white/10 rounded-xl text-xs font-medium text-neutral-200 transition-all"
        >
          <FileText size={13} />
          <span>Summarize</span>
        </button>
      </div>
    </motion.div>
  );
};
