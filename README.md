# Realtime AI Backend

A high-performance, asynchronous Python backend implementing real-time conversational sessions with WebSocket bi-directional communication, LLM streaming, and Supabase persistence.

## Table of Contents

- [Setup Instructions](#setup-instructions)
- [Database Schema](#database-schema)
- [Running and Testing](#running-and-testing)
- [Design Choices](#design-choices)
- [Project Structure](#project-structure)
- [WebSocket Protocol](#websocket-protocol)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone [https://github.com/saiteja9078/ChatBot.git](https://github.com/saiteja9078/ChatBot-TechnoVi_Assignment/)
cd ChatBot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:

- quart
- quart-cors
- supabase
- langchain-google-genai
- langchain-core
- httpx
- python-dotenv

### 3. Configure Environment Variables

Open `.env` file in the project root:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
GEMINI_API_KEY=your_gemini_api_key
WEATHER_API_KEY=your_openweathermap_key
SERPAPI_KEY=your_serpapi_key
```

### 4. Set Up Database

Run the SQL commands from the Database Schema section in Supabase SQL Editor.

## Database Schema

The schema consists of two tables:

**sessions** - Stores session metadata (session_id, user_id, start_time, end_time)

```sql
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY,
    user_id TEXT DEFAULT 'anonymous',
    session_name TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_seconds INTEGER,
    summary TEXT
);
```

**session_events** - Stores chronological event log (user messages, AI responses, tool calls)

```sql
CREATE TABLE session_events (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_session_events_session_id ON session_events(session_id);
```

## Running and Testing

### Start the Server

```bash
python main.py
```

The server starts at `http://localhost:5001`.

### Testing via Browser

1. Open `http://localhost:5001` in your browser
2. The frontend interface loads automatically
3. Click "New chat" or type a message to start
4. Open DevTools (F12) > Network > WS tab to observe WebSocket traffic

### Testing via Command Line

Using websocat:

```bash
brew install websocat
websocat ws://localhost:5001/ws/session/test-session-123
```

Send a message:

```json
{ "type": "message", "content": "What is the weather in Tokyo?" }
```

### Testing via Python

```python
import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:5001/ws/session/test-123") as ws:
        await ws.send(json.dumps({"type": "message", "content": "Hello"}))
        while True:
            response = json.loads(await ws.recv())
            print(response)
            if response.get("type") == "done":
                break

asyncio.run(test())
```

## Design Choices

### Framework: Quart

Quart was chosen for its native async/await support, essential for non-blocking WebSocket connections and concurrent session handling.

### WebSocket over SSE

WebSocket provides true bi directional communication, allowing real time message exchange and immediate token streaming.

### Function/Tool Calling

The LLM uses function calling to execute weather lookups and web searches, demonstrating complex interaction beyond simple Q&A. The model autonomously decides when to invoke tools.

### State Management

Each WebSocket connection maintains independent conversation history, ensuring context continuity across multiple user turns.

### Post-Session Processing

When a WebSocket disconnects, an async task generates a session summary using the LLM and persists it along with end_time and duration to the database.

### Frontend

For simplicity, the frontend is built with plain HTML and JavaScript. No frameworks or build tools are required. The static files are served directly by the Quart server.

## Project Structure

```
ChatBot/
├── main.py                  # Quart WebSocket server
├── config.py                # Environment configuration
├── requirements.txt         # Python dependencies
├── services/
│   ├── supabase_service.py  # Database operations
│   ├── llm_service.py       # Gemini LLM with streaming
│   └── tools.py             # Weather and search tools
└── static/
    ├── index.html           # Chat UI (HTML)
    ├── chatbot.css          # Styling (CSS)
    └── chatbot.js           # WebSocket client (JavaScript)
```

## WebSocket Protocol

### Client to Server

```json
{"type": "message", "content": "user message"}
{"type": "ping"}
```

### Server to Client

```json
{"type": "thinking_start"}
{"type": "token", "content": "partial response"}
{"type": "tool_use", "tool_name": "get_weather", "tool_args": {"city": "Tokyo"}}
{"type": "tool_output", "tool_name": "get_weather", "output": "..."}
{"type": "thinking_end"}
{"type": "done"}
{"type": "error", "message": "..."}
{"type": "pong"}
```
