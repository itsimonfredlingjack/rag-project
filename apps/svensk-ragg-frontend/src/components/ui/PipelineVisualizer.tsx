import React from "react";
import { useAppStore } from "../../stores/useAppStore";
import type { PipelineStage } from "../../stores/useAppStore";
import { STEP_TIMER_MS } from "../../constants";
import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Brain,
  RefreshCw,
  Database,
  Sparkles,
  ShieldCheck,
  ChevronDown,
  Check,
  XCircle,
  Loader2,
  Filter,
  Lightbulb,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";

const stages: { id: PipelineStage; label: string; icon: LucideIcon }[] = [
  { id: "query_classification", label: "Classify", icon: Brain },
  { id: "decontextualization", label: "Decontext", icon: RefreshCw },
  { id: "retrieval", label: "Retrieval", icon: Database },
  { id: "grading", label: "Grade", icon: Filter },
  { id: "self_reflection", label: "Reflect", icon: Lightbulb },
  { id: "generation", label: "Generate", icon: Sparkles },
  { id: "guardrail_validation", label: "Validate", icon: ShieldCheck },
];

const stageMessages: Record<PipelineStage, string> = {
  idle: "",
  query_classification: "Classify: analyzing intent…",
  decontextualization: "Decontext: rewriting query…",
  retrieval: "Retrieval: fetching sources…",
  grading: "Grade: verifying relevance…",
  self_reflection: "Reflect: planning response…",
  generation: "Generate: composing answer…",
  guardrail_validation: "Validate: checking output…",
};

const runStateLabel: Record<"running" | "complete" | "error", string> = {
  running: "RUNNING",
  complete: "COMPLETE",
  error: "ERROR",
};

export interface PipelineVisualizerProps {
  isActive?: boolean;
  searchStage?: string;
  pipelineStage?: string;
  pipelineLog?: Array<{ ts: number; stage: string; message: string }>;
  selectedPipelineStage?: string | null;
  isPipelineDrawerOpen?: boolean;
  error?: string | null;
  onSelectStage?: (stage: string) => void;
  onToggleDrawer?: (force?: boolean) => void;
}

