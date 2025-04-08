import httpx
from mcp.server.fastmcp import FastMCP
from claudette import Client

mcp = FastMCP("llms-txt-parser")
USER_AGENT = "llms-txt-parser/1.0"
CLAUDE_MODEL = "claude-3-7-sonnet-latest" 

async def fetch_url(url: str) -> str | None:
    """Fetch markdown content from a URL."""
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.text
        except Exception: return None

@mcp.resource("fasthtml://chatbot")
def get_fasthtml_chatbot_rules() -> str:
    """Rules for implementing chatbot interfaces in FastHTML applications. Demonstrates real-time message handling, chat history management, and integration with AI/ML services. Includes patterns for streaming responses, user input handling, and conversation state management."""
    return "App configuration here"

@mcp.tool()
async def parse_llms_txt(llms_txt_url: str, query: str) -> str:
    """Parse an llms.txt file and fetch relevant documentation based on a query."""

    llms_content = await fetch_url(llms_txt_url)
    if not llms_content: return f"Error: Could not fetch llms.txt from {llms_txt_url}"
    
    client = Client(CLAUDE_MODEL)
    relevant_links = client.structured(
        f"""Given this llms.txt content and user query, analyze which documentation links are most relevant.
        The llms.txt format is a standardized way to provide LLM-friendly documentation, containing a project overview 
        and links to detailed documentation in markdown format.

        llms.txt content:
        {llms_content}

        User query: {query}
        """, 
        links
    )
    
    results = []
    for link in relevant_links:
        url = link['url']
        content = await fetch_url(url)
        if content: results.append(f"# {link['title']}\n{link['description']}\n\n{content}\n---\n")
        else: results.append(f"Could not fetch content from {url}\n---\n")
    return "\n".join(results) if results else "No relevant documentation found."

if __name__ == "__main__":
    mcp.run(transport='stdio')