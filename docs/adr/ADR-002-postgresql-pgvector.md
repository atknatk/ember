# ADR-002: PostgreSQL + pgvector as the Primary Database

| Field    | Value                    |
|----------|--------------------------|
| Date     | 2026-02-23               |
| Status   | Accepted                 |
| Deciders | Architecture Team        |
| Replaces | —                        |

---

## Context

Ember requires a database that can:

1. Store structured relational data: users, characters, conversations, messages.
2. Support semantic (vector) similarity search for memory retrieval.
3. Provide ACID guarantees for message ordering and consistency.
4. Scale efficiently with cursor-based pagination on time-series message data.
5. Integrate cleanly with SQLAlchemy async and Alembic migrations.

The team evaluated:

- **PostgreSQL + pgvector** — relational DB with vector extension.
- **MongoDB** — document database with Atlas Vector Search.
- **DynamoDB** — AWS-managed NoSQL, no native vector search.
- **Pinecone** — dedicated vector database (no relational data).
- **Supabase** — managed PostgreSQL + pgvector (hosted).
- **Qdrant** — dedicated vector database.

---

## Decision

**Use PostgreSQL 16 with the pgvector extension.**

- Relational data (users, messages, conversations, characters): standard PostgreSQL tables.
- Vector similarity search (memory retrieval backup): pgvector `vector` column type.
- Primary memory layer: Mem0 (see ADR-004). pgvector is retained as a local fallback
  and for direct embedding queries where Mem0 API is unsuitable.
- Deployment: AWS RDS PostgreSQL 16 with pgvector enabled, or self-hosted on EC2.

---

## Reasons

### 1. Production Validation at Scale

OpenAI uses PostgreSQL + pgvector for storing and retrieving embeddings at 800+ million
user scale. This is the most credible production proof for this architecture.

The pgvector 0.8.0 release (2024) added HNSW (Hierarchical Navigable Small World) indexing,
which delivers approximate nearest-neighbor search at sub-10ms latency for millions of
vectors. This is production-ready for Ember's expected scale.

### 2. ACID Compliance for Message Ordering

Chat messages have strict ordering requirements:

- A message sent at `T` must always appear after messages sent before `T`.
- Conversation history must be consistent — no phantom reads between pagination cursors.
- If a transaction fails (e.g., LLM call fails), the partial message must not be committed.

PostgreSQL's ACID transactions and MVCC (Multi-Version Concurrency Control) guarantee these
properties. MongoDB's transactions exist but are significantly less battle-tested under
high-concurrency write workloads.

DynamoDB provides eventual consistency by default; strong consistency requires additional
configuration and adds latency.

### 3. Cursor Pagination Simplicity

Ember's message pagination uses `(created_at, id)` as the cursor. The query is:

```sql
SELECT * FROM messages
WHERE user_id = $1
  AND character_id = $2
  AND (created_at, id) < ($cursor_ts, $cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT 31;
```

This query benefits from a standard B-tree index on `(user_id, character_id, created_at DESC, id DESC)`.
PostgreSQL's query planner handles this extremely efficiently.

DynamoDB requires careful primary key and sort key design to support this access pattern,
and does not support `ORDER BY` natively — sorting must be handled in application code
or via a secondary GSI that adds cost and complexity.

MongoDB's cursor pagination requires careful use of `$lt` on `_id` or a custom cursor field;
it works, but is less natural than PostgreSQL's row comparisons.

### 4. Single Data Store

Using one database for both relational and vector data simplifies operations:

- One backup strategy.
- One monitoring setup (CloudWatch RDS metrics).
- One migration tool (Alembic).
- One connection pool.
- Transactions can span relational and vector operations atomically.

A separate Pinecone or Qdrant instance would require:
- A second connection pool.
- Dual-write logic (write to Postgres AND vector DB).
- Dual-read logic (query Postgres AND vector DB).
- Data consistency management between two stores.

### 5. SQLAlchemy Integration

SQLAlchemy has first-class support for pgvector via the `pgvector-python` package:

```python
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))  # OpenAI dimensions
    content: Mapped[str]
```

Vector similarity search in SQLAlchemy:

```python
from pgvector.sqlalchemy import cosine_distance
from sqlalchemy import select

stmt = (
    select(Memory)
    .order_by(cosine_distance(Memory.embedding, query_embedding))
    .limit(10)
)
```

This integrates cleanly with the existing async SQLAlchemy setup without any additional
abstraction layers.

### 6. Alembic Migrations

PostgreSQL schema changes are managed entirely through Alembic. This gives:

- Version-controlled schema history.
- Rollback capability.
- CI validation that migrations are correct before deployment.

DynamoDB has no schema migrations — schema changes are ad-hoc and untracked.
MongoDB's flexible schema is a double-edged sword: it allows inconsistent documents
and makes it hard to enforce data contracts.

### 7. AWS RDS Availability

AWS RDS for PostgreSQL 16 supports the pgvector extension natively since pgvector 0.5.0.
This means:

- No custom AMI or manual installation required.
- Automated backups, Multi-AZ failover, read replicas — all managed.
- RDS Parameter Groups allow tuning `shared_preload_libraries` for pgvector.

---

## Consequences

### Positive

- Single operational data store with full ACID guarantees.
- Efficient cursor pagination with standard B-tree indexes.
- Vector search without a separate service.
- Alembic migrations track all schema changes.
- Proven at scale (OpenAI, Supabase production).
- Cost-efficient: one RDS instance handles both relational and vector workloads.

### Negative

- pgvector approximate search (HNSW) is not as fast as dedicated vector databases
  (Pinecone, Qdrant) for very large vector datasets (>10M vectors).
- RDS vertical scaling has an upper limit; very large deployments may require read replicas.
- `ALTER TABLE` on large tables (e.g., adding a column) requires careful planning to avoid
  locks.

### Accepted Trade-offs

- At Ember's expected scale (< 10M users initially), pgvector HNSW performance is
  indistinguishable from Pinecone for the memory retrieval use case.
- If the vector dataset grows beyond 50M embeddings, the architecture can be extended
  to add a dedicated vector store without changing the relational layer.

---

## Alternatives Considered

### MongoDB + Atlas Vector Search

Rejected because:
- Transactions are available but less mature than PostgreSQL.
- Cursor pagination is less natural.
- Document model provides no structural benefit for Ember's well-defined schemas.
- Atlas Vector Search requires Atlas (managed), limiting self-hosting options.

### DynamoDB

Rejected because:
- No native vector search.
- Cursor pagination requires careful key design.
- No `ORDER BY` — application-side sorting for messages.
- Eventual consistency by default is incompatible with message ordering requirements.
- Higher operational complexity for relational access patterns.

### Pinecone (dedicated vector DB)

Rejected because:
- Does not store relational data — would require a second database.
- Dual-write complexity.
- Higher cost than RDS + pgvector for equivalent functionality.

### Supabase

Not rejected — Supabase is a managed PostgreSQL + pgvector service that could host
this setup. However, for production the team prefers AWS RDS for consistency with the
existing AWS infrastructure (Cognito, Secrets Manager, CloudWatch, ECS).
Supabase remains a viable option for staging or development environments.
