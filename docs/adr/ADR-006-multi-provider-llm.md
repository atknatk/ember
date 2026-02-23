# ADR-006: Multi-Provider LLM Architecture

| Field    | Value                    |
|----------|--------------------------|
| Date     | 2026-02-23               |
| Status   | Accepted                 |
| Deciders | Architecture Team        |
| Replaces | —                        |

---

## Context

Ember's core functionality is AI conversation. The quality of conversations depends directly
on the Large Language Model powering them. The team must decide:

1. Should the backend be locked to a single LLM provider?
2. If not, how should the abstraction be structured?
3. Which provider should be the default?
4. Which model within a provider should be used, and for what tasks?

The primary providers evaluated:

- **Anthropic Claude** — Claude Sonnet 4.6, Claude Haiku 3.5, Claude Opus 4.6
- **OpenAI** — GPT-4o, GPT-4o-mini, o3-mini
- **Google** — Gemini 2.0 Flash, Gemini 2.0 Pro
- **Meta** — Llama 3.3 70B (via AWS Bedrock or self-hosted)

---

## Decision

**Implement a multi-provider LLM abstraction. Default provider is Anthropic Claude.
The provider is configurable via environment variable (`LLM_PROVIDER`).**

All LLM calls go through a `LLMProvider` abstract interface. Concrete implementations
exist for Claude and OpenAI (Phase 1). Gemini and Llama are Phase 2 additions.

The default model routing:

| Task                        | Default Model            | Reason                         |
|-----------------------------|--------------------------|--------------------------------|
| Main conversation           | claude-sonnet-4-6        | Best personality, nuance       |
| Fast/cheap classification   | claude-haiku-3-5         | Low latency, low cost          |
| Long document analysis      | claude-sonnet-4-6        | 200K context window            |
| Fallback (Claude down)      | gpt-4o                   | Strong alternative             |

---

## Reasons

### 1. Provider Risk Mitigation

A single-provider architecture creates a single point of failure:

- API outages affect all users.
- Price increases have no leverage.
- Policy changes (e.g., content moderation tightening) may block certain Ember use cases.
- Provider discontinuing a model requires emergency migration.

With a multi-provider abstraction, switching providers requires changing one environment
variable (`LLM_PROVIDER=openai`). No application code changes.

This has already proven valuable in practice: Anthropic had a documented API degradation
in November 2024 that lasted several hours. With provider switching, this would have been
a < 1 minute operational response rather than a user-facing outage.

### 2. Cost Optimization Options

LLM API pricing changes frequently. Different providers offer different price-performance
trade-offs at different points in time.

The multi-provider architecture allows:

- Routing cheap tasks (e.g., classifying message sentiment) to the cheapest model (Haiku).
- Routing quality-sensitive tasks (main conversation) to the best model (Sonnet).
- Switching the default provider if a competitor offers significantly better pricing.

Example cost breakdown for 100,000 DAU each sending 10 messages/day:
- 1,000,000 messages/day × average 500 tokens each = 500M tokens/day
- At Sonnet pricing: X per million tokens (varies — check current pricing)
- At Haiku pricing: 5–10x cheaper for applicable tasks

Cost optimization without multi-provider requires hardcoded provider-specific logic.
With multi-provider, it is a routing configuration.

### 3. Different Models for Different Tasks

The best model for one task is not the best model for all tasks. Examples:

| Task                               | Optimal Choice    | Reason                                    |
|------------------------------------|-------------------|-------------------------------------------|
| Character conversation (emotional) | Claude Sonnet     | Superior emotional intelligence, nuance   |
| Classify message intent (fast)     | Claude Haiku      | 10x faster, 10x cheaper for simple tasks  |
| Summarize long conversation        | Claude Sonnet     | Long context, high quality                |
| Generate short acknowledgment      | Haiku or GPT-4o-mini | Sub-500ms latency possible            |
| Complex reasoning / roleplay       | Claude Opus       | Best quality at higher cost               |

The `LLMProvider` abstraction + model configuration allows different routes or tasks
to specify which model to use:

```python
# In config
CLAUDE_CONVERSATION_MODEL = "claude-sonnet-4-6"
CLAUDE_FAST_MODEL = "claude-haiku-3-5"

# In LLM service
async def complete_fast(self, ...) -> str:
    # Use Haiku for fast/cheap operations
    return await self._complete(model=settings.claude_fast_model, ...)

async def complete(self, ...) -> str:
    # Use Sonnet for main conversations
    return await self._complete(model=settings.claude_conversation_model, ...)
```

### 4. Why Claude is the Default

Anthropic Claude is chosen as the default for Ember's core conversation use case because:

**Emotional Intelligence**: Claude's training emphasizes nuanced, empathetic responses.
For a companion app, the character's emotional intelligence directly affects user satisfaction.
Claude Sonnet 4.6 consistently outperforms GPT-4o on empathy, emotional support, and
character roleplay benchmarks in internal testing.

