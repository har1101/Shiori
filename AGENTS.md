# Shiori Agent Project

## Project Overview

We developed an agent using Amazon Bedrock AgentCore and the Strands Agents SDK that integrates with Slack to automatically collect and store technical outputs such as blog posts and presentation materials. It ingests messages from designated channels, follows embedded URLs to evaluate their content, and saves the results as structured data in Aurora DSQL.

## Working Directions

* Perform reasoning in English, but provide responses in Japanese.
* Prepare both English and Japanese versions for source code comments and documentation.
* Before starting any task, always conduct sufficient research using MCP and web search.
