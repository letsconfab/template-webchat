# Chat Journey

State: `explored`

Verified score: `n/a`

Agent-ready: `no`

Assessment attempts: `0`

## Concepts Seen

- browser chat
- WebSocket session
- backend agent
- retrieval tool
- LLM streaming
- frontend WebSocket event protocol
- `backend /ws/chat handler lifecycle`
- handshake vs message loop phases
- `provider/model sentinel precedence (client vs server settings)`
- dual history store (in-memory dict + persisted load)
- defensive error frame on socket teardown
- GraphRAG hybrid retrieval (Qdrant primary, Neo4j secondary)
- GraphRAG context concatenation (vector passages then graph relationships)
- LangGraph ReAct factory and compiled message-state loop
- Deep Agents fit boundary (future deep research mode, not default chat)
- LangChain v1 create_agent migration decision
- LangGraph event-to-WebSocket protocol adapter
- model reasoning versus answer-content channels
- tool lifecycle think frames
- direct-LLM and error fallbacks
- assistant response persistence and end-frame lifecycle
- end-to-end WebSocket consumer state machine
- think frames are transient and not available to feedback review

## Code Anchors

- `frontend/src/pages/ChatPage.tsx:153`
- `backend/main.py:440`
- `backend/main.py:455`
- `backend/main.py:482`
- `backend/main.py:519`
- `backend/main.py:304`
- `backend/services/graphrag_service.py:23`
- `backend/services/graphrag_service.py:108`
- `backend/services/graphrag_service.py:222`
- `backend/main.py:334`
- `backend/main.py:356`
- `backend/main.py:380`
- `backend/main.py:396`
- `backend/main.py:416`
- `test_ws.py:49`
- `backend/models/wiki.py:91`
- `backend/models/wiki.py:110`
