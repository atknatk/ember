# ADR-004: Mem0.ai as the Memory Layer

| Field    | Value                    |
|----------|--------------------------|
| Date     | 2026-02-23               |
| Status   | Accepted                 |
| Deciders | Architecture Team        |
| Replaces | —                        |

---

## Context

Ember's single-conversation model (ADR-003) requires the AI to "remember" facts about
the user across a conversation that may span months or years. No LLM has a context window
large enough to include the entire conversation history in every prompt.

The memory problem has several dimensions:

1. **Extraction**: Which facts from the conversation are worth remembering long-term?
2. **Storage**: Where are memories stored? How are they indexed for retrieval?
3. **Retrieval**: Given a new user message, which stored memories are relevant?
4. **Deduplication**: If the user says "I live in Istanbul" in 10 different messages,
   should there be 10 memories or one?
5. **Updates**: If the user says "I moved to Ankara," does the old memory get replaced?
6. **Isolation**: User A's memories must never appear in User B's context.
7. **Per-character isolation**: Memories from a conversation with Luna should not appear
   in a conversation with Aria (unless explicitly designed otherwise).

The team evaluated building a custom memory system versus using Mem0.ai.

---

## Decision

**Use Mem0.ai as the managed memory layer for all character conversations.**

Mem0 is called after each user-assistant exchange to extract and store memories.
Before building the LLM prompt, relevant memories are retrieved from Mem0 via semantic search.

---

## Reasons

### 1. Automatic Semantic Memory Extraction

Building a custom memory extractor requires:

- Prompting an LLM to classify each message and decide what is worth remembering.
- Defining a schema for memories (entity, attribute, value? freeform text? vector?).
- Handling contradictions (user says one thing in message 100, opposite in message 500).
- Building an update/merge strategy for conflicting memories.

This is a substantial engineering investment with significant ML research involved.
Mem0 has already solved this problem. Its extraction pipeline:

- Processes the conversation in context.
- Identifies factual claims, preferences, and important events.
- Classifies them semantically.
- Automatically resolves conflicts by updating existing memories rather than duplicating.

The quality of Mem0's extraction is validated by its production customers and is
continuously improved by the Mem0 team.

### 2. Per-User Per-Character Isolation via agent_id

Mem0's data model supports two levels of isolation out of the box:

```python
await client.add(
    messages=messages,
    user_id=user_id,            # isolates by user
    agent_id=f"{template_id}_{user_id}",  # isolates by user+character
)
```

The `agent_id` pattern `{template_id}_{user_id}` ensures:

- User A's Luna memories (`luna_user_a`) are completely separate from User B's Luna memories (`luna_user_b`).
- User A's Luna memories (`luna_user_a`) are separate from User A's Aria memories (`aria_user_a`).
- No cross-contamination is possible at the API level.

Building this isolation in a custom system requires careful multi-tenant database design.
Mem0 provides it as a first-class feature.

### 3. Managed Service (Self-Hosting Option Available)

Mem0 is a managed cloud service, which means:

- No infrastructure to operate.
- No vector database to provision and maintain.
- No embedding model to host.
- API availability SLA provided by Mem0.

Critically, Mem0 is open-source and supports self-hosting via Docker. If the managed
service becomes too expensive, unavailable, or unsuitable at scale, the team can:

1. Deploy Mem0 on EC2 or ECS.
2. Point `AsyncMemoryClient` at the self-hosted URL.
3. No application code changes required.

This exit strategy is available without changing any business logic.

### 4. Handles Memory Conflicts and Updates Automatically

When a user's situation changes, their memories should update:

- User says "I have a dog named Max" → memory created.
- User says "My dog Max passed away last week" → memory updated, emotional context preserved.
- User says "I'm 28 years old" → memory created.
- 2 years later: "I just turned 30" → age memory updated.

Building a conflict resolution and update strategy from scratch is non-trivial. Mem0's
extraction pipeline handles this automatically using its own LLM-based reasoning layer.

### 5. Integration Simplicity

The Mem0 Python client integrates in under 50 lines of code:

```python
from mem0 import AsyncMemoryClient

client = AsyncMemoryClient(api_key=settings.mem0_api_key)

# After each exchange
await client.add(
    messages=[
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_reply},
    ],
    user_id=user_id,
    agent_id=f"{template_id}_{user_id}",
)

# Before building LLM prompt
memories = await client.search(
    query=user_message,
    user_id=user_id,
    agent_id=f"{template_id}_{user_id}",
    limit=10,
)
```

