"use client";

import { useEffect, useState, useCallback } from "react";
import Container from "@/components/container";
import { EmbeddingScatter } from "@/components/chart-blocks";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { KBInfo, Projection2D } from "@/types/types";

const STRATEGY_OPTIONS = [
  { value: "direct", label: "Direct（直接注入）" },
  { value: "simple", label: "Simple（固定大小）" },
  { value: "semantic", label: "Semantic（语义分块）" },
  { value: "code_aware", label: "Code Aware（代码感知）" },
  { value: "proposition", label: "Proposition（原子命题）" },
];

export default function KnowledgePage() {
  const [kbs, setKbs] = useState<KBInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showBuild, setShowBuild] = useState(false);
  const [building, setBuilding] = useState(false);
  const [buildMsg, setBuildMsg] = useState("");
  const [selectedKb, setSelectedKb] = useState<string | null>(null);
  const [projection, setProjection] = useState<Projection2D[] | null>(null);

  // Form state
  const [formSource, setFormSource] = useState("");
  const [formStrategy, setFormStrategy] = useState("direct");
  const [formChunkSize, setFormChunkSize] = useState(500);
  const [formOverlap, setFormOverlap] = useState(50);
  const [formForce, setFormForce] = useState(false);

  const loadKbs = useCallback(async () => {
    try {
      const res = await api.kbList();
      setKbs(res.knowledge_bases || []);
    } catch {
      setKbs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadKbs(); }, [loadKbs]);

  const loadVisualization = useCallback(async (source: string) => {
    setSelectedKb(source);
    try {
      const res = await api.kbVisualization(source);
      setProjection(res.points || []);
    } catch {
      setProjection(null);
    }
  }, []);

  const handleBuild = async () => {
    if (!formSource.trim()) return;
    setBuilding(true);
    setBuildMsg("构建中...");
    try {
      const res = await api.kbBuild(formSource, formStrategy, formChunkSize, formOverlap, formForce);
      // Poll task status
      const poll = async () => {
        try {
          const status = await api.taskStatus(res.task_id);
          if (status.status === "completed") {
            setBuildMsg("构建完成!");
            setBuilding(false);
            setShowBuild(false);
            loadKbs();
          } else if (status.status === "failed") {
            setBuildMsg(`构建失败: ${status.error || "未知错误"}`);
            setBuilding(false);
          } else {
            setBuildMsg(status.message || "处理中...");
            setTimeout(poll, 2000);
          }
        } catch {
          setBuildMsg("状态查询失败");
          setBuilding(false);
        }
      };
      setTimeout(poll, 2000);
    } catch (e: unknown) {
      setBuildMsg(`构建失败: ${e instanceof Error ? e.message : "未知错误"}`);
      setBuilding(false);
    }
  };

  return (
    <div>
      {/* Toolbar */}
      <Container className="flex items-center justify-between border-b border-border py-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          已构建 {kbs.length} 个知识库
        </h2>
        <Button onClick={() => setShowBuild(true)} size="sm">
          构建知识库
        </Button>
      </Container>

      {/* KB List */}
      <Container className="py-4">
        {loading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">加载中...</div>
        ) : kbs.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            暂无知识库，点击"构建知识库"开始
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">来源</th>
                  <th className="px-4 py-2.5 text-left font-medium">分块策略</th>
                  <th className="px-4 py-2.5 text-left font-medium">Chunks</th>
                  <th className="px-4 py-2.5 text-left font-medium">Embedding 模型</th>
                  <th className="px-4 py-2.5 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {kbs.map((kb) => (
                  <tr key={kb.source} className="border-t border-border hover:bg-muted/30">
                    <td className="px-4 py-2.5 font-mono">{kb.source}</td>
                    <td className="px-4 py-2.5">{kb.chunk_strategy}</td>
                    <td className="px-4 py-2.5 font-mono">{kb.chunk_count}</td>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground">{kb.embedding_model}</td>
                    <td className="px-4 py-2.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => loadVisualization(kb.source)}
                      >
                        可视化
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Container>

      {/* Visualization */}
      {selectedKb && (
        <Container className="border-t border-border py-4">
          <EmbeddingScatter data={projection} />
        </Container>
      )}

      {/* Build Dialog */}
      {showBuild && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !building && setShowBuild(false)}>
          <div className="mx-4 w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-lg font-medium">构建知识库</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">来源标识</label>
                <input
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  placeholder="如: gdwx"
                  value={formSource}
                  onChange={(e) => setFormSource(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium">策略</label>
                  <select
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={formStrategy}
                    onChange={(e) => setFormStrategy(e.target.value)}
                  >
                    {STRATEGY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Chunk Size</label>
                  <input
                    type="number"
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={formChunkSize}
                    onChange={(e) => setFormChunkSize(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Overlap</label>
                  <input
                    type="number"
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={formOverlap}
                    onChange={(e) => setFormOverlap(Number(e.target.value))}
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={formForce}
                  onChange={(e) => setFormForce(e.target.checked)}
                  className="rounded"
                />
                强制重建
              </label>
            </div>
            {buildMsg && <div className="mt-3 text-sm text-muted-foreground">{buildMsg}</div>}
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowBuild(false)} disabled={building}>
                取消
              </Button>
              <Button onClick={handleBuild} disabled={building || !formSource.trim()}>
                {building ? "构建中..." : "开始构建"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
