# Shiori

**Shiori** is an intelligent multi-agent system designed to automatically collect, analyze, and bookmark technical outputs from Slack channels. The name "Shiori" (栞) means "bookmark" in Japanese, reflecting the system's purpose of helping users easily record and organize their technical achievements like placing bookmarks in a book.

## 🔖 Project Overview

Shiori leverages Amazon Bedrock AgentCore and the Strands Agents SDK to create a seamless workflow for:

- Collecting technical content URLs from designated Slack channels
- Extracting and summarizing content using AI agents
- Storing structured data in Amazon Aurora DSQL
- Providing an intuitive Streamlit-based web interface

## 🏗️ Architecture

### Multi-Agent System

- **Slack Agent**: Retrieves messages and URLs from specified Slack channels
- **Web Content Agent**: Extracts and analyzes content using Firecrawl
- **AWS Level Assessment Agent**: Evaluates technical complexity and AWS service usage

### Core Components

- **Frontend**: Streamlit-based chat interface (`frontend_app.py`)
- **Agent Graph**: Multi-agent orchestration (`agent_graph/shiori_agent_graph.py`)
- **Data Access Layer**: Aurora DSQL integration (`agent_graph/data_access/dsql_client.py`)
- **Database Schema**: Structured data storage (`sql/create_tables_output_history.sql`)

## 🚀 Getting Started

### Prerequisites

1. **Install uv package manager**

   ```bash
   # Install uv if not already installed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Set up Amazon Aurora DSQL**
   - Create an Aurora DSQL cluster and IAM Role(for access your cluster) in your AWS account
   - Follow the setup guide: https://qiita.com/har1101/items/7dd1a6d803e48e3e0525
   - Execute the SQL schema from `sql/create_tables_output_history.sql`

3. **Set up Bedrock AgentCore Gateway & Identity**
   - Create an AgentCore Gateway(for Slack MCP)
   - Create some AgentCore Identity(for AgentCore Gateway & Langfuse)
   - Follow the setup guide:
     - https://qiita.com/har1101/items/aae967fa157b01e414a9
     - https://qiita.com/har1101/items/73165084bc6ec5c64290

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/har1101/Shiori.git
   cd Shiori
   ```

2. **Set up Python virtual environment**

   ```bash
   uv venv
   cd agent_graph
   uv pip install -r requirements.txt
   ```

3. **Install additional dependencies**

   ```bash
   uv pip install bedrock-agentcore-starter-toolkit streamlit
   ```

4. **Configure AgentCore**

   ```bash
   cd agent_graph
   agentcore configure
   ```

5. **Launch AgentCore with environment variables**

   ```bash
   agentcore launch \
     --env LANGFUSE_PUBLIC_KEY_SECRET_ID=langfuse-public-key
     --env LANGFUSE_SECRET_KEY_SECRET_ID=langfuse-secret-key \
     --env DISABLE_ADOT_OBSERVABILITY=true \
     --env LANGFUSE_HOST=https://us.cloud.langfuse.com \
     --env COGNITO_SCOPE=<scope> \
     --env GATEWAY_URL=https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp \
     --env PROVIDER_NAME=<AgentCore Identity Provider Name> \
     --env SLACK_CHANNEL=<Slack Channel ID>
     --env AURORA_DSQL_CLUSTER_ENDPOINT=<Cluster ID>.dsql.<region>.on.aws \
     --env AURORA_DSQL_DATABASE_USER=<DB User Name>
   ```

6. **Start the frontend application**

   ```bash
   # From project root
   streamlit run frontend_app.py
   ```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SLACK_CHANNEL` | Target Slack channel ID | `C*********` |
| `DSQL_ENDPOINT` | Aurora DSQL cluster endpoint | `your-cluster.dsql.region.on.aws` |
| `LANGFUSE_HOST` | Langfuse observability endpoint | `https://us.cloud.langfuse.com` |

### Database Setup

Execute the SQL schema in Aurora DSQL:

```bash
psql -h your-dsql-endpoint -U admin -d postgres -f sql/create_tables_output_history.sql
```

## 📊 Features

### Intelligent Content Collection

- Automatically monitors specified Slack channels
- Extracts URLs from messages containing technical content
- Filters relevant technical outputs (blog posts, presentations, documentation)

### AI-Powered Analysis

- Content summarization using advanced language models
- AWS service usage assessment and technical level evaluation
- Structured data extraction from web content

### Streamlit Web Interface

- Real-time chat interface for interacting with the agent system
- Visual progress tracking and execution statistics
- Structured response formatting with expandable details

### Data Management

- Persistent storage in Amazon Aurora DSQL
- Comprehensive activity tracking and monthly reporting
- Processing history and error logging

## 🛠️ Technology Stack

- **Framework**: Amazon Bedrock AgentCore, Strands Agents SDK
- **Database**: Amazon Aurora DSQL
- **Frontend**: Streamlit
- **Language**: Python 3.9+
- **Observability**: Langfuse
- **Protocols**: MCP (Model Context Protocol)

## 📁 Project Structure

```text
Shiori/
├── agent_graph/                 # Core agent system
│   ├── agents/                  # Agent implementations
│   │   ├── slack_agent_factory.py
│   │   ├── web_agent_factory.py
│   │   └── nodes/               # Custom node implementations
│   ├── data_access/             # Database access layer
│   │   └── dsql_client.py
│   ├── requirements.txt         # Python dependencies
│   └── shiori_agent_graph.py    # Main agent graph
├── sql/                         # Database schema
│   └── create_tables_output_history.sql
├── docs/                        # Documentation
├── frontend_app.py              # Streamlit frontend
└── README.md                    # This file
```

## 📚 Reference Documentation

- [Bedrock AgentCore Setup Guide](https://qiita.com/har1101/items/aae967fa157b01e414a9)
- [Aurora DSQL Configuration](https://qiita.com/har1101/items/7dd1a6d803e48e3e0525)