A custom vector memory system would require: embedding model selection, vector DB setup,
extraction prompt engineering, conflict resolution logic, and retrieval ranking. This is
weeks of work versus a one-day Mem0 integration.

---

## Implementation Details

### agent_id Format (Canonical)

```
{template_id}_{user_id}

luna_550e8400-e29b-41d4-a716-446655440000
aria_550e8400-e29b-41d4-a716-446655440000
```

This format is defined in `docs/standards/common.md` and enforced in code via:

```python
def agent_id(template_id: str, user_id: str) -> str:
    return f"{template_id}_{user_id}"
```

Never construct `agent_id` inline — always call this function.

### Memory Timing

Memory extraction runs **after** the assistant response is sent to the user, not before.
This is done asynchronously to avoid adding latency to the response:

```python
async def send_message(self, user_id, character_id, content):
    # 1. Retrieve memories (parallel with history fetch)
    memories, history = await asyncio.gather(
        self.memory_svc.search(query=content, user_id=user_id, template_id=template_id),
        self.get_recent_messages(character_id, user_id),
    )

    # 2. Build prompt with memories + history
    response = await self.llm.complete(system=system_prompt, messages=context_messages)

    # 3. Save message to DB
    await self.save_message(...)

    # 4. Async memory update (fire and forget — do not await in response path)
    asyncio.create_task(
        self.memory_svc.add(
            messages=[
                {"role": "user", "content": content},
                {"role": "assistant", "content": response},
            ],
            user_id=user_id,
            template_id=template_id,
        )
    )

    return response
```

Memory extraction is fire-and-forget in the response path. A failure to update Mem0
does not fail the user's message.

### Memory Display

Users can view their memories in the app's character settings screen. This calls:

```python
await client.get_all(user_id=user_id, agent_id=agent_id(template_id, user_id))
```

Users can delete individual memories. This calls:

```python
await client.delete(memory_id=memory_id)
```

---

## Consequences

### Positive

- Zero infrastructure to operate for memory functionality.
- Automatic conflict resolution and update logic.
- Per-user per-character isolation is a built-in API feature.
- Self-hosting migration path exists without code changes.
- Fast integration: < 1 day to wire up.
- Semantic search quality is continuously improved by Mem0.

### Negative

- External dependency: if Mem0 API is unavailable, memory retrieval degrades gracefully
  (empty memories → no crash, but character context quality degrades).
- API rate limits from Mem0 may require throttling at high volume.
- Per-API-call cost: each memory search and add call is billed.
- Limited control over extraction logic — cannot tune what Mem0 chooses to remember.

### Accepted Trade-offs

- Memory extraction quality is "good enough" for an initial product. If specific
  extraction behavior needs tuning in Phase 3+, the self-hosted Mem0 option allows
  configuration of the extraction prompt.
- At 100,000 active users sending 10 messages/day, Mem0 API costs are estimated at
  $X/month (to be validated against Mem0 pricing).
- Graceful degradation: Mem0 failures are caught and logged, but do not fail the message
  delivery. The character continues the conversation without the missing memories.

---

## Alternatives Considered

### Custom Vector Memory System

Build our own: extract memories with an LLM prompt → embed with OpenAI → store in pgvector →
retrieve with cosine similarity → merge conflicts with another LLM prompt.

Rejected because:
- 3–4 weeks of engineering effort for functionality that Mem0 provides in 1 day.
- The conflict resolution and update logic is the hardest part, and it requires ongoing tuning.
- We would be maintaining an ML pipeline rather than building product features.
- Not a core competency of the Ember team.

### LangChain Memory

LangChain's memory modules provide `ConversationSummaryMemory`, `VectorStoreRetrieverMemory`, etc.

Rejected because:
- LangChain abstractions are designed for chain/agent workflows, not standalone memory.
- LangChain's memory modules do not handle multi-user isolation cleanly.
- The LangChain ecosystem is large and introduces many transitive dependencies.
- Mem0 is purpose-built for exactly this use case.

### Storing Full Conversation + Sliding Window Only

Use only the last N messages as context, no extracted memories.

Rejected because:
- After a few weeks of daily conversations, the 50-message window loses important context.
- Character cannot reference events from a month ago.
- Breaks the relationship continuity that is Ember's product promise.
- Addressed in ADR-003 rationale.
