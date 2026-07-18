"""Provider-neutral AI gateway foundation."""

from core.ai.config import AiGatewayConfig, load_ai_gateway_config
from core.ai.gateway import AiGateway
from core.ai.models import (
    AiCapabilityResult,
    AiGatewayRequest,
    AiGatewayResponse,
    AiProviderReadiness,
    AiRequestMetadata,
)

__all__ = [
    "AiCapabilityResult",
    "AiGateway",
    "AiGatewayConfig",
    "AiGatewayRequest",
    "AiGatewayResponse",
    "AiProviderReadiness",
    "AiRequestMetadata",
    "load_ai_gateway_config",
]
