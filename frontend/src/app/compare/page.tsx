"use client";

import { useEffect, useState, useCallback } from "react";
import Container from "@/components/container";
import { ConfigScores } from "@/components/chart-blocks";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { TargetInfo, CompareMetrics, FunctionMatch } from "@/types/types";

export default function ComparePage() {
  const [targets, setTargets] = useState<TargetInfo[]>([]);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [metrics, setMetrics] = useState<CompareMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");

  useEffect(() => {
    api.targets().then((res) => setTargets(res.targets || [])).catch(() => {});
  }, []);

  // 支持通过 URL 参数直接选中目标协议，如 /compare?target=dllg
  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = new URLSearchParams(window.location.search).get("target");
    if (t) setSelectedTarget(t);
  }, []);

  // 选择 target 后自动加载已有评测结果
  useEffect(() => {
    if (!selectedTarget) return;
    api.compareResult(selectedTarget)
      .then((res) => {
        if (res.exists && res.metrics) setMetrics(res.metrics);
      })
      .catch(() => {});
  }, [selectedTarget]);

  const runCompare = async () => {
    if (!selectedTarget) return;
    setLoading(true);
    setProgress("评测中...");
    setMetrics(null);
    try {
      const res = await api.runCompare(selectedTarget);
      const poll = async () => {
        try {
          const status = await api.taskStatus(res.task_id);
          if (status.status === "completed") {
            const result = await api.compareResult(selectedTarget);
            if (result.exists && result.metrics) {
              setMetrics(result.metrics);
            }
            setProgress("");
            setLoading(false);
          } else if (status.status === "failed") {
            setProgress(`失败: ${status.error || "未知错误"}`);
            setLoading(false);
          } else {
            setProgress(status.message || "评测中...");
            setTimeout(poll, 2000);
          }
        } catch {
          setProgress("状态查询失败");
          setLoading(false);
        }
      };
      setTimeout(poll, 2000);
    } catch (e: unknown) {
      setProgress(`评测失败: ${e instanceof Error ? e.message : "未知错误"}`);
      setLoading(false);
    }
  };

  const fmt = (v: number) => `${v.toFixed(1)}%`;
  const matches = metrics?.details?.function_matches || [];
  const unmatchedGt = metrics?.details?.unmatched_gt_functions || [];
  const unmatchedGen = metrics?.details?.unmatched_gen_functions || [];

  return (
    <div>
      {/* Toolbar */}
      <Container className="flex items-center gap-4 border-b border-border py-3">
        <select
          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={selectedTarget}
          onChange={(e) => setSelectedTarget(e.target.value)}
        >
          <option value="">-- 选择目标协议 --</option>
          {targets.map((t) => (
            <option key={t.name} value={t.name}>{t.name}</option>
          ))}
        </select>
        <Button onClick={runCompare} disabled={!selectedTarget || loading}>
          {loading ? "评测中..." : "运行评测"}
        </Button>
      </Container>

      {progress && !metrics && (
        <Container className="py-3">
          <div className="text-sm text-muted-foreground">{progress}</div>
        </Container>
      )}

      {metrics && (
        <>
          {/* Score Cards */}
          <Container className="grid grid-cols-2 gap-3 border-b border-border py-4 phone:grid-cols-4 laptop:grid-cols-7">
            {[
              { label: "拓扑", value: fmt(metrics.topology_similarity) },
              { label: "命令表", value: fmt(metrics.cmd_list_similarity) },
              { label: "遥测表", value: fmt(metrics.tele_handler_similarity) },
              { label: "内部处理", value: fmt(metrics.internal_handler_similarity) },
              { label: "Config", value: fmt(metrics.config_similarity), highlight: true },
              { label: "Handler", value: fmt(metrics.handler_similarity) },
              { label: "整体", value: fmt(metrics.overall_similarity), highlight: true },
            ].map((item) => (
              <div key={item.label} className={`rounded-lg border p-3 text-center ${item.highlight ? "border-primary/30 bg-primary/5" : "border-border"}`}>
                <div className="text-xs text-muted-foreground">{item.label}</div>
                <div className={`mt-1 text-lg font-medium ${item.highlight ? "text-primary" : ""}`}>{item.value}</div>
              </div>
            ))}
          </Container>

          {/* Chart + Details */}
          <div className="grid grid-cols-1 divide-y border-b border-border laptop:grid-cols-2 laptop:divide-x laptop:divide-y-0">
            <Container className="py-4">
              <ConfigScores data={{
                topology: metrics.topology_similarity,
                cmd_list: metrics.cmd_list_similarity,
                tele_handler: metrics.tele_handler_similarity,
                internal_handler: metrics.internal_handler_similarity,
              }} />
            </Container>
            <Container className="py-4">
              <h3 className="mb-3 text-sm font-medium">Handler 匹配统计</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">真实函数</span>
                  <span className="font-mono">{metrics.details?.function_matches?.length ?? 0}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">成功匹配</span>
                  <span className="font-mono text-primary">{matches.filter((m) => m.is_matched).length}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">未匹配 (GT)</span>
                  <span className="font-mono text-destructive">{unmatchedGt.length}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">多余生成</span>
                  <span className="font-mono text-muted-foreground">{unmatchedGen.length}</span>
                </div>
              </div>
            </Container>
          </div>

          {/* Function Match Table */}
          {matches.length > 0 && (
            <Container className="py-4">
              <h3 className="mb-3 text-sm font-medium">函数匹配列表</h3>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">真实函数</th>
                      <th className="px-3 py-2 text-left font-medium">生成函数</th>
                      <th className="px-3 py-2 text-left font-medium">同名</th>
                      <th className="px-3 py-2 text-left font-medium">AST</th>
                      <th className="px-3 py-2 text-left font-medium">TED</th>
                      <th className="px-3 py-2 text-left font-medium">语义</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matches.map((m: FunctionMatch, i: number) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-3 py-2 font-mono text-xs">{m.gt_func_name}</td>
                        <td className="px-3 py-2 font-mono text-xs">{m.gen_func_name || "-"}</td>
                        <td className="px-3 py-2">{m.is_name_match ? "✓" : "✗"}</td>
                        <td className="px-3 py-2 font-mono">{(m.ast_similarity * 100).toFixed(1)}%</td>
                        <td className="px-3 py-2 font-mono">{(m.tree_edit_similarity * 100).toFixed(1)}%</td>
                        <td className="px-3 py-2 font-mono">{(m.semantic_feature_similarity * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Container>
          )}
        </>
      )}

      {!metrics && !loading && (
        <Container className="py-8 text-center text-sm text-muted-foreground">
          选择目标协议并运行评测
        </Container>
      )}
    </div>
  );
}
