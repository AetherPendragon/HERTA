/**
 * 后端 API 封装
 *
 * 前端通过 Next.js rewrites 将 /api/* 代理到 http://localhost:8000/api/*
 */

import type {
  KBInfo,
  TargetInfo,
  CompareMetrics,
  TaskStatus,
  SettingsData,
  Projection2D,
} from "@/types/types";

const BASE = "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} 失败: ${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export interface KBListResponse {
  knowledge_bases: KBInfo[];
}

export interface TargetsResponse {
  targets: TargetInfo[];
}

export interface TaskSubmitResponse {
  task_id: string;
  status: string;
}

export interface VisualizationResponse {
  points: Projection2D[];
}

export interface GenerateResultResponse {
  exists?: boolean;
  config?: Record<string, unknown>;
  handler_source?: string;
}

export interface CompareResultResponse {
  exists: boolean;
  metrics?: CompareMetrics;
}

export const api = {
  // ---------- 知识库 ----------
  kbList: () => request<KBListResponse>("/kb/list"),

  kbBuild: (
    source: string,
    chunkStrategy: string,
    chunkSize: number,
    chunkOverlap: number,
    force: boolean
  ) =>
    request<TaskSubmitResponse>("/kb/build", {
      method: "POST",
      body: JSON.stringify({
        source,
        chunk_strategy: chunkStrategy,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        force,
      }),
    }),

  kbVisualization: (source: string) =>
    request<VisualizationResponse>(`/kb/visualization/${source}`),

  // ---------- 代码生成 ----------
  targets: () => request<TargetsResponse>("/generate/targets"),

  generateConfig: (target: string, sourceKb: string, topK: number) =>
    request<TaskSubmitResponse>("/generate/config", {
      method: "POST",
      body: JSON.stringify({ target, source_kb: sourceKb, top_k: topK }),
    }),

  generateHandler: (target: string, sourceKb: string, topK: number) =>
    request<TaskSubmitResponse>("/generate/handler", {
      method: "POST",
      body: JSON.stringify({ target, source_kb: sourceKb, top_k: topK }),
    }),

  generateResult: (target: string) =>
    request<GenerateResultResponse>(`/generate/result/${target}`),

  // ---------- 评测对比 ----------
  runCompare: (target: string) =>
    request<TaskSubmitResponse>("/compare/run", {
      method: "POST",
      body: JSON.stringify({ target }),
    }),

  compareResult: (target: string) =>
    request<CompareResultResponse>(`/compare/result/${target}`),

  // ---------- 设置 / 任务 ----------
  getSettings: () => request<SettingsData>("/settings"),

  saveSettings: (data: {
    api_key?: string;
    chat_model?: string;
    embedding_model?: string;
  }) =>
    request<{ status: string }>("/settings", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  taskStatus: (taskId: string) =>
    request<TaskStatus>(`/settings/task/${taskId}`),
};
