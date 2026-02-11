import os
from pathlib import Path
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


def resolve_qr_path(raw_path: str) -> str | None:
    """尝试多种路径解析方式找到收款码文件"""
    candidates = [raw_path]
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        data_path = Path(get_astrbot_data_path())
        candidates.append(str(data_path / "plugin_data" / "astrbot_plugin_payqr" / raw_path))
        candidates.append(str(data_path / raw_path))
        candidates.append(str(data_path.parent / raw_path))
    except Exception:
        pass
    candidates.append(str(Path(os.getcwd()) / raw_path))

    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


@dataclass
class SendPaymentQRTool(FunctionTool[AstrAgentContext]):
    name: str = "send_payment_qr"
    description: str = "当你觉得自己没钱了、穷了、需要别人打钱、转账、赞助、请客、发红包等与要钱相关的话题时，调用此工具发送收款码图片。"
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        ctx = context.context.context  # AstrBot Context
        event = context.context.event

        # 从插件配置获取收款码路径
        stars = ctx.get_all_stars()
        qr_path = None
        for star in stars:
            if star.star_cls and hasattr(star.star_cls, '_qr_path'):
                qr_path = star.star_cls._qr_path
                break

        if not qr_path:
            return "收款码还没有配置或文件不存在，请让管理员在插件配置中上传收款码图片。"

        try:
            mc = MessageChain().message("给我打钱！👇").file_image(qr_path)
            await ctx.send_message(event.unified_msg_origin, mc)
            return "收款码图片已成功发送给用户，你可以继续正常回复。"
        except Exception as e:
            logger.error(f"[PayQR] 发送收款码失败: {e}")
            return f"发送收款码失败: {e}"


@register("astrbot_plugin_payqr", "user", "当LLM觉得没钱时自动发送收款码", "1.0.0")
class PayQRPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 解析并缓存收款码路径
        self._qr_path = None
        files = config.get("payment_qr", [])
        if files:
            self._qr_path = resolve_qr_path(files[0])
            logger.info(f"[PayQR] 收款码路径: {self._qr_path}")

        self.context.add_llm_tools(SendPaymentQRTool())
