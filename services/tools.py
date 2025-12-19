# Tool definitions and implementations for weather lookup and web search.
import httpx
from typing import Optional
import config


async def get_weather(city: str) -> str:
    if not config.WEATHER_API_KEY or config.WEATHER_API_KEY.startswith("your_"):
        return f"Weather API not configured. Please add WEATHER_API_KEY to .env file. (Simulated: Weather in {city} is sunny, 22C)"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": city,
                    "appid": config.WEATHER_API_KEY,
                    "units": "metric"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                weather = data["weather"][0]["description"]
                temp = data["main"]["temp"]
                feels_like = data["main"]["feels_like"]
                humidity = data["main"]["humidity"]
                wind_speed = data["wind"]["speed"]
                
                return (
                    f"Weather in {city}:\n"
                    f"Condition: {weather.capitalize()}\n"
                    f"Temperature: {temp}C (feels like {feels_like}C)\n"
                    f"Humidity: {humidity}%\n"
                    f"Wind Speed: {wind_speed} m/s"
                )
            else:
                return f"Could not fetch weather for {city}. Error: {response.status_code}"
                
    except Exception as e:
        return f"Error fetching weather: {str(e)}"


async def google_search(query: str, num_results: int = 5) -> str:
    if not config.SERPAPI_KEY or config.SERPAPI_KEY.startswith("your_"):
        return await duckduckgo_search(query, num_results)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": config.SERPAPI_KEY,
                    "engine": "google",
                    "num": num_results
                },
                timeout=15.0
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("organic_results", [])[:num_results]
                
                if not results:
                    return f"No search results found for: {query}"
                
                formatted_results = [f"Search results for '{query}':\n"]
                for i, result in enumerate(results, 1):
                    title = result.get("title", "No title")
                    snippet = result.get("snippet", "No description")
                    link = result.get("link", "")
                    formatted_results.append(f"{i}. {title}\n   {snippet}\n   URL: {link}\n")
                
                return "\n".join(formatted_results)
            else:
                return await duckduckgo_search(query, num_results)
                
    except Exception as e:
        return await duckduckgo_search(query, num_results)


async def duckduckgo_search(query: str, num_results: int = 5) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                
                results = []
                
                if data.get("Abstract"):
                    results.append(f"Summary: {data['Abstract']}")
                    if data.get("AbstractURL"):
                        results.append(f"Source: {data['AbstractURL']}")
                
                related = data.get("RelatedTopics", [])[:num_results]
                if related:
                    results.append("\nRelated information:")
                    for i, topic in enumerate(related, 1):
                        if isinstance(topic, dict) and "Text" in topic:
                            text = topic["Text"]
                            url = topic.get("FirstURL", "")
                            results.append(f"{i}. {text}")
                            if url:
                                results.append(f"   URL: {url}")
                
                if results:
                    return f"Search results for '{query}':\n\n" + "\n".join(results)
                else:
                    return f"No detailed results found for '{query}'. Try a more specific search."
                    
            else:
                return f"Search failed with status code: {response.status_code}"
                
    except Exception as e:
        return f"Search error: {str(e)}"


TOOL_DEFINITIONS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a specific city. Use this when the user asks about weather conditions, temperature, or forecast for a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city to get weather for (e.g., 'London', 'New York', 'Tokyo')"
                }
            },
            "required": ["city"]
        }
    },
    {
        "name": "google_search",
        "description": "Search the web for information. Use this when the user asks about current events, facts, news, or any information that might need to be looked up online.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
]


TOOL_FUNCTIONS = {
    "get_weather": get_weather,
    "google_search": google_search
}
