"""
函数注册表模块

从目标协议提取所有需要生成的函数，构建函数清单，
并注入Prompt强制LLM生成完整函数集合。
"""

import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from herta.generator.schemas import RetrievedChunk, TargetProtocolSpec
from herta.llm.client import BigModelClient
from herta.logging import get_logger

logger = get_logger(__name__)


class FunctionType(Enum):
    """函数类型"""
    CMD = "cmd"                    # 命令处理函数
    TELEMETRY = "telemetry"        # 遥测处理函数
    INTERNAL = "internal"          # 内部处理函数
    CALLBACK = "callback"          # 回调函数
    PARSE = "parse"                # 解析函数
    INIT = "init"                  # 初始化函数
    UTIL = "util"                  # 工具函数


@dataclass
class FunctionSpec:
    """
    函数规格定义
    
    描述一个需要生成的函数的所有信息
    """
    # 基本信息
    name: str                           # 函数名（如：dllg_handle_login）
    display_name: str                   # 显示名称（如：登录处理函数）
    func_type: FunctionType             # 函数类型
    
    # 命令相关（如果是cmd类型）
    cmd_code: Optional[str] = None      # 命令字（如：0x01, CMD_LOGIN）
    cmd_name: Optional[str] = None      # 命令名称（如：登录命令）
    
    # 输入输出
    input_params: List[Dict] = field(default_factory=list)   # 输入参数
    output_params: List[Dict] = field(default_factory=list)   # 输出参数
    
    # 功能描述
    description: str = ""               # 功能描述
    business_logic: str = ""            # 业务逻辑说明
    
    # 依赖关系
    dependencies: List[str] = field(default_factory=list)     # 依赖的其他函数名
    calls_external: List[str] = field(default_factory=list)   # 调用的外部函数
    
    # 参考信息
    related_chunks: List[str] = field(default_factory=list)   # 相关的kb chunk_id
    reference_function: Optional[str] = None                 # 参考的源协议函数名
    
    # 生成约束
    is_required: bool = True            # 是否必须生成
    priority: int = 5                   # 优先级（1-10，10最高）
    estimated_lines: int = 50           # 预估代码行数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'func_type': self.func_type.value,
            'cmd_code': self.cmd_code,
            'cmd_name': self.cmd_name,
            'input_params': self.input_params,
            'output_params': self.output_params,
            'description': self.description,
            'business_logic': self.business_logic,
            'dependencies': self.dependencies,
            'is_required': self.is_required,
            'priority': self.priority,
        }


