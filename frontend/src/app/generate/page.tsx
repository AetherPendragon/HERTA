"use client";

import { useEffect, useState, useCallback } from "react";
import Container from "@/components/container";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { TargetInfo, KBInfo } from "@/types/types";

export default function GeneratePage() {
  const [targets, setTargets] = useState<TargetInfo[]>([]);
  const [kbs, setKbs] = useState<KBInfo[]>([]);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [selectedKb, setSelectedKb] = useState("");
  const [topK, setTopK] = useState(30);
  const [step, setStep] = useState(1);
  const [progress, setProgress] = useState("");
  const [progressPct, setProgressPct] = useState(0);
  const [configResult, setConfigResult] = useState<string | null>(null);
  const [handlerResult, setHandlerResult] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"config" | "handler">("config");

  useEffect(() => {
    Promise.all([api.targets(), api.kbList()])
      .then(([tRes, kRes]) => {
        setTargets(tRes.targets || []);
        setKbs(kRes.knowledge_bases || []);
      })
      .catch(() => {});
  }, []);

  const pollTask = useCallback(async (taskId: string, onDone: () => void) => {
    const poll = async () => {
      try {
        const status = await api.taskStatus(taskId);
        if (status.status === "completed") {
          setProgressPct(100);
          setTimeout(onDone, 500);
        } else if (status.status === "failed") {
          setProgress(`失败: ${status.error || "未知错误"}`);
          setStep(1);
        } else {
          setProgress(status.message || "处理中...");
          setProgressPct(Math.min(status.progress || 50, 90));
          setTimeout(poll, 2000);
        }
      } catch {
        setProgress("状态查询失败");
        setStep(1);
      }
    };
    setTimeout(poll, 2000);
  }, []);

  const handleGenConfig = async () => {
    if (!selectedTarget) return;
    setStep(2);
    setProgress("正在生成 Config...");
    setProgressPct(10);
    try {
      const res = await api.generateConfig(selectedTarget, selectedKb, topK);
      await pollTask(res.task_id, async () => {
        try {
          const result = await api.generateResult(selectedTarget);
          setConfigResult(JSON.stringify(result.config, null, 2));
          setStep(3);
          setProgress("");
        } catch {
          setProgress("获取结果失败");
          setStep(1);
        }
      });
    } catch (e: unknown) {
      setProgress(`生成失败: ${e instanceof Error ? e.message : "未知错误"}`);
      setStep(1);
    }
  };

  const handleGenHandler = async () => {
    if (!selectedTarget) return;
    setProgress("正在生成 Handler...");
    setProgressPct(10);
    try {
      const res = await api.generateHandler(selectedTarget, selectedKb, topK);
      await pollTask(res.task_id, async () => {
        try {
          const result = await api.generateResult(selectedTarget);
          setHandlerResult(result.handler_source || "");
          setProgress("");
        } catch {
          setProgress("获取结果失败");
        }
      });
    } catch (e: unknown) {
      setProgress(`生成失败: ${e instanceof Error ? e.message : "未知错误"}`);
    }
  };

  return (
    <div>
      {/* Target selection */}
      <Container className="border-b border-border py-4">
        <div className="grid gap-4 laptop:grid-cols-4">
          <div>
            <label className="mb-1 block text-sm font-medium">目标协议</label>
            <select
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={selectedTarget}
              onChange={(e) => setSelectedTarget(e.target.value)}
            >
              <option value="">-- 选择目标 --</option>
              {targets.map((t) => (
                <option key={t.name} value={t.name}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">源知识库</label>
            <select
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={selectedKb}
              onChange={(e) => setSelectedKb(e.target.value)}
            >
              <option value="">-- 选择知识库 --</option>
              {kbs.map((kb) => (
                <option key={kb.source} value={kb.source}>{kb.source}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Top-K</label>
            <input
              type="number"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </div>
          <div className="flex items-end gap-2">
            <Button onClick={handleGenConfig} disabled={!selectedTarget || step === 2}>
              生成 Config
            </Button>
            <Button
              variant="outline"
              onClick={handleGenHandler}
              disabled={!selectedTarget || !configResult}
            >
              生成 Handler
            </Button>
          </div>
        </div>
      </Container>

      {/* Progress */}
      {progress && (
        <Container className="border-b border-border py-3">
          <div className="text-sm text-muted-foreground">{progress}</div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </Container>
      )}

      {/* Result */}
      {(configResult || handlerResult) && (
        <Container className="py-4">
          <div className="mb-3 flex gap-2">
            <Button variant={viewMode === "config" ? "default" : "outline"} size="sm" onClick={() => setViewMode("config")}>
              Config
            </Button>
            <Button variant={viewMode === "handler" ? "default" : "outline"} size="sm" onClick={() => setViewMode("handler")}>
              Handler
            </Button>
          </div>
          <pre className="max-h-[600px] overflow-auto rounded-lg border border-border bg-muted/30 p-4 text-xs leading-relaxed">
            <code>{viewMode === "config" ? configResult : handlerResult}</code>
          </pre>
        </Container>
      )}
    </div>
  );
}
