"""
Cloud-optimized model configuration for awesome-ai-apps.

Maps expensive large models to smaller, cost-effective alternatives
while preserving functionality. All models route through Nebius
Token Factory for unified billing and inference.

Usage:
    from cloud_deploy.model_config import get_optimized_model, get_model_config

    model_id = get_optimized_model("Qwen/Qwen3-Coder-480B-A35B-Instruct")
    # Returns: "Qwen/Qwen3-30B-A3B"

    config = get_model_config()
    # Returns full config dict with base_url, model, embedding model
"""

import os
from dataclasses import dataclass, field

NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1"

MODEL_TIER_MAP = {
    "minimal": {
        "Qwen/Qwen3-Coder-480B-A35B-Instruct": "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen3-235B-A22B": "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen3.5-397B-A17B": "Qwen/Qwen3-30B-A3B",
        "deepseek-ai/DeepSeek-V3-0324": "deepseek-ai/DeepSeek-V3-0324",
        "meta-llama/Meta-Llama-3.1-70B-Instruct": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.3-70B-Instruct-fast": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4o": "gpt-4o-mini",
    },
    "balanced": {
        "Qwen/Qwen3-Coder-480B-A35B-Instruct": "Qwen/Qwen3-235B-A22B",
        "Qwen/Qwen3-235B-A22B": "Qwen/Qwen3-235B-A22B",
        "Qwen/Qwen3.5-397B-A17B": "Qwen/Qwen3-235B-A22B",
        "deepseek-ai/DeepSeek-V3-0324": "deepseek-ai/DeepSeek-V3-0324",
        "meta-llama/Meta-Llama-3.1-70B-Instruct": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.3-70B-Instruct-fast": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4o": "gpt-4o-mini",
    },
}

EMBEDDING_MODELS = {
    "minimal": "BAAI/bge-en-icl",
    "balanced": "BAAI/bge-en-icl",
}

INFERENCE_PARAMS = {
    "minimal": {
        "max_tokens": 1024,
        "temperature": 0.3,
        "top_p": 0.9,
    },
    "balanced": {
        "max_tokens": 2048,
        "temperature": 0.7,
        "top_p": 0.95,
    },
}


@dataclass
class ModelConfig:
    tier: str = "minimal"
    base_url: str = NEBIUS_BASE_URL
    api_key: str = ""
    default_model: str = ""
    embedding_model: str = ""
    inference_params: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.getenv("NEBIUS_API_KEY", "")
        if not self.default_model:
            self.default_model = "Qwen/Qwen3-30B-A3B" if self.tier == "minimal" else "Qwen/Qwen3-235B-A22B"
        if not self.embedding_model:
            self.embedding_model = EMBEDDING_MODELS.get(self.tier, "BAAI/bge-en-icl")
        if not self.inference_params:
            self.inference_params = INFERENCE_PARAMS.get(self.tier, INFERENCE_PARAMS["minimal"])


def get_optimized_model(original_model: str, tier: str = None) -> str:
    if tier is None:
        tier = os.getenv("CLOUD_TIER", "minimal")
    tier_map = MODEL_TIER_MAP.get(tier, MODEL_TIER_MAP["minimal"])
    return tier_map.get(original_model, original_model)


def get_model_config(tier: str = None) -> ModelConfig:
    if tier is None:
        tier = os.getenv("CLOUD_TIER", "minimal")
    return ModelConfig(tier=tier)


def patch_openai_client_args(original_kwargs: dict, tier: str = None) -> dict:
    """Patch OpenAI client constructor args for cloud optimization."""
    config = get_model_config(tier)
    patched = dict(original_kwargs)
    if "base_url" not in patched or "nebius" in patched.get("base_url", ""):
        patched["base_url"] = config.base_url
    if "api_key" not in patched:
        patched["api_key"] = config.api_key
    if "model" in patched:
        patched["model"] = get_optimized_model(patched["model"], tier)
    return patched
