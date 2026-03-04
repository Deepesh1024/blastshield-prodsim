# BlastShield — Production Failure Simulator

> SRE-grade failure simulation for Python projects. Powered by AWS Lambda, Bedrock, and Docker sandboxing.

## Architecture

```
User / Frontend
      │
      ▼
API Gateway (HTTP API)
      │
      ▼
Lambda Orchestrator (FastAPI + Mangum)
      │
      ├── Upload artifact → S3 (blastshield-artifacts)
      │
      ├── Run simulation drills (concurrency, latency, chaos)
      │
      └── POST /run-sandbox → EC2 Sandbox Server
                        │
                        ▼
              Docker Container (read-only, no-network)
                        │
                        ▼
              Runtime errors + logs + Groq AI analysis
                        │
                        ▼
                returned to Lambda
                        │
                        ▼
        Lambda calls Bedrock (Nova Pro / Claude)
                        │
                        ▼
               Final structured result
```

## Project Structure

```
blastshield-agent/
├── app/                          # Lambda code
│   ├── api/scan.py               # Orchestrator endpoint
│   ├── core/drills.py            # Concurrency, latency, chaos drills
│   ├── core/edge_cases.py        # Edge case testing
│   ├── core/curl_runner.py       # Simulated load tests
│   ├── core/s3_storage.py        # S3 artifact upload
│   ├── core/ec2_client.py        # EC2 sandbox HTTP client
│   ├── core/extract.py           # Code/zip extraction
│   ├── ai/bedrock.py             # Bedrock + Groq AI client
│   └── ai/prompt.py              # Prompt builder
├── ec2_sandbox/                  # EC2 server (NOT in Lambda zip)
│   ├── server.py                 # FastAPI sandbox server
│   ├── docker_runner.py          # Docker execution engine
│   ├── groq_analyzer.py          # Groq AI error analysis
│   ├── runner.py                 # Runs INSIDE Docker container
│   ├── Dockerfile                # Docker image definition
│   └── requirements.txt          # EC2 dependencies
├── handler.py                    # Lambda entry point (Mangum)
├── serverless.yml                # Lambda deployment config
├── requirements.txt              # Lambda dependencies
└── .env                          # Environment variables (not in git)
```

## Quick Start

### Lambda (Local)

```bash
# Install deps
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Set env vars
export $(cat .env | xargs)

# Run
uvicorn app.main:app --port 8000

# Test
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "from fastapi import FastAPI\napp = FastAPI()\n@app.get(\"/health\")\ndef health():\n    return {\"ok\": True}"}'
```

### EC2 Sandbox Server

```bash
# On EC2 instance
cd ec2_sandbox
pip install -r requirements.txt

# Build Docker image
docker build -t blastshield-runner .

# Run server
export GROQ_API_KEY="your-key"
export AWS_REGION="us-east-1"
python server.py
# Runs on port 9000
```

### Lambda (AWS Deploy)

```bash
# Package
pip install -r requirements.txt -t /tmp/pkg --platform manylinux2014_aarch64 --python-version 3.13 --implementation cp --only-binary=:all:
cp -r app handler.py /tmp/pkg/
cd /tmp/pkg && zip -r ~/Desktop/blastshield-deploy.zip .

# Upload to Lambda via AWS Console
# Set env vars in Lambda Configuration
```

## API

### `POST /scan`

Accepts Python code or a .zip file:

```bash
# JSON code string
curl -X POST https://your-api/scan \
  -H "Content-Type: application/json" \
  -d '{"code": "..."}'

# Zip file upload
curl -X POST https://your-api/scan \
  -F "file=@project.zip"
```

**Response:**

```json
{
  "scan_id": "uuid",
  "overall_score": 45,
  "simulation_results": {
    "files": [...],
    "endpoints": [...],
    "drills": { "concurrency": [...], "latency": [...], "chaos": [...] },
    "edge_cases": [...],
    "curl_results": [...]
  },
  "deployment_validation": {
    "deployment_status": "success|failure|timeout",
    "runtime_errors": [],
    "logs": "...",
    "container_exit_code": 0
  },
  "ai_analysis": {
    "timeline": "...",
    "outage_scenario": "...",
    "blast_radius": "...",
    "patches": [...]
  },
  "s3_artifact": { "bucket": "...", "key": "..." }
}
```

### `GET /health`

```bash
curl https://your-api/health
# {"status": "ok"}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API Key (bearer token) |
| `GROQ_API_KEY` | Groq API key for AI analysis |
| `AWS_REGION` | AWS region (default: `us-east-1`) |
| `S3_BUCKET` | S3 bucket for artifacts (default: `blastshield-artifacts`) |
| `EC2_SANDBOX_URL` | EC2 sandbox server URL (default: `http://localhost:9000`) |

## IAM Policies

### Lambda Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::blastshield-artifacts/*"
    }
  ]
}
```

### EC2 Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::blastshield-artifacts/*"
    }
  ]
}
```

## Docker Security Controls

| Control | Limit |
|---------|-------|
| CPU | 1 core |
| Memory | 512 MB |
| PIDs | 64 |
| Network | Disabled |
| Filesystem | Read-only |
| Temp storage | 64 MB tmpfs |
| Timeout | Configurable (default 10s) |

## EC2 Setup (Full)

```bash
# 1. Launch EC2 (Amazon Linux 2023, t3.small)
# 2. Install Docker
sudo yum install -y docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

# 3. Clone and setup
git clone https://github.com/Deepesh1024/blastshield-prodsim.git
cd blastshield-prodsim/ec2_sandbox
pip install -r requirements.txt

# 4. Build runner image
docker build -t blastshield-runner .

# 5. Configure
export AWS_REGION=us-east-1
export GROQ_API_KEY="your-key"

# 6. Run
python server.py
# Server runs on port 9000

# 7. Open port 9000 in Security Group
```

## Model Cascade

```
1. Amazon Nova Pro (Bedrock) ✅ primary
2. Anthropic Prompt Router (Bedrock) — fallback
3. Groq openai/gpt-oss-120b — final fallback
4. Static fallback — safety net
```
