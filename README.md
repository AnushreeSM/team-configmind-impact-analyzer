# ConfigMind — AI-Powered Impact Analyzer

ConfigMind is an AI-powered impact analysis tool that intercepts admin configuration changes, estimates their blast radius across downstream services, and surfaces risk-level recommendations before destructive actions are confirmed.

---

## Overview

When an admin makes a configuration change — moving a group, toggling a feature, adjusting a threshold — ConfigMind analyzes the scope of impact in real time. It queries live downstream services using the admin's own auth token and uses an AWS Bedrock agentic loop to reason about cascading effects.

**Key capabilities:**
- Blast radius estimation across groups, users, vehicles, devices, and safety events
- Workflow and device settings cascade detection
- PCS (Program Configuration Service) feature dependency analysis
- Known bug detection (e.g., VOYAGE-1988: removing one group deletes behavior for all)
- Risk-level recommendations with structured impact reports

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| AI Agent | AWS Bedrock (Claude Sonnet 4.6) |
| Auth | Bearer token forwarded to all downstream calls |
| Config | Python dotenv |
| HTTP Client | HTTPX |
| Data Validation | Pydantic v2 |

---

## Project Structure

```
ConfigMind/
├── configmind/
│   ├── agent/
│   │   ├── bedrock_agent.py   # Bedrock agentic loop
│   │   └── prompts.py         # System prompts
│   ├── models/
│   │   └── impact.py          # Pydantic request/response models
│   ├── tools/
│   │   ├── definitions.py     # Tool schemas for Bedrock
│   │   └── dispatcher.py      # Tool execution handlers
│   ├── app.py                 # FastAPI application
│   ├── config.py              # Environment config
│   └── recommendations.py     # Recommendation engine
├── knowledge/
│   ├── ontology.yaml          # Change type ontology
│   └── known_bugs.yaml        # Known bug registry
├── recommendations/
│   ├── recommendation_engine.py
│   └── recommendation_data.json
├── tests/
│   └── payloads/              # Example request payloads
├── .env.example               # Environment variable template
├── requirements.txt
└── run.py                     # Server entrypoint
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- AWS account with Bedrock access (Claude Sonnet 4.6)
- Valid auth token for downstream Lytx services

### Installation

```bash
# Clone the repo
git clone https://github.com/AnushreeSM/team-configmind-impact-analyzer.git
cd team-configmind-impact-analyzer/ConfigMind

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # macOS/Linux
.venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and fill in your AWS credentials and service URLs
```

### Running the Server

```bash
python run.py
```

Server starts at `http://localhost:8000`
Interactive API docs at `http://localhost:8000/docs`

---

## API Reference

### `POST /analyze`

Analyze the blast radius of a proposed configuration change.

**Headers:**
```
Authorization: Bearer <your-token>
Content-Type: application/json
```

**Example request:**
```bash
curl -X POST http://localhost:8000/analyze \
     -H "Authorization: Bearer <your-token>" \
     -H "Content-Type: application/json" \
     -d @tests/payloads/move_group.json
```

**Returns:** Structured `ImpactReport` with risk level, affected counts, and recommendations.

### `GET /health`

Returns service health status and downstream tool endpoints.

### `GET /demos`

Lists available example payloads with descriptions.

---

## Example Scenarios

| Scenario | Change Type | Description |
|---|---|---|
| Move Group | `groups.move_group` | 18 downstream services notified via Kafka |
| Add to Fatigue | `groups.fatigue.add_group` | Workflow shared with N groups — all get new behavior |
| Remove from Fatigue | `groups.fatigue.remove_group` | Bug: removes behavior for ALL groups on workflow |
| Enable PCS Sub-Feature | `pcs.enable_sub_feature` | Cascades to device settings + group options + workflow |
| Disable PCS Sub-Feature | `pcs.disable_sub_feature` | Shared prerequisite — may break 6 in-cab features |
| Change Alert Threshold | `pcs.change_threshold` | Lower threshold increases event volume |

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description |
|---|---|
| `LYTX_ENV` | Environment (`dev`, `staging`, `prod`) |
| `BEDROCK_REGION` | AWS region for Bedrock |
| `BEDROCK_MODEL_ID` | Bedrock model ID |
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `AWS_SESSION_TOKEN` | AWS session token (if using temporary credentials) |
| `GROUP_API_URL` | Lytx Group API base URL |
| `DEVICE_SETTINGS_URL` | Device Settings API base URL |
| `WORKFLOW_URL` | Workflow Admin API base URL |
| `HTTP_TIMEOUT` | HTTP request timeout in seconds |

---

## Team

| Name | Role |
|---|---|
| Anushree SM | Developer |
| Nisha | Developer |
| Bhoomika SB | Developer |
| Monisha Rajendran | Developer |

---

## License

Internal project — Lytx Hackathon.
