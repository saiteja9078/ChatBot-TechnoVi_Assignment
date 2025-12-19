# Supabase database service
from supabase import create_client, Client
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import config


class SupabaseService:
    
    def __init__(self):
        self.client: Client = create_client(
            supabase_url=config.SUPABASE_URL,
            supabase_key=config.SUPABASE_SERVICE_ROLE_KEY
        )
    
    async def create_session(self, session_id: str, user_id: str = "anonymous", session_name: str = None) -> Dict[str, Any]:
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
        
        if session_name:
            session_data["session_name"] = session_name
        
        response = self.client.table("sessions").insert(session_data).execute()
        return response.data[0] if response.data else None
    
    async def update_session(
        self,
        session_id: str,
        session_name: Optional[str] = None,
        end_time: Optional[datetime] = None,
        duration_seconds: Optional[int] = None,
        summary: Optional[str] = None
    ) -> Dict[str, Any]:
        update_data = {}
        
        if session_name:
            update_data["session_name"] = session_name
        if end_time:
            update_data["end_time"] = end_time.isoformat()
        if duration_seconds is not None:
            update_data["duration_seconds"] = duration_seconds
        if summary:
            update_data["summary"] = summary
        
        if update_data:
            response = self.client.table("sessions").update(update_data).eq("session_id", session_id).execute()
            return response.data[0] if response.data else None
        return None
    
    async def delete_session(self, session_id: str) -> bool:
        try:
            self.client.table("sessions").delete().eq("session_id", session_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        response = self.client.table("sessions").select("*").eq("session_id", session_id).execute()
        return response.data[0] if response.data else None
    
    async def get_all_sessions(self, user_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        query = self.client.table("sessions").select("*").order("start_time", desc=True).limit(limit)
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.execute()
        return response.data or []
    
    async def log_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        event_data = {
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
        }
        
        response = self.client.table("session_events").insert(event_data).execute()
        return response.data[0] if response.data else None
    
    async def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("session_events")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []
    
    async def get_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        events = await self.get_session_events(session_id)
        
        history = []
        for event in events:
            if event["event_type"] == "user_message":
                history.append({
                    "role": "user",
                    "content": event["payload"].get("content", "")
                })
            elif event["event_type"] == "ai_response":
                history.append({
                    "role": "assistant",
                    "content": event["payload"].get("content", "")
                })
        
        return history


supabase_service = SupabaseService()
