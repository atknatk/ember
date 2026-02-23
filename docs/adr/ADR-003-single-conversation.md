# ADR-003: Single Continuous Conversation Per Character

| Field    | Value                    |
|----------|--------------------------|
| Date     | 2026-02-23               |
| Status   | Accepted                 |
| Deciders | Architecture Team        |
| Replaces | —                        |

---

## Context

Most LLM-powered chat interfaces (ChatGPT, Claude.ai, Gemini) use a session-based model:

- Users create new chat sessions.
- Each session has its own isolated history.
- Users can switch between sessions or start fresh.
- Sessions can be titled, renamed, and deleted.

This model is appropriate for productivity tools where users want task isolation:
"This session is about my resume. This other session is about my trip planning."

Ember is different. Ember is a personal AI companion. The product premise is:

> "Ember knows you. Ember remembers your conversations. Ember grows alongside you."

The fundamental question for Ember's architecture is: should users have one ongoing
relationship with each character, or should users be able to start fresh sessions?

---

## Decision

**Each user has exactly one continuous conversation per character, with no ability to
start new sessions.**

There is no "New Chat" button. The first message a user sends to a character creates
the conversation. All subsequent messages — across all app sessions, all devices, all time —
append to the same conversation.

---

## Reasons

### 1. Companion App Requires Relationship Continuity

The product differentiation of Ember over generic LLM chatbots is the sense of an ongoing
relationship. Relationship continuity requires:

- The character remembers previous conversations.
- The character can reference past events ("How did that job interview go?").
- The character tracks user growth over time.
- The emotional tone of the relationship evolves.

Session-based chat fundamentally breaks this. If a user can start a "new chat" with Luna,
Luna has no context about their previous conversations. The relationship resets. The product
value proposition is destroyed.

### 2. Mem0 Provides Long-Term Memory Within the Single Conversation Model

The practical concern with a single conversation is context window limits. An LLM can only
process a fixed number of tokens at once. A conversation that spans months or years will
far exceed any model's context window.

Mem0 solves this problem:

- After each exchange, Mem0 automatically extracts semantic memories from the conversation.
- Memories are stored with per-user, per-character isolation (`agent_id = {template_id}_{user_id}`).
- When building the LLM prompt, relevant memories are retrieved via semantic search.
- Only the last 30–50 messages are included as raw context.

The effective experience: the character "remembers everything" but the LLM only processes
the most relevant recent history plus extracted memories.

```
Prompt = system_prompt
       + top_10_relevant_memories (from Mem0)
       + last_50_messages (from conversation)
       + new_user_message
```

### 3. Simpler Data Model

The session-based model requires:

```
User → many Sessions → each Session → many Messages
```

API routing: `POST /sessions/:id/messages`

This creates questions:
- What session ID does the mobile app use after an app restart?
- How does the app know which session is "current"?
- Can the user have multiple active sessions simultaneously?
- When does a session expire?

The single-conversation model eliminates these questions:

```
User → many Characters → each Character → one Conversation → many Messages
```

API routing: `POST /characters/:id/messages`

The character ID is the only routing key needed. There is no session to manage.

### 4. Technical Implementation

#### Conversation Auto-Creation

```python
# In MessageService.send()
async def get_or_create_conversation(self, user_id: str, character_id: str) -> Conversation:
    result = await self.db.execute(
        select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.character_id == character_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        conversation = Conversation(user_id=user_id, character_id=character_id)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
    return conversation
```

This is called on every message. The first message creates the conversation.
All subsequent messages reuse it. No explicit conversation creation endpoint is needed.

#### Unique Constraint

```sql
CREATE UNIQUE INDEX conversations_user_character_unique
ON conversations (user_id, character_id);
```

The database enforces the one-per-user-per-character rule. A race condition where two
simultaneous first messages both try to create a conversation is handled by the unique
constraint — one will succeed, the other will get a conflict and retry with the existing
conversation.

#### Context Window Slice

Messages are paginated with cursor pagination. The LLM context always uses the most recent
N messages:

```python
# Get last 50 messages for LLM context (not cursor-paginated, just recent slice)
stmt = (
    select(Message)
    .where(Message.conversation_id == conversation.id)
    .order_by(Message.created_at.desc())
    .limit(50)
)
result = await self.db.execute(stmt)
recent_messages = list(reversed(result.scalars().all()))
```

The full history is still available through the cursor-paginated message list endpoint
for display in the UI. Only the LLM context is truncated to 50 messages.

---

## Consequences

### Positive

- Product differentiation: real relationship continuity, not isolated sessions.
- Simpler API: `POST /characters/:id/messages` — no session management.
- Simpler mobile state: no "current session ID" to track across app restarts.
- Simpler data model: one conversation row per (user, character) pair.
- Mem0 makes long-term memory practical within this model.

### Negative

- Users cannot isolate conversations by topic. A user cannot say
  "start a new chat about my work problems separate from my personal life."
- If a user wants to "reset" a character relationship, there is no built-in mechanism.
  (This is intentional: Ember is about continuity, not fresh starts.)
- The message history table will grow indefinitely for active users. Requires monitoring
  and potentially archiving old messages past a certain depth.

### Accepted Trade-offs

- The inability to start new sessions is a product feature, not a limitation.
  It enforces the relationship model.
- A "reset relationship" feature could be added as an explicit, deliberate user action
  in settings (not a casual "new chat" button). This is Phase 4+ scope.
- Message archiving after 10,000+ messages per conversation is a performance concern
  addressed in Phase 3 operations work.

---

## Alternatives Considered

### Session-Based Model (ChatGPT Style)

Rejected because:
- Destroys the relationship continuity that is Ember's core value proposition.
- Adds session management complexity to the API and mobile clients.
- Users will accidentally start new sessions, losing context and feeling confused.

### Session-Based with "Continue Previous" as Default

Considered: a model where the most recent session is automatically continued,
but users CAN start a new session.

Rejected because:
- "New session" is always one tap away. Users who want to reset WILL tap it.
- The UI must explain the difference, adding cognitive load.
- Mem0 memory would need to be cleared or scoped per session, complicating the
  memory architecture.
- It is a half-measure that provides neither clean isolation nor true continuity.

### Time-Window Sessions (Auto-Split After Inactivity)

Considered: automatically start a new conversation after 7 days of inactivity.

Rejected because:
- Breaks the relationship when the user returns after a vacation.
- Arbitrary threshold (7 days? 30 days?) has no product justification.
- Mem0 already handles long gaps in conversation by retaining extracted memories.
