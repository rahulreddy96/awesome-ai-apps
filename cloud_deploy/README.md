# Cloud Deploy — Minimum Resource Optimization

Run any project from this repo on cloud infrastructure with optimized AI model selection and minimal resource usage.

## What It Does

- **Model optimization**: Automatically downgrades expensive models (480B, 235B param) to efficient alternatives (30B, 8B param) while keeping the same Nebius Token Factory API
- **Resource limits**: Docker containers capped at 1 CPU / 512MB RAM
- **Unified deployment**: Single Dockerfile + compose file runs any project
- **Two tiers**: `minimal` (cheapest, uses smallest models) and `balanced` (mid-range models)

## Model Mapping

| Tier | Original Model | Optimized Model | Savings |
|------|---------------|----------------|---------|
| minimal | Qwen3-Coder-480B | Qwen3-30B-A3B | ~90% |
| minimal | Qwen3-235B-A22B | Qwen3-30B-A3B | ~85% |
| minimal | Qwen3.5-397B | Qwen3-30B-A3B | ~90% |
| minimal | Llama-3.1-70B | Llama-3.1-8B | ~80% |
| balanced | Qwen3-Coder-480B | Qwen3-235B-A22B | ~50% |
| balanced | Llama-3.1-70B | Llama-3.1-8B | ~80% |

## Quick Start

```bash
cd cloud_deploy
cp .env.example .env
# Edit .env with your NEBIUS_API_KEY

# Run locally
CLOUD_TIER=minimal python -m cloud_deploy.run starter_ai_agents/agno_starter

# Run with Docker
docker compose up --build

# Run a different project
PROJECT=rag_apps/chat_with_code docker compose up --build
```

## List Available Projects

```bash
python -m cloud_deploy.run --list
```

## Cloud Deployment (AWS/GCP/Azure)

### AWS ECS (Fargate) — Cheapest Option

```bash
# Build and push
docker build -t awesome-ai-apps -f cloud_deploy/Dockerfile .
docker tag awesome-ai-apps:latest <account>.dkr.ecr.<region>.amazonaws.com/awesome-ai-apps:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/awesome-ai-apps:latest

# Use task definition with:
#   CPU: 256 (0.25 vCPU)
#   Memory: 512 MB
#   Environment: NEBIUS_API_KEY, CLOUD_TIER=minimal, PROJECT=<your-project>
```

### Google Cloud Run

```bash
gcloud run deploy awesome-ai-apps \
  --source . \
  --dockerfile cloud_deploy/Dockerfile \
  --set-env-vars NEBIUS_API_KEY=$NEBIUS_API_KEY,CLOUD_TIER=minimal,PROJECT=starter_ai_agents/agno_starter \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 1
```

## Using Model Config in Your Code

```python
from cloud_deploy.model_config import get_optimized_model, get_model_config

# Swap a model for its optimized version
model = get_optimized_model("Qwen/Qwen3-Coder-480B-A35B-Instruct")
# Returns "Qwen/Qwen3-30B-A3B" when CLOUD_TIER=minimal

# Get full config
config = get_model_config()
print(config.base_url)        # Nebius Token Factory URL
print(config.default_model)   # Tier-appropriate default
print(config.inference_params) # Token limits, temperature
```