export const PipelineVisualizer: React.FC<PipelineVisualizerProps> = (
  props,
) => {
  const queries = useAppStore((state) => state.queries);
  const activeQueryId = useAppStore((state) => state.activeQueryId);
  const storeSetSelectedPipelineStage = useAppStore(
    (state) => state.setSelectedPipelineStage,
  );
  const storeTogglePipelineDrawer = useAppStore(
    (state) => state.togglePipelineDrawer,
  );
  const updateQueryResult = useAppStore((state) => state.updateQueryResult);

  const activeFromStore = activeQueryId
    ? queries.find((q) => q.id === activeQueryId)
    : null;

  const hasProps =
    props.searchStage !== undefined || props.pipelineStage !== undefined;
  const pipelineStage =
    (hasProps ? props.pipelineStage : activeFromStore?.pipelineStage) ?? "idle";
  const searchStage =
    (hasProps ? props.searchStage : activeFromStore?.searchStage) ?? "idle";
  const error = hasProps
    ? (props.error ?? null)
    : (activeFromStore?.error ?? null);
  const selectedPipelineStage = hasProps
    ? (props.selectedPipelineStage ?? "query_classification")
    : (activeFromStore?.selectedPipelineStage ?? "query_classification");
  const isPipelineDrawerOpen = hasProps
    ? (props.isPipelineDrawerOpen ?? false)
    : (activeFromStore?.isPipelineDrawerOpen ?? false);
  const pipelineLog = useMemo(
    () => (hasProps ? (props.pipelineLog ?? []) : (activeFromStore?.pipelineLog ?? [])),
    [activeFromStore?.pipelineLog, hasProps, props.pipelineLog],
  );

  const isActive = props.isActive !== false;
  const setSelectedPipelineStage = useCallback(
    (stage: string) => {
      if (props.onSelectStage && hasProps) {
        props.onSelectStage(stage);
        return;
      }
      if (activeQueryId) updateQueryResult(activeQueryId, { selectedPipelineStage: stage });
      else storeSetSelectedPipelineStage(stage as PipelineStage);
    },
    [
      activeQueryId,
      hasProps,
      props,
      storeSetSelectedPipelineStage,
      updateQueryResult,
    ],
  );
  const togglePipelineDrawer = useCallback(
    (force?: boolean) => {
      if (props.onToggleDrawer && hasProps) {
        props.onToggleDrawer(force);
        return;
      }
      if (activeQueryId && activeFromStore)
        updateQueryResult(activeQueryId, {
          isPipelineDrawerOpen:
            typeof force === "boolean" ? force : !activeFromStore.isPipelineDrawerOpen,
        });
      else storeTogglePipelineDrawer(force);
    },
    [activeFromStore, activeQueryId, hasProps, props, storeTogglePipelineDrawer, updateQueryResult],
  );

  const isIdle = searchStage === "idle";

  // Determine active index for progress bar
  const runningStage: PipelineStage =
    pipelineStage === "idle"
      ? "guardrail_validation"
      : (pipelineStage as PipelineStage);
  const activeIndex = stages.findIndex((s) => s.id === runningStage);

  const selectedIndex = stages.findIndex((s) => s.id === selectedPipelineStage);
  const progressPct =
    selectedIndex >= 0
      ? `${(selectedIndex / (stages.length - 1)) * 100}%`
      : "0%";

  const runState = useMemo<"running" | "complete" | "error">(() => {
    if (!isActive) return "complete";
    if (searchStage === "error") return "error";
    if (searchStage === "complete") return "complete";
    return "running";
  }, [searchStage, isActive]);

  // Display smoothing: if backend jumps quickly, we still animate through steps so the process is legible.
  const [displayIndex, setDisplayIndex] = useState(() =>
    !isActive ? stages.length - 1 : Math.max(0, activeIndex),
  );
  const stepTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
    if (!isActive) {
      stepTimerRef.current = setTimeout(() => setDisplayIndex(stages.length - 1), 0);
      return () => {
        if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
      };
    }
    if (runState === "complete") {
      stepTimerRef.current = setTimeout(() => setDisplayIndex(stages.length - 1), 0);
      return () => {
        if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
      };
    }

    // On error, snap to current (and mark failed visually).
    if (runState === "error") {
      stepTimerRef.current = setTimeout(() => setDisplayIndex(Math.max(0, activeIndex)), 0);
      return () => {
        if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
      };
    }

    // Running: step forward gradually if we need to catch up.
    const target = Math.max(0, activeIndex);
    if (displayIndex > target) {
      stepTimerRef.current = setTimeout(() => setDisplayIndex(target), 0);
      return () => {
        if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
      };
    }

    if (displayIndex < target) {
      stepTimerRef.current = setTimeout(() => {
        setDisplayIndex((prev) => Math.min(prev + 1, target));
      }, STEP_TIMER_MS);
    }

    return () => {
      if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
    };
  }, [isActive, activeIndex, runState, displayIndex]);

  const displayStage =
    stages[Math.max(0, Math.min(displayIndex, stages.length - 1))]?.id;

  // Keep selected stage following the active stage unless the drawer is open (user exploring).
  useEffect(() => {
    if (isPipelineDrawerOpen) return;
    if (displayStage && selectedPipelineStage !== displayStage) {
      setSelectedPipelineStage(displayStage);
    }
  }, [
    isPipelineDrawerOpen,
    displayStage,
    selectedPipelineStage,
    setSelectedPipelineStage,
  ]);

  const visibleLog = useMemo(() => {
    return pipelineLog
      .filter((l) => l.stage === selectedPipelineStage)
      .slice(-5);
  }, [pipelineLog, selectedPipelineStage]);

  const effectiveStageForStatus = displayStage ?? runningStage;

  const statusText =
    searchStage === "error"
      ? `Error: ${error || "Unknown error"}`
      : searchStage === "complete"
        ? "Complete: answer ready"
        : stageMessages[effectiveStageForStatus];

  const percent = Math.round((displayIndex / (stages.length - 1)) * 100);

  if (isIdle) return null;

  return (
    <div
      className={clsx(
        "w-full rounded-2xl border glass-panel shadow-[0_12px_40px_rgba(0,0,0,0.5)] px-7 py-6 border-white/[0.035]"
      )}
    >
      {/* Small header row */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
          PIPELINE PIPELINE_RUN
        </div>
        <div
          className={clsx(
            "text-[10px] font-mono uppercase tracking-wider",
            runState === "error"
              ? "text-red-400"
              : runState === "complete"
                ? "text-accent-primary"
                : "text-slate-400"
          )}
        >
          {runStateLabel[runState]} • {percent}%
        </div>
      </div>

      {/* Top row: stages */}
      <div className="relative mb-6">
        {/* Connector baseline */}
        <div
          className={clsx(
            "absolute left-0 top-[20px] w-full h-[2px] rounded-full pointer-events-none -z-10",
            runState === "error" ? "bg-red-500/10" : "bg-white/[0.03]"
          )}
        />

        {/* Active Progress Bar */}
        <motion.div
          className={clsx(
            "absolute left-0 top-[20px] h-[2px] rounded-full pointer-events-none -z-10",
            runState === "error" ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" : "bg-accent-primary shadow-[0_0_8px_rgba(0,240,244,0.5)]"
          )}
          initial={{ width: "0%" }}
          animate={{
            width:
              displayIndex >= 0
                ? `${(displayIndex / (stages.length - 1)) * 100}%`
                : "0%",
          }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        />

        {/* Progress glow (subtle, material-like) */}
        <motion.div
          aria-hidden="true"
          className={clsx(
            "absolute left-0 top-[20px] h-[10px] -translate-y-1/2 blur-md rounded-full pointer-events-none -z-10",
            runState === "error" ? "bg-red-500/20" : "bg-accent-primary/20"
          )}
          initial={{ width: "0%" }}
          animate={{
            width:
              displayIndex >= 0
                ? `${(displayIndex / (stages.length - 1)) * 100}%`
                : "0%",
          }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        />

        {/* Energy flow shimmer (only while running) */}
        {runState === "running" && (
          <motion.div
            aria-hidden="true"
            className="absolute left-0 top-[20px] h-[2px] rounded-full overflow-hidden pointer-events-none -z-10"
            style={{
              width:
                displayIndex >= 0
                  ? `${(displayIndex / (stages.length - 1)) * 100}%`
                  : "0%",
            }}
          >
            <motion.div
              className="h-full w-full"
              style={{
                backgroundImage:
                  "linear-gradient(90deg, rgba(0,240,244,0) 0%, rgba(0,240,244,0.6) 45%, rgba(0,240,244,0) 80%)",
                backgroundSize: "200% 100%",
              }}
              animate={{ backgroundPositionX: ["0%", "200%"] }}
              transition={{ repeat: Infinity, duration: 1.1, ease: "linear" }}
            />
          </motion.div>
        )}

        {/* Energy pulse (only while running) */}
        {runState === "running" && displayIndex >= 0 && (
          <>
            <motion.div
              aria-hidden="true"
              className="absolute top-[20px] -translate-y-1/2 w-6 h-6 rounded-full bg-accent-primary/10 blur-sm pointer-events-none"
              style={{
                left: `calc(${(displayIndex / (stages.length - 1)) * 100}% - 12px)`,
              }}
              animate={{ opacity: [0.2, 0.5, 0.2] }}
              transition={{
                repeat: Infinity,
                duration: 1.15,
                ease: "easeInOut",
              }}
            />
            <motion.div
              className="absolute top-[20px] -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-accent-primary shadow-[0_0_8px_rgba(0,240,244,0.6)] pointer-events-none"
              style={{
                left: `calc(${(displayIndex / (stages.length - 1)) * 100}% - 5px)`,
              }}
              animate={{
                scale: [1, 1.25, 1],
                opacity: [0.7, 1, 0.7],
              }}
              transition={{
                repeat: Infinity,
                duration: 1.05,
                ease: "easeInOut",
              }}
            />
          </>
        )}

        <div className="flex items-start justify-between gap-2">
          {stages.map((stage, index) => {
            const isBefore = displayIndex >= 0 && index < displayIndex;
            const isCurrent = index === displayIndex;
            const isSelected = stage.id === selectedPipelineStage;
            const Icon = stage.icon;

            const stepState: "pending" | "active" | "done" | "failed" =
              runState === "complete"
                ? "done"
                : runState === "error"
                  ? isCurrent
                    ? "failed"
                    : isBefore
                      ? "done"
                      : "pending"
                  : isCurrent
                    ? "active"
                    : isBefore
                      ? "done"
                      : "pending";

            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => {
                  setSelectedPipelineStage(stage.id);
                  togglePipelineDrawer(true);
                }}
                className={clsx(
                  "group flex flex-col items-center gap-1.5 text-center select-none cursor-pointer",
                  "focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-primary/30 rounded-xl px-0.5"
                )}
              >
                <motion.div
                  className={clsx(
                    "relative rounded-full flex items-center justify-center border",
                    "transition-all duration-200",
                    stepState === "active"
                      ? "bg-[#0E151A] border-accent-primary ring-2 ring-accent-primary/10 shadow-[0_0_12px_rgba(0,240,244,0.15)] text-accent-primary"
                      : stepState === "done"
                        ? "bg-[#0E1217] border-white/10 text-slate-300"
                        : stepState === "failed"
                          ? "bg-[#1D1217] border-red-500/50 ring-2 ring-red-500/10 text-red-400"
                          : "bg-transparent border-white/5 text-slate-600",
                    isSelected && "border-white/30"
                  )}
                  style={{
                    width: 40,
                    height: 40,
                  }}
                  animate={
                    stepState === "active"
                      ? { scale: [1, 1.05, 1] }
                      : { scale: 1 }
                  }
                  transition={{
                    repeat: stepState === "active" ? Infinity : 0,
                    duration: 1.8,
                  }}
                >
                  <Icon
                    size={16}
                    className={clsx(
                      stepState === "pending" && "opacity-40",
                      stepState === "done" && "opacity-80"
                    )}
                    strokeWidth={1.5}
                  />

                  {stepState === "done" && (
                    <span className="absolute -right-1 -top-1 w-[16px] h-[16px] rounded-full bg-[#0E1217] border border-white/10 flex items-center justify-center shadow-[0_2px_5px_rgba(0,0,0,0.3)]">
                      <Check
                        className="w-3 h-3 text-accent-primary"
                        strokeWidth={2.5}
                      />
                    </span>
                  )}

                  {stepState === "failed" && (
                    <span className="absolute -right-1 -top-1 w-[16px] h-[16px] rounded-full bg-[#1D1217] border border-red-500/30 flex items-center justify-center shadow-[0_2px_5px_rgba(0,0,0,0.3)]">
                      <XCircle
                        className="w-3 h-3 text-red-500"
                        strokeWidth={2.5}
                      />
                    </span>
                  )}
                </motion.div>
                <span
                  className={clsx(
                    "text-[9px] font-mono uppercase tracking-wider transition-colors",
                    stepState === "active"
                      ? "text-slate-100 font-semibold"
                      : stepState === "done"
                        ? "text-slate-300"
                        : stepState === "failed"
                          ? "text-red-400"
                          : "text-slate-600"
                  )}
                >
                  {stage.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Inline status row + drawer toggle */}
      <div className="mt-4 flex items-center justify-between gap-4 pt-3 border-t border-white/[0.02]">
        <motion.div
          key={`${searchStage}:${pipelineStage}:${displayIndex}`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className={clsx(
            "text-xs font-mono truncate flex items-center gap-2",
            runState === "error" ? "text-red-400" : "text-slate-300"
          )}
        >
          {runState === "running" ? (
            <Loader2
              className="w-3.5 h-3.5 animate-spin text-accent-primary/80"
              strokeWidth={2}
            />
          ) : runState === "complete" ? (
            <Check className="w-3.5 h-3.5 text-accent-primary" strokeWidth={2.5} />
          ) : (
            <XCircle className="w-3.5 h-3.5 text-red-500" strokeWidth={2.5} />
          )}
          <span className="truncate">{statusText}</span>
          <span className="text-[10px] text-slate-500 font-mono whitespace-nowrap">
            {Math.max(1, displayIndex + 1)}/{stages.length}
          </span>
        </motion.div>

        <button
          type="button"
          onClick={() => togglePipelineDrawer()}
          className={clsx(
            "flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider cursor-pointer",
            "text-slate-400 hover:text-accent-primary transition-colors"
          )}
        >
          <span>{isPipelineDrawerOpen ? "Dölj" : "Detaljer"}</span>
          <ChevronDown
            className={clsx(
              "w-3 h-3 transition-transform",
              isPipelineDrawerOpen ? "rotate-180" : "rotate-0"
            )}
            strokeWidth={1.5}
          />
        </button>
      </div>

      {/* Slim drawer (inline) */}
      <AnimatePresence initial={false}>
        {isPipelineDrawerOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="mt-3 overflow-hidden"
          >
            <div className="rounded-xl border border-white/5 bg-black/30 px-5 py-4">
              {/* Selected stage progress hint */}
              <div className="flex items-center justify-between mb-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                  {stages.find((s) => s.id === selectedPipelineStage)?.label}{" "}
                  Loggar
                </div>
                <div className="w-24 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                  <div
                    className="h-full bg-accent-primary/60 shadow-[0_0_8px_rgba(0,240,244,0.3)]"
                    style={{ width: progressPct }}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                {visibleLog.length === 0 ? (
                  <div className="text-xs text-slate-500 font-mono">
                    Inga loggar tillgängliga.
                  </div>
                ) : (
                  visibleLog.map((l) => (
                    <div
                      key={`${l.ts}:${l.message}`}
                      className="text-xs text-slate-400 font-mono leading-relaxed"
                    >
                      &gt; {l.message}
                    </div>
                  ))
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
