import {
  Gauge,
  Database,
  Code2,
  GitCompareArrows,
  Settings,
  type LucideIcon,
} from "lucide-react";

export type Navigation = {
  icon: LucideIcon;
  name: string;
  href: string;
};

export const siteConfig = {
  title: "Herta - 工业协议代码生成系统",
  description: "基于领域知识增强 LLM 的工业协议代码自动生成平台",
};

export const navigations: Navigation[] = [
  { icon: Gauge, name: "仪表盘", href: "/" },
  { icon: Database, name: "知识库", href: "/knowledge" },
  { icon: Code2, name: "代码生成", href: "/generate" },
  { icon: GitCompareArrows, name: "评测对比", href: "/compare" },
  { icon: Settings, name: "设置", href: "/settings" },
];
