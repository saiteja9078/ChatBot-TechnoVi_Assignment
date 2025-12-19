# Quart WebSocket server with REST API endpoints.
import asyncio
import json
import uuid
from datetime import datetime, timezone
from quart import Quart, request, jsonify, send_from_directory, Response, websocket
from quart_cors import cors
import config
from services.supabase_service import supabase_service
from services.llm_service import llm_service
app = Quart(__name__, static_folder='static')
app = cors(app, allow_origin="*")

sessions_state = {}

def get_session_state(session_id: str) -> dict:
    if session_id not in sessions_state:
        sessions_state[session_id] = {
            "conversation_history": [],
            "start_time": datetime.now(timezone.utc),
            "is_first_message": True,
            "session_persisted": False
        }
    return sessions_state[session_id]

def cleanup_session_state(session_id: str):
    if session_id in sessions_state:
        del sessions_state[session_id]

current_session_id = None
conversation_history = []
session_start_time = None
is_first_message = True
session_persisted = False




@app.route('/')
async def index():
    return await send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:filename>')
async def static_files(filename):
    return await send_from_directory(app.static_folder, filename)




@app.route('/sessions', methods=['GET'])
async def get_sessions():
    try:
        sessions = await supabase_service.get_all_sessions()
        return jsonify({"sessions": sessions})
    except Exception as e:
        print(f"Error getting sessions: {e}")
        return jsonify({"sessions": [], "error": str(e)})


