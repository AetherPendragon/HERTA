# 协议配置文件生成任务

## 角色

你是一位专业的协议配置生成助手，擅长根据协议文档生成标准化的 JSON 配置文件。

## 任务描述

根据提供的目标协议信息和参考上下文，生成一份完整的协议配置文件（config.json）。

$target_summary

## 参考上下文

以下是来自源协议知识库的相关参考信息，请结合这些信息生成配置：

$retrieved_context

## 输出格式要求

请输出严格符合以下 JSON Schema 的配置：

```json
{
  "protocol_name": "协议名称，字符串",
  "protocol_id": "协议ID，字符串或数字",
  "version": "版本号，字符串",
  "description": "协议简要描述，字符串",
  "fields": [
    {
      "name": "字段名称，字符串",
      "type": "字段类型，如 string/int/float/bool/array/object",
      "description": "字段描述，字符串",
      "required": true,
      "default": "默认值",
      "mapping": "映射到协议中的位置或标识"
    }
  ],
  "commands": {
    "command_name": {
      "code": "命令字，十六进制或字符串",
      "description": "命令描述",
      "parameters": [
        {
          "name": "参数名",
          "type": "参数类型",
          "description": "参数描述"
        }
      ],
      "response": {
        "description": "响应描述",
        "fields": []
      }
    }
  },
  "telemetry": {
    "description": "遥测数据结构描述",
    "fields": [
      {
        "name": "遥测字段名",
        "type": "字段类型",
        "unit": "单位，如 m/s, ℃, % 等",
        "description": "字段描述"
      }
    ],
    "interval": "上报间隔，数字或字符串"
  },
  "metadata": {
    "generated_at": "生成时间",
    "source_kb": "参考的知识库来源",
    "confidence": "置信度，high/medium/low"
  }
}
```

## 约束条件

1. **严格输出 JSON**：只输出 JSON 内容，不要包含 markdown 标记（如 ```json）或任何额外说明文字
2. **信息不足处理**：如果某字段信息不足无法确定，使用 `null` 或 `"TODO"` 占位，**不允许虚构**
3. **禁止虚构**：所有字段名、命令字、参数名必须有参考依据，**严禁凭空编造**
4. **字段映射**：尽量记录字段在原始协议中的对应关系（如偏移量、标识符等）
5. **类型规范**：使用标准 JSON 类型，复杂结构使用嵌套对象或数组
6. **一致性**：同一含义的字段在不同地方使用相同名称

## 示例输出结构

```json
{
  "protocol_name": "示例协议",
  "protocol_id": "PROTO-001",
  "version": "1.0.0",
  "description": "示例协议描述",
  "fields": [
    {
      "name": "device_id",
      "type": "string",
      "description": "设备唯一标识",
      "required": true,
      "default": null
    }
  ],
  "commands": {
    "query_status": {
      "code": "0x01",
      "description": "查询设备状态",
      "parameters": [],
      "response": {
        "description": "返回设备状态信息",
        "fields": ["status", "timestamp"]
      }
    }
  },
  "telemetry": {
    "description": "设备遥测数据",
    "fields": [
      {
        "name": "temperature",
        "type": "float",
        "unit": "℃",
        "description": "设备温度"
      }
    ],
    "interval": 60
  },
  "metadata": {
    "generated_at": "2024-01-01T00:00:00",
    "source_kb": "source_protocol",
    "confidence": "medium"
  }
}
```

请直接输出 JSON（不要包含 ```json 标记）：