@dataclass
class FunctionList:
    """
    函数清单
    
    包含所有需要生成的函数
    """
    functions: List[FunctionSpec] = field(default_factory=list)
    
    # 统计信息
    total_count: int = 0
    cmd_count: int = 0
    telemetry_count: int = 0
    internal_count: int = 0
    parse_count: int = 0
    init_count: int = 0
    
    # 分组索引（便于快速查找）
    by_type: Dict[str, List[FunctionSpec]] = field(default_factory=dict)
    by_cmd: Dict[str, FunctionSpec] = field(default_factory=dict)
    by_name: Dict[str, FunctionSpec] = field(default_factory=dict)
    
    def build_index(self) -> None:
        """构建索引"""
        self.total_count = len(self.functions)
        self.by_type = {}
        self.by_cmd = {}
        self.by_name = {}
        
        # 重置计数
        self.cmd_count = 0
        self.telemetry_count = 0
        self.internal_count = 0
        self.parse_count = 0
        self.init_count = 0
        
        for func in self.functions:
            type_key = func.func_type.value
            
            # 按类型分组
            if type_key not in self.by_type:
                self.by_type[type_key] = []
            self.by_type[type_key].append(func)
            
            # 按命令字索引
            if func.cmd_code:
                self.by_cmd[func.cmd_code] = func
            
            # 按名称索引
            self.by_name[func.name] = func
            
            # 统计
            if func.func_type == FunctionType.CMD:
                self.cmd_count += 1
            elif func.func_type == FunctionType.TELEMETRY:
                self.telemetry_count += 1
            elif func.func_type == FunctionType.INTERNAL:
                self.internal_count += 1
            elif func.func_type == FunctionType.PARSE:
                self.parse_count += 1
            elif func.func_type == FunctionType.INIT:
                self.init_count += 1
    
    def get_by_type(self, func_type: FunctionType) -> List[FunctionSpec]:
        """按类型获取函数列表"""
        return self.by_type.get(func_type.value, [])
    
    def get_by_cmd(self, cmd_code: str) -> Optional[FunctionSpec]:
        """按命令字获取函数"""
        return self.by_cmd.get(cmd_code)
    
    def get_by_name(self, name: str) -> Optional[FunctionSpec]:
        """按名称获取函数"""
        return self.by_name.get(name)
    
    def get_missing_functions(
        self,
        generated_code: str,
    ) -> List[FunctionSpec]:
        """
        检查生成代码中缺失的函数
        
        Args:
            generated_code: 生成的handler代码
        
        Returns:
            未生成的函数列表
        """
        missing = []
        for func in self.functions:
            if not func.is_required:
                continue
            
            # 检查代码中是否包含函数定义
            # 匹配：函数名后面跟着括号（函数定义）
            pattern = rf'\b{re.escape(func.name)}\s*\('
            if not re.search(pattern, generated_code):
                missing.append(func)
        
        return missing
    
    def to_checklist(self) -> str:
        """生成检查清单文本"""
        lines = ["【函数生成检查清单】"]
        lines.append(f"总计: {self.total_count} 个函数")
        lines.append("")
        
        # 按类型分组输出
        type_order = ['init', 'internal', 'cmd', 'telemetry', 'parse', 'callback', 'util']
        type_names = {
            'init': '初始化函数',
            'internal': '内部处理函数',
            'cmd': '命令处理函数',
            'telemetry': '遥测处理函数',
            'parse': '解析函数',
            'callback': '回调函数',
            'util': '工具函数',
        }
        
        for type_key in type_order:
            funcs = self.by_type.get(type_key, [])
            if not funcs:
                continue
            
            lines.append(f"\n▸ {type_names.get(type_key, type_key)} ({len(funcs)}个):")
            
            # 按优先级排序
            sorted_funcs = sorted(funcs, key=lambda f: f.priority, reverse=True)
            
            for func in sorted_funcs:
                marker = "[必须]" if func.is_required else "[可选]"
                cmd_info = f" [CMD:{func.cmd_code}]" if func.cmd_code else ""
                lines.append(f"  {marker} {func.name}{cmd_info}")
                lines.append(f"    → {func.display_name}")
        
        return "\n".join(lines)
    
    def to_manifest(self) -> str:
        """生成函数清单文本（用于Prompt）"""
        lines = [
            f"【必须生成的函数清单】共 {self.total_count} 个函数",
            "",
        ]
        
        type_names = {
            'init': '初始化函数',
            'internal': '内部处理函数',
            'cmd': '命令处理函数',
            'telemetry': '遥测处理函数',
            'parse': '解析函数',
            'callback': '回调函数',
            'util': '工具函数',
        }
        
        for type_key in ['init', 'internal', 'cmd', 'telemetry', 'parse']:
            funcs = self.by_type.get(type_key, [])
            if not funcs:
                continue
            
            lines.append(f"## {type_names.get(type_key, type_key)} ({len(funcs)}个)")
            
            for func in funcs:
                cmd_info = f" (命令字: {func.cmd_code})" if func.cmd_code else ""
                lines.append(f"- {func.name}{cmd_info}")
                lines.append(f"  功能: {func.display_name}")
                
                if func.description:
                    lines.append(f"  说明: {func.description}")
                
                if func.input_params:
                    params = ", ".join([p.get('name', '?') for p in func.input_params])
                    lines.append(f"  输入: {params}")
                
                if func.output_params:
                    returns = ", ".join([p.get('name', '?') for p in func.output_params])
                    lines.append(f"  输出: {returns}")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_count': self.total_count,
            'cmd_count': self.cmd_count,
            'telemetry_count': self.telemetry_count,
            'internal_count': self.internal_count,
            'functions': [f.to_dict() for f in self.functions]
        }