@app.route('/sessions/<session_id>', methods=['GET'])
async def get_session(session_id):
    global current_session_id, conversation_history, session_start_time, is_first_message
    
    try:
        session = await supabase_service.get_session(session_id)
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        history = await supabase_service.get_conversation_history(session_id)
        
        current_session_id = session_id
        conversation_history = history
        session_start_time = datetime.now(timezone.utc)
        is_first_message = len(history) == 0
        
        return jsonify({
            "session": session,
            "history": history
        })
    except Exception as e:
        print(f"Error getting session: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/new_chat', methods=['POST'])
async def new_chat():
    global current_session_id, conversation_history, session_start_time, is_first_message, session_persisted
    
    if current_session_id and session_persisted and len(conversation_history) >= 2:
        asyncio.create_task(process_session_end(
            current_session_id, 
            session_start_time or datetime.now(timezone.utc)
        ))
    
    current_session_id = str(uuid.uuid4())
    conversation_history = []
    session_start_time = datetime.now(timezone.utc)
    is_first_message = True
    session_persisted = False
    
    return jsonify({"status": "new chat started", "session_id": current_session_id})


@app.route('/sessions/<session_id>', methods=['DELETE'])
async def delete_session(session_id):
    global current_session_id, conversation_history
    
    try:
        success = await supabase_service.delete_session(session_id)
        
        if success:
            if session_id == current_session_id:
                current_session_id = None
                conversation_history = []
            
            return jsonify({"status": "deleted", "session_id": session_id})
        else:
            return jsonify({"error": "Failed to delete session"}), 500
    except Exception as e:
        print(f"Error deleting session: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/chat', methods=['POST'])
async def chat():
    global current_session_id, conversation_history, session_start_time, is_first_message, session_persisted
    
    data = await request.get_json()
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({"error": "No message provided"}), 400
    
    if not current_session_id:
        current_session_id = str(uuid.uuid4())
        session_start_time = datetime.now(timezone.utc)
        is_first_message = True
        session_persisted = False
    
    if is_first_message:
        is_first_message = False
        try:
            await supabase_service.create_session(current_session_id)
            session_persisted = True
        except Exception as e:
            print(f"Error creating session: {e}")
        asyncio.create_task(generate_and_save_chat_name(current_session_id, user_message))
    
    try:
        await supabase_service.log_event(
            session_id=current_session_id,
            event_type="user_message",
            payload={"content": user_message}
        )
    except Exception as e:
        print(f"Error logging user message: {e}")
    
    conversation_history.append({
        "role": "user",
        "content": user_message
    })
    
    async def generate():
        full_response = ""
        tool_events = []
        
        try:
            yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"
            
            async for chunk in llm_service.generate_streaming_response(
                user_message=user_message,
                conversation_history=conversation_history[:-1]
            ):
                chunk_type = chunk.get("type")
                
                if chunk_type == "token":
                    content = chunk.get("content", "")
                    full_response += content
                    yield f"data: {json.dumps({'type': 'response_chunk', 'content': content})}\n\n"
                
                elif chunk_type == "tool_call":
                    tool_name = chunk.get("name", "")
                    tool_args = chunk.get("args", {})
                    tool_events.append(chunk)
                    
                    display_name = "WebSearch" if tool_name == "google_search" else tool_name
                    yield f"data: {json.dumps({'type': 'tool_use', 'tool_name': display_name, 'tool_args': tool_args})}\n\n"
                
                elif chunk_type == "tool_result":
                    tool_name = chunk.get("name", "")
                    result = chunk.get("result", "")
                    tool_events.append(chunk)
                    
                    display_name = "WebSearch" if tool_name == "google_search" else tool_name
                    yield f"data: {json.dumps({'type': 'tool_output', 'tool_name': display_name, 'output': result})}\n\n"
                
                elif chunk_type == "done":
                    full_response = chunk.get("full_response", full_response)
                
                elif chunk_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': chunk.get('content', 'Unknown error')})}\n\n"
            
            yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"
            
            conversation_history.append({
                "role": "assistant",
                "content": full_response
            })
            
            try:
                await supabase_service.log_event(
                    session_id=current_session_id,
                    event_type="ai_response",
                    payload={"content": full_response}
                )
                
                for tool_event in tool_events:
                    await supabase_service.log_event(
                        session_id=current_session_id,
                        event_type=tool_event.get("type", "tool_event"),
                        payload=tool_event
                    )
            except Exception as e:
                print(f"Error logging AI response: {e}")
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"Error in stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


async def generate_and_save_chat_name(session_id: str, first_message: str):
    try:
        chat_name = await llm_service.generate_chat_name(first_message)
        await supabase_service.update_session(
            session_id=session_id,
            session_name=chat_name
        )
        print(f"Generated chat name: {chat_name}")
    except Exception as e:
        print(f"Error generating chat name: {e}")




@app.websocket('/ws/session/<session_id>')
async def ws_session(session_id: str):
    print(f"WebSocket connected: session {session_id}")
    
    state = get_session_state(session_id)
    
    try:
        while True:
            raw_message = await websocket.receive()
            
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
                continue
            
            msg_type = data.get("type", "")
            
            if msg_type == "message":
                user_content = data.get("content", "").strip()
                
                if not user_content:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Empty message"
                    }))
                    continue
                
                if state["is_first_message"]:
                    state["is_first_message"] = False
                    try:
                        await supabase_service.create_session(session_id)
                        state["session_persisted"] = True
                    except Exception as e:
                        print(f"Error creating session: {e}")
                    asyncio.create_task(generate_and_save_chat_name(session_id, user_content))
                
                try:
                    await supabase_service.log_event(
                        session_id=session_id,
                        event_type="user_message",
                        payload={"content": user_content}
                    )
                except Exception as e:
                    print(f"Error logging user message: {e}")
                
                state["conversation_history"].append({
                    "role": "user",
                    "content": user_content
                })
                
                await websocket.send(json.dumps({"type": "thinking_start"}))
                
                full_response = ""
                tool_events = []
                
                try:
                    async for chunk in llm_service.generate_streaming_response(
                        user_message=user_content,
                        conversation_history=state["conversation_history"][:-1]
                    ):
                        chunk_type = chunk.get("type")
                        
                        if chunk_type == "token":
                            content = chunk.get("content", "")
                            full_response += content
                            await websocket.send(json.dumps({
                                "type": "token",
                                "content": content
                            }))
                        
                        elif chunk_type == "tool_call":
                            tool_name = chunk.get("name", "")
                            tool_args = chunk.get("args", {})
                            tool_events.append(chunk)
                            display_name = "WebSearch" if tool_name == "google_search" else tool_name
                            await websocket.send(json.dumps({
                                "type": "tool_use",
                                "tool_name": display_name,
                                "tool_args": tool_args
                            }))
                        
                        elif chunk_type == "tool_result":
                            tool_name = chunk.get("name", "")
                            result = chunk.get("result", "")
                            tool_events.append(chunk)
                            display_name = "WebSearch" if tool_name == "google_search" else tool_name
                            await websocket.send(json.dumps({
                                "type": "tool_output",
                                "tool_name": display_name,
                                "output": result
                            }))
                        
                        elif chunk_type == "done":
                            full_response = chunk.get("full_response", full_response)
                        
                        elif chunk_type == "error":
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": chunk.get("content", "Unknown error")
                            }))
                    
                    await websocket.send(json.dumps({"type": "thinking_end"}))
                    
                    state["conversation_history"].append({
                        "role": "assistant",
                        "content": full_response
                    })
                    
                    try:
                        await supabase_service.log_event(
                            session_id=session_id,
                            event_type="ai_response",
                            payload={"content": full_response}
                        )
                        
                        for tool_event in tool_events:
                            await supabase_service.log_event(
                                session_id=session_id,
                                event_type=tool_event.get("type", "tool_event"),
                                payload=tool_event
                            )
                    except Exception as e:
                        print(f"Error logging AI response: {e}")
                    
                    await websocket.send(json.dumps({"type": "done"}))
                    
                except Exception as e:
                    print(f"Error in LLM stream: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": str(e)
                    }))
            
            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong"}))
    
    except asyncio.CancelledError:
        print(f"WebSocket cancelled: session {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print(f"WebSocket disconnected: session {session_id}")
        if state["session_persisted"] and len(state["conversation_history"]) >= 2:
            asyncio.create_task(process_session_end(
                session_id,
                state["start_time"]
            ))
        cleanup_session_state(session_id)


async def process_session_end(session_id: str, start_time: datetime):
    try:
        session_end = datetime.now(timezone.utc)
        duration_seconds = int((session_end - start_time).total_seconds())
        
        history = await supabase_service.get_conversation_history(session_id)
        
        if history:
            summary = await llm_service.generate_session_summary(history)
        else:
            summary = "Empty session - no conversation occurred."
        
        await supabase_service.update_session(
            session_id=session_id,
            end_time=session_end,
            duration_seconds=duration_seconds,
            summary=summary
        )
        
        await supabase_service.log_event(
            session_id=session_id,
            event_type="session_end",
            payload={
                "duration_seconds": duration_seconds,
                "summary": summary
            }
        )
        
        print(f"Session {session_id} ended. Duration: {duration_seconds}s")
        
    except Exception as e:
        print(f"Error processing session end: {e}")




if __name__ == '__main__':
    try:
        config.validate_config()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Please check your .env file and add the required API keys.")
        exit(1)
    
    print(f"Starting ChatBot server on http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=True)
