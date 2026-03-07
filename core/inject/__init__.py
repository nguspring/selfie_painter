"""
智能注入模块

提供五大组件：
1. ConversationContextCache - 对话上下文缓存
2. IntentClassifier - 意图分类器
3. ActivityStateAnalyzer - 状态分析器
4. InjectOptimizer - 注入优化器
5. ContentTemplateEngine - 内容模板引擎
"""

from .context_cache import ConversationContextCache, get_context_cache
from .intent_classifier import IntentClassifier, IntentType, classify_intent
from .state_analyzer import ActivityStateAnalyzer, analyze_schedule_state
from .inject_optimizer import InjectOptimizer, optimize_injection
from .content_template import ContentTemplateEngine, render_injection_content

__all__ = [
    "ConversationContextCache",
    "get_context_cache",
    "IntentClassifier",
    "IntentType",
    "classify_intent",
    "ActivityStateAnalyzer",
    "analyze_schedule_state",
    "InjectOptimizer",
    "optimize_injection",
    "ContentTemplateEngine",
    "render_injection_content",
]