**Instruction Following**: Claude reliably follows system prompts that define a character's
personality, backstory, and conversational style. Character consistency is a core product
requirement. Claude's instruction following is measurably more reliable than alternatives
for complex, multi-constraint system prompts.

**Context Window**: Claude Sonnet 4.6 has a 200,000 token context window. This allows
including more conversation history and memories in the prompt without truncation.

**Safety**: Anthropic's safety training is calibrated for meaningful emotional conversations.
GPT-4o's RLHF training sometimes produces more conservative responses that break character
immersion.

**API Reliability**: Anthropic's API has maintained high uptime in 2025–2026.

### 5. Provider Abstraction Design

```python
# app/services/llm_service.py
from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """Abstract interface for all LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> str:
        """Non-streaming completion."""
        ...

    @abstractmethod
    async def stream(
        self,
        system: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> AsyncIterator[str]:
        """Streaming completion — yields text chunks."""
        ...
```

This interface is minimal and covers 100% of Ember's LLM needs. Adding a new provider
means implementing two methods.

The `LLMRouter` extends this to support model-level routing:

```python
class LLMRouter:
    """Routes to different providers/models based on task type."""

    def __init__(self, config: Settings):
        self.providers: dict[str, LLMProvider] = {}
        if config.anthropic_api_key:
            self.providers["claude"] = ClaudeProvider(config)
        if config.openai_api_key:
            self.providers["openai"] = OpenAIProvider(config)

        self.default = config.llm_provider  # "claude" by default

    def get(self, provider: str | None = None) -> LLMProvider:
        name = provider or self.default
        if name not in self.providers:
            raise ValueError(f"Provider '{name}' not configured")
        return self.providers[name]
```

---

## Model Version Policy

Model versions are pinned in config, not hardcoded in service code:

```python
# app/config.py
class Settings(BaseSettings):
    llm_provider: str = "claude"

    # Claude models
    claude_conversation_model: str = "claude-sonnet-4-6"
    claude_fast_model: str = "claude-haiku-3-5"

    # OpenAI models (fallback)
    openai_conversation_model: str = "gpt-4o"
    openai_fast_model: str = "gpt-4o-mini"
```

**Rules for model version updates:**

1. Never change a model version in code without a staged rollout.
2. A/B test new model versions before full rollout.
3. Monitor conversation quality metrics (user engagement, session length) for regressions.
4. Document model version changes in CHANGELOG.

---

## Consequences

### Positive

- Provider outages can be mitigated by switching `LLM_PROVIDER` environment variable.
- Cost optimization by routing cheap tasks to cheaper models.
- New providers can be added by implementing two methods.
- Claude's emotional intelligence is the best available for a companion app.
- Model version updates are configuration changes, not code changes.

### Negative

- Two provider implementations to maintain (Claude + OpenAI at minimum).
- Provider-specific features (function calling, vision, etc.) require provider-specific
  code paths or are abstracted away.
- Streaming response format differs between providers — the abstraction handles this,
  but it adds complexity.
- Testing requires mocking multiple providers.

### Accepted Trade-offs

- The `LLMProvider` abstraction does not expose provider-specific features (e.g.,
  Anthropic's extended thinking, OpenAI's structured outputs). Features that require
  provider-specific APIs use the provider client directly and are not routed through
  the abstraction. These are rare and explicitly documented.
- The abstraction may not support every new model capability immediately.
  Provider-specific capabilities are added to the abstraction when they become
  cross-provider standards.

---

## Alternatives Considered

### Locked to Anthropic Only

Rejected because:
- Single point of failure for outages, pricing, and policy changes.
- No cost optimization path for fast/cheap tasks.
- Not significantly simpler (two methods vs. the provider interface).

### OpenAI as Default

Considered. OpenAI GPT-4o is a strong model.

Rejected as default because:
- In internal A/B testing on emotionally sensitive companion conversations, Claude
  Sonnet produced measurably higher user satisfaction scores.
- Character instruction following is more reliable with Claude for complex system prompts.
- OpenAI remains the first fallback provider.

### LangChain LLM Abstraction

LangChain provides a unified `LLM` interface for multiple providers.

Rejected because:
- LangChain is a large dependency that brings many abstractions the team does not need.
- LangChain's streaming interface (`callbacks`) is less ergonomic than `async for chunk`.
- LangChain's model interface is designed for chain/agent patterns, not simple completion.
- The team's thin `LLMProvider` interface covers 100% of Ember's needs in < 100 lines.
  LangChain brings thousands of lines of dependencies for the same result.

### AWS Bedrock for All Models

AWS Bedrock provides a unified API for Claude, Llama, Titan, and other models hosted on AWS.

Considered as a Phase 3 addition for Llama and self-hosted model support.

Not used as the primary Claude interface because:
- Direct Anthropic API has lower latency (one fewer hop).
- Anthropic API provides features not yet available on Bedrock.
- Bedrock's Claude pricing is slightly higher than direct API at Ember's expected volume.

Bedrock remains a valid option for Llama 3.3 70B access in later phases.
