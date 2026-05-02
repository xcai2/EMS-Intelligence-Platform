import logging
import os

logger = logging.getLogger(__name__)


async def ask_gemini_with_search(question: str) -> str:
    """
    Send question to Gemini with Google Search grounding enabled.
    Returns raw response text. Raises on failure.
    """
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        client = genai.Client(api_key=api_key)

        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool], max_output_tokens=8192)

        response = client.models.generate_content(
            model=model_name,
            contents=question,
            config=config,
        )
        return response.text or ""
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        raise
