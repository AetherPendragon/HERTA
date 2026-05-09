"use client";

import { useEffect, useState } from "react";
import Container from "@/components/container";
import { Metrics, ConfigScores } from "@/components/chart-blocks";
import type { MetricData, ConfigScoreData } from "@/components/chart-blocks";
import { api } from "@/lib/api";
import type { KBInfo, CompareMetrics, SettingsData } from "@/types/types";

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<MetricData[]>([
    { title: "知识库", value: "-", change: 0 },
    { title: "Config 相似度", value: "-", change: 0 },
    { title: "Handler 相似度", value: "-", change: 0 },
    { title: "整体相似度", value: "-", change: 0 },
  ]);
  const [configScores, setConfigScores] = useState<ConfigScoreData | null>(null);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [kbCount, setKbCount] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        const [kbRes, settingsRes] = await Promise.all([
          api.kbList().catch(() => ({ knowledge_bases: [] })),
          api.getSettings().catch(() => null),
        ]);
        const kbs = kbRes.knowledge_bases || [];
        setKbCount(kbs.length);
        setSettings(settingsRes);

        setMetrics([
          { title: "知识库", value: `${kbs.length} 个`, change: 0 },
          { title: "Config 相似度", value: "-", change: 0 },
          { title: "Handler 相似度", value: "-", change: 0 },
          { title: "整体相似度", value: "-", change: 0 },
        ]);

        // Try to load latest compare result from first target
        const targetsRes = await api.targets().catch(() => ({ targets: [] }));
        const targets = targetsRes.targets || [];
        if (targets.length > 0) {
          try {
            const cmpRes = await api.compareResult(targets[0].name);
            if (cmpRes.exists && cmpRes.metrics) {
              const m = cmpRes.metrics;
              setMetrics([
                { title: "知识库", value: `${kbs.length} 个`, change: 0 },
                { title: "Config 相似度", value: `${m.config_similarity.toFixed(1)}%`, change: 0 },
                { title: "Handler 相似度", value: `${m.handler_similarity.toFixed(1)}%`, change: 0 },
                { title: "整体相似度", value: `${m.overall_similarity.toFixed(1)}%`, change: 0 },
              ]);
              setConfigScores({
                topology: m.topology_similarity,
                cmd_list: m.cmd_list_similarity,
                tele_handler: m.tele_handler_similarity,
                internal_handler: m.internal_handler_similarity,
              });
            }
          } catch {
            // no compare result yet
          }
        }
      } catch (e) {
        console.error("Dashboard load error:", e);
      }
    }
    load();
  }, []);

  return (
    <div>
      <Metrics data={metrics} />
      <div className="grid grid-cols-1 divide-y border-b border-border laptop:grid-cols-2 laptop:divide-x laptop:divide-y-0">
        <Container className="py-6 laptop:col-span-1">
          <ConfigScores data={configScores} />
        </Container>
        <Container className="py-6 laptop:col-span-1">
          <div className="flex h-full flex-col gap-3">
            <h2 className="text-base font-medium">系统信息</h2>
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full text-sm">
                <tbody>
                  <tr className="border-b border-border">
                    <td className="bg-muted/50 px-4 py-2.5 font-medium">LLM 模型</td>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground">{settings?.chat_model || "-"}</td>
                  </tr>
                  <tr className="border-b border-border">
                    <td className="bg-muted/50 px-4 py-2.5 font-medium">Embedding 模型</td>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground">{settings?.embedding_model || "-"}</td>
                  </tr>
                  <tr className="border-b border-border">
                    <td className="bg-muted/50 px-4 py-2.5 font-medium">Embedding 维度</td>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground">{settings?.embedding_dimensions || "-"}</td>
                  </tr>
                  <tr>
                    <td className="bg-muted/50 px-4 py-2.5 font-medium">API Key</td>
                    <td className="px-4 py-2.5 font-mono text-muted-foreground">
                      {settings?.api_key_set ? settings.api_key_preview : "未设置"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </Container>
      </div>
    </div>
  );
}
