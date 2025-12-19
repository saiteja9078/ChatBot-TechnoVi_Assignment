# LLM service using Google Gemini
import json
from typing import AsyncGenerator, List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
import config
from services.tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS


SYSTEM_PROMPT = """You are a helpful AI assistant with access to real-time tools. You can:

1. **Get Weather**: Fetch current weather conditions for any city worldwide
2. **Web Search**: Search the internet for current information, news, and facts

When users ask about weather or need to look up information, use the appropriate tool.
Always be helpful, concise, and informative. If you use a tool, explain the results clearly.

For general conversation, respond naturally and engagingly."""


class LLMService:
    
    def __init__(self):
        self.model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=config.GEMINI_API_KEY,
            temperature=0.7,
        )
        
        self.naming_model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=config.GEMINI_API_KEY_NAMING,
            temperature=0.3,
        )
        
        self.model_with_tools = self.model.bind_tools(
            tools=TOOL_DEFINITIONS,
            tool_choice="auto"
        )
    
    def _build_messages(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]]
    ) -> List:
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        
        for msg in conversation_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        
        messages.append(HumanMessage(content=user_message))
        return messages
    
    async def generate_chat_name(self, first_message: str) -> str:
        naming_prompt = f"""Generate a very short title (2-5 words max) for a chat that starts with this message:

"{first_message}"

Rules:
- Maximum 5 words
- Be descriptive but concise
- No quotes, just the title
- Examples: "Weather in Paris", "Python Help", "Math Homework", "Travel Planning"

Title:"""
        
        try:
            messages = [HumanMessage(content=naming_prompt)]
            response = await self.naming_model.ainvoke(messages)
            name = response.content.strip().strip('"\'')
            words = name.split()
            if len(words) > 5:
                name = ' '.join(words[:5])
            return name
        except Exception as e:
            words = first_message.split()[:4]
            return ' '.join(words) + ('...' if len(first_message.split()) > 4 else '')
    
    async def generate_streaming_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        conversation_history = conversation_history or []
        messages = self._build_messages(user_message, conversation_history)
        
        full_response = ""
        tool_calls_pending = []
        
        try:
            async for chunk in self.model_with_tools.astream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield {"type": "token", "content": chunk.content}
                
                if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                    for tool_call in chunk.tool_calls:
                        tool_calls_pending.append(tool_call)
            
            if tool_calls_pending:
                for tool_call in tool_calls_pending:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("args", {})
                    tool_id = tool_call.get("id", "")
                    
                    yield {
                        "type": "tool_call",
                        "name": tool_name,
                        "args": tool_args
                    }
                    
                    if tool_name in TOOL_FUNCTIONS:
                        tool_result = await TOOL_FUNCTIONS[tool_name](**tool_args)
                        
                        yield {
                            "type": "tool_result",
                            "name": tool_name,
                            "result": tool_result
                        }
                        
                        messages.append(AIMessage(
                            content=full_response,
                            tool_calls=[tool_call]
                        ))
                        messages.append(ToolMessage(
                            content=tool_result,
                            tool_call_id=tool_id
                        ))
                
                full_response = ""
                async for chunk in self.model.astream(messages):
                    if chunk.content:
                        full_response += chunk.content
                        yield {"type": "token", "content": chunk.content}
            
            yield {"type": "done", "full_response": full_response}
            
        except Exception as e:
            yield {"type": "error", "content": f"Error generating response: {str(e)}"}
    
    async def generate_session_summary(
        self,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        if not conversation_history:
            return "Empty session - no conversation occurred."
        
        conversation_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in conversation_history
        ])
        
        summary_prompt = f"""Please provide a concise summary (2-3 sentences) of the following conversation. 
Focus on the main topics discussed, any tools used, and key outcomes.

CONVERSATION:
{conversation_text}

SUMMARY:"""
        
        try:
            messages = [HumanMessage(content=summary_prompt)]
            response = await self.model.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            return f"Error generating summary: {str(e)}"


llm_service = LLMService()