class FunctionRegistryBuilder:
    """
    函数注册表构建器
    
    从目标协议解析结果中提取所有需要生成的函数
    """
    
    def __init__(self, llm_client: Optional[BigModelClient] = None):
        self.llm_client = llm_client or BigModelClient()
    
    def build_from_target(
        self,
        target_spec: TargetProtocolSpec,
        retrieved_chunks: List[RetrievedChunk],
    ) -> FunctionList:
        """
        从目标协议构建函数清单
        
        流程：
        1. 解析目标协议的命令列表
        2. 解析遥测处理需求
        3. 识别内部处理逻辑
        4. 构建完整的FunctionList
        
        Args:
            target_spec: 目标协议规格
            retrieved_chunks: 检索到的chunks（用于辅助识别）
        
        Returns:
            FunctionList函数清单
        """
        logger.info(f"开始构建函数清单: target={target_spec.target_name}")
        
        func_list = FunctionList()
        
        # 1. 提取命令处理函数
        cmd_functions = self._extract_cmd_functions(target_spec)
        func_list.functions.extend(cmd_functions)
        
        # 2. 提取遥测处理函数
        telemetry_functions = self._extract_telemetry_functions(target_spec)
        func_list.functions.extend(telemetry_functions)
        
        # 3. 提取内部处理函数
        internal_functions = self._extract_internal_functions(target_spec)
        func_list.functions.extend(internal_functions)
        
        # 4. 提取解析函数
        parse_functions = self._extract_parse_functions(target_spec)
        func_list.functions.extend(parse_functions)
        
        # 5. 使用LLM辅助识别补充
        try:
            supplementary = self._llm_supplement_functions(target_spec, func_list)
            func_list.functions.extend(supplementary)
        except Exception as e:
            logger.warning(f"LLM补充函数识别失败: {e}")
        
        # 6. 构建索引
        func_list.build_index()
        
        logger.info(
            f"函数清单构建完成: 总计{func_list.total_count}个 "
            f"(cmd:{func_list.cmd_count}, telemetry:{func_list.telemetry_count}, "
            f"internal:{func_list.internal_count})"
        )
        
        return func_list
    
    def _extract_cmd_functions(
        self,
        target_spec: TargetProtocolSpec,
    ) -> List[FunctionSpec]:
        """从目标协议提取命令处理函数"""
        functions = []
        
        # 尝试从sections中提取命令字信息
        cmd_list = self._parse_cmd_list_from_sections(target_spec.sections)
        
        for cmd in cmd_list:
            # 生成函数名
            cmd_name_lower = cmd['name'].lower().replace(' ', '_')
            func_name = f"{target_spec.target_name}_handle_{cmd_name_lower}"
            
            func = FunctionSpec(
                name=func_name,
                display_name=f"{cmd['name']}处理函数",
                func_type=FunctionType.CMD,
                cmd_code=cmd.get('code', cmd.get('cmd_code')),
                cmd_name=cmd['name'],
                description=cmd.get('description', f"处理{cmd['name']}命令"),
                business_logic=cmd.get('logic', ''),
                input_params=self._parse_cmd_input_params(cmd),
                output_params=self._parse_cmd_output_params(cmd),
                priority=7,  # 命令处理函数优先级较高
            )
            functions.append(func)
        
        logger.debug(f"提取到 {len(functions)} 个命令处理函数")
        return functions
    
    def _extract_telemetry_functions(
        self,
        target_spec: TargetProtocolSpec,
    ) -> List[FunctionSpec]:
        """提取遥测处理函数"""
        functions = []
        
        # 检查是否有遥测相关章节
        telemetry_keywords = ['遥测', 'telemetry', '状态上报', 'status', 'heartbeat', '心跳']
        has_telemetry = any(
            any(kw in s.get('title', '').lower() for kw in telemetry_keywords)
            for s in target_spec.sections
        )
        
        if has_telemetry:
            # 主遥测处理函数
            func_main = FunctionSpec(
                name=f"{target_spec.target_name}_handle_telemetry",
                display_name="遥测数据处理函数",
                func_type=FunctionType.TELEMETRY,
                description="处理设备遥测数据上报",
                input_params=[{
                    'name': 'data',
                    'type': 'const uint8_t*',
                    'description': '遥测数据缓冲区',
                }, {
                    'name': 'len',
                    'type': 'size_t',
                    'description': '数据长度',
                }],
                output_params=[{
                    'name': 'result',
                    'type': 'int32_t',
                    'description': '处理结果，0成功，其他失败',
                }],
                priority=8,
            )
            functions.append(func_main)
            
            # 遥测解析函数
            func_parse = FunctionSpec(
                name=f"{target_spec.target_name}_parse_telemetry",
                display_name="遥测数据解析函数",
                func_type=FunctionType.PARSE,
                description="解析遥测数据包，提取各字段",
                input_params=[{
                    'name': 'data',
                    'type': 'const uint8_t*',
                    'description': '原始数据',
                }],
                output_params=[{
                    'name': 'telemetry',
                    'type': f'{target_spec.target_name}_telemetry_t*',
                    'description': '解析后的遥测数据结构',
                }],
                dependencies=[func_main.name],
                priority=6,
            )
            functions.append(func_parse)
        
        return functions
    
    def _extract_internal_functions(
        self,
        target_spec: TargetProtocolSpec,
    ) -> List[FunctionSpec]:
        """提取内部处理函数"""
        functions = []
        target = target_spec.target_name
        
        # 1. 初始化函数
        functions.append(FunctionSpec(
            name=f"{target}_init",
            display_name="模块初始化函数",
            func_type=FunctionType.INIT,
            description="初始化协议处理模块，设置回调等",
            output_params=[{
                'name': 'result',
                'type': 'int32_t',
                'description': '初始化结果',
            }],
            priority=10,  # 最高优先级
        ))
        
        # 2. 主入口函数
        functions.append(FunctionSpec(
            name=f"{target}_process",
            display_name="主处理入口函数",
            func_type=FunctionType.INTERNAL,
            description="协议数据包主处理入口，外部调用的主接口",
            input_params=[{
                'name': 'data',
                'type': 'const uint8_t*',
                'description': '接收到的数据',
            }, {
                'name': 'len',
                'type': 'size_t',
                'description': '数据长度',
            }],
            output_params=[{
                'name': 'result',
                'type': 'int32_t',
                'description': '处理结果',
            }],
            priority=10,
        ))
        
        # 3. 命令分发函数
        functions.append(FunctionSpec(
            name=f"{target}_dispatch_cmd",
            display_name="命令分发函数",
            func_type=FunctionType.INTERNAL,
            description="根据命令字分发到对应处理函数",
            input_params=[{
                'name': 'cmd_code',
                'type': 'uint8_t',
                'description': '命令字',
            }, {
                'name': 'data',
                'type': 'const uint8_t*',
                'description': '命令数据',
            }],
            output_params=[{
                'name': 'result',
                'type': 'int32_t',
                'description': '处理结果',
            }],
            priority=9,
        ))
        
        # 4. 校验函数
        functions.append(FunctionSpec(
            name=f"{target}_verify_checksum",
            display_name="校验和验证函数",
            func_type=FunctionType.INTERNAL,
            description="验证数据包校验和",
            input_params=[{
                'name': 'data',
                'type': 'const uint8_t*',
                'description': '数据',
            }, {
                'name': 'len',
                'type': 'size_t',
                'description': '长度',
            }],
            output_params=[{
                'name': 'valid',
                'type': 'bool',
                'description': '是否有效',
            }],
            priority=5,
        ))
        
        return functions
    
    def _extract_parse_functions(
        self,
        target_spec: TargetProtocolSpec,
    ) -> List[FunctionSpec]:
        """提取解析函数"""
        functions = []
        
        # 通用消息头解析函数
        functions.append(FunctionSpec(
            name=f"{target_spec.target_name}_parse_header",
            display_name="消息头解析函数",
            func_type=FunctionType.PARSE,
            description="解析协议消息头",
            input_params=[{
                'name': 'data',
                'type': 'const uint8_t*',
                'description': '原始数据',
            }],
            output_params=[{
                'name': 'header',
                'type': f'{target_spec.target_name}_header_t*',
                'description': '解析后的消息头',
            }],
            priority=7,
        ))
        
        return functions
    
    def _parse_cmd_list_from_sections(
        self,
        sections: List[Dict],
    ) -> List[Dict]:
        """从章节结构解析命令列表"""
        cmd_list = []
        
        # 查找命令相关章节
        for section in sections:
            title = section.get('title', '').lower()
            
            if any(kw in title for kw in ['命令', 'command', 'cmd', '指令']):
                # 尝试从内容提取命令字表格
                content = section.get('content', '')
                
                # 简单模式匹配命令字定义
                # 匹配：CMD_XXX = 0xXX 或 0xXX (CMD_NAME)
                cmd_patterns = [
                    r'(CMD_\w+)\s*[=:]\s*(0x[0-9A-Fa-f]+)',
                    r'(0x[0-9A-Fa-f]+)\s*[(:]\s*(\w+)',
                ]
                
                for pattern in cmd_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if len(match) == 2:
                            name, code = match
                            cmd_list.append({
                                'name': name,
                                'code': code,
                                'description': f'{name} 命令',
                            })
        
        return cmd_list
    
    def _parse_cmd_input_params(self, cmd: Dict) -> List[Dict]:
        """解析命令输入参数"""
        # 默认参数
        return [
            {'name': 'data', 'type': 'const uint8_t*', 'description': '命令数据'},
            {'name': 'len', 'type': 'size_t', 'description': '数据长度'},
        ]
    
    def _parse_cmd_output_params(self, cmd: Dict) -> List[Dict]:
        """解析命令输出参数"""
        return [
            {'name': 'result', 'type': 'int32_t', 'description': '处理结果'},
        ]
    
    def _llm_supplement_functions(
        self,
        target_spec: TargetProtocolSpec,
        current_list: FunctionList,
    ) -> List[FunctionSpec]:
        """使用LLM辅助识别补充函数"""
        
        # 构造当前函数清单文本
        current_funcs_text = "\n".join([
            f"- {f.name} ({f.func_type.value}): {f.display_name}"
            for f in current_list.functions
        ])
        
        prompt = f"""【任务】
基于以下目标协议信息，检查函数清单的完整性，识别可能遗漏的必要函数。

【目标协议】
名称: {target_spec.target_name}
摘要: {target_spec.summary[:200]}
章节数: {len(target_spec.sections)}

【当前函数清单】
{current_funcs_text}

【检查要点】
1. 是否遗漏了通用的辅助函数（如数据转换、校验等）？
2. 是否遗漏了错误处理函数？
3. 是否遗漏了状态管理函数？
4. 是否需要事件通知/回调函数？
5. 是否需要内存管理相关函数？

【输出格式】
如果识别到遗漏的函数，输出JSON数组：
[
  {{
    "name": "函数名",
    "type": "cmd/telemetry/internal/parse/callback/util",
    "display_name": "显示名称",
    "reason": "补充原因",
    "priority": 数字1-10
  }}
]

如果没有遗漏，输出空数组 []。

只输出JSON，不要其他内容。"""
        
        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            # 解析JSON
            # 尝试提取JSON部分
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group()
                supplementary_data = json.loads(json_str)
                
                supplementary = []
                for data in supplementary_data:
                    try:
                        func = FunctionSpec(
                            name=data['name'],
                            display_name=data.get('display_name', data['name']),
                            func_type=FunctionType(data.get('type', 'util')),
                            description=data.get('reason', ''),
                            priority=data.get('priority', 3),
                        )
                        supplementary.append(func)
                    except (ValueError, KeyError) as e:
                        logger.warning(f"解析补充函数失败: {e}")
                
                logger.info(f"LLM识别到 {len(supplementary)} 个补充函数")
                return supplementary
            
        except Exception as e:
            logger.warning(f"LLM补充函数识别失败: {e}")
        
        return []


# 便捷函数
def build_function_list(
    target_spec: TargetProtocolSpec,
    retrieved_chunks: List[RetrievedChunk],
    llm_client: Optional[BigModelClient] = None,
) -> FunctionList:
    """
    便捷函数：构建函数清单
    
    Args:
        target_spec: 目标协议规格
        retrieved_chunks: 检索到的chunks
        llm_client: LLM客户端
    
    Returns:
        FunctionList函数清单
    """
    builder = FunctionRegistryBuilder(llm_client)
    return builder.build_from_target(target_spec, retrieved_chunks)
