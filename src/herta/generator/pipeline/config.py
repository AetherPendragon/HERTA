"""
Pipeline配置管理

支持YAML配置加载和动态覆盖
"""

import copy
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from pathlib import Path

from herta.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StageConfig:
    """单个阶段的配置"""
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StageConfig':
        return cls(
            enabled=data.get('enabled', True),
            params=data.get('params', {})
        )
    
    def to_dict(self) -> Dict:
        return {
            'enabled': self.enabled,
            'params': self.params
        }


@dataclass
class PipelineConfig:
    """完整的Pipeline配置"""
    name: str = "herta_rag_pipeline"
    version: str = "2.0"
    fail_on_error: bool = False
    
    # 各阶段配置
    query_rewrite: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    retrieval: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    rerank: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    context_compression: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    structured_context: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    prompt_building: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    llm_generation: StageConfig = field(default_factory=lambda: StageConfig(enabled=True))
    
    # 覆盖配置
    overrides: Dict[str, Dict] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls, path: str) -> 'PipelineConfig':
        """从YAML文件加载配置"""
        path = Path(path)
        
        if not path.exists():
            logger.warning(f"配置文件不存在: {path}，使用默认配置")
            return cls()
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data or 'pipeline' not in data:
            logger.warning("配置文件格式错误，使用默认配置")
            return cls()
        
        pipeline_data = data.get('pipeline', {})
        stages = pipeline_data.get('stages', {})
        
        return cls(
            name=pipeline_data.get('name', cls.name),
            version=pipeline_data.get('version', cls.version),
            fail_on_error=pipeline_data.get('fail_on_error', cls.fail_on_error),
            
            query_rewrite=StageConfig.from_dict(stages.get('query_rewrite', {})),
            retrieval=StageConfig.from_dict(stages.get('retrieval', {})),
            rerank=StageConfig.from_dict(stages.get('rerank', {})),
            context_compression=StageConfig.from_dict(stages.get('context_compression', {})),
            structured_context=StageConfig.from_dict(stages.get('structured_context', {})),
            prompt_building=StageConfig.from_dict(stages.get('prompt_building', {})),
            llm_generation=StageConfig.from_dict(stages.get('llm_generation', {})),
            
            overrides=pipeline_data.get('overrides', {})
        )
    
    def get_config_for_generation_type(self, gen_type: str) -> 'PipelineConfig':
        """获取特定生成类型的配置（应用覆盖）"""
        if gen_type not in self.overrides:
            return self
        
        # 创建副本并应用覆盖
        new_config = copy.deepcopy(self)
        
        override = self.overrides[gen_type].get('stages', {})
        for stage_name, stage_override in override.items():
            if hasattr(new_config, stage_name):
                current: StageConfig = getattr(new_config, stage_name)
                # 合并params
                if 'params' in stage_override:
                    current.params.update(stage_override['params'])
                # 更新enabled
                if 'enabled' in stage_override:
                    current.enabled = stage_override['enabled']
        
        logger.debug(f"应用配置覆盖: {gen_type}")
        return new_config
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'name': self.name,
            'version': self.version,
            'fail_on_error': self.fail_on_error,
            'stages': {
                'query_rewrite': self.query_rewrite.to_dict(),
                'retrieval': self.retrieval.to_dict(),
                'rerank': self.rerank.to_dict(),
                'context_compression': self.context_compression.to_dict(),
                'structured_context': self.structured_context.to_dict(),
                'prompt_building': self.prompt_building.to_dict(),
                'llm_generation': self.llm_generation.to_dict(),
            }
        }
    
    def save(self, path: str) -> None:
        """保存配置到YAML文件"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'pipeline': {
                'name': self.name,
                'version': self.version,
                'fail_on_error': self.fail_on_error,
                'stages': self.to_dict()['stages'],
                'overrides': self.overrides
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"配置已保存: {path}")
