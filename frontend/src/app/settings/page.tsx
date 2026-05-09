"use client";

import { useEffect, useState } from "react";
import Container from "@/components/container";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { SettingsData } from "@/types/types";

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getSettings()
      .then((data) => {
        setSettings(data);
        setChatModel(data.chat_model || "");
        setEmbedModel(data.embedding_model || "");
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMsg("");
    try {
      const data: Record<string, string> = { chat_model: chatModel, embedding_model: embedModel };
      if (apiKey) data.api_key = apiKey;
      await api.saveSettings(data);
      setMsg("保存成功");
      setApiKey("");
      const updated = await api.getSettings();
      setSettings(updated);
    } catch (e: unknown) {
      setMsg(`保存失败: ${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Container className="py-6">
      <div className="mx-auto max-w-lg space-y-6">
        <div className="rounded-lg border border-border p-5">
          <h3 className="mb-4 text-base font-medium">API 设置</h3>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">智谱 API Key</label>
              <input
                type="password"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder={settings?.api_key_set ? `当前: ${settings.api_key_preview}` : "输入 API Key"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
              <div className="mt-1 text-xs text-muted-foreground">
                {settings?.api_key_set ? "已设置，留空保持不变" : "未设置"}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Chat 模型</label>
                <input
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  placeholder="glm-5.1"
                  value={chatModel}
                  onChange={(e) => setChatModel(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Embedding 模型</label>
                <input
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  placeholder="embedding-3"
                  value={embedModel}
                  onChange={(e) => setEmbedModel(e.target.value)}
                />
              </div>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "保存中..." : "保存设置"}
            </Button>
            {msg && <span className="text-sm text-muted-foreground">{msg}</span>}
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          注意：此处的设置仅在当前服务器会话有效。重启后需重新设置，或通过环境变量 ZAI_API_KEY 永久配置。
        </div>
      </div>
    </Container>
  );
}
