from typing import List, Dict, Optional, Tuple
import httpx
from mcp.server.fastmcp import FastMCP, Context
from claudette import Client, Chat
import os

mcp = FastMCP("llms-txt-parser")
USER_AGENT = "llms-txt-parser/1.0"
CLAUDE_MODEL = "claude-3-7-sonnet-latest"
JINA_API_KEY = os.environ.get('JINA_READER_KEY')  # Get API key from environment variable

def links(url: str, title: str, description: str):
    """
    Create a formatted link entry for documentation.
    
    Args:
        url: URL to the documentation
        title: Title of the link
        description: Optional description of the link
        
    Returns:
        tuple: (url, title, description)
    """
    return {'url': url, 'title': title, 'description': description}

async def fetch_markdown(url: str, headers: dict = None) -> str | None:
    """Fetch markdown content from a URL."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.text
        except Exception: return None

async def check_path_exists(base_url: str, path: str) -> Optional[str]:
    """Check if a path exists at a URL and return its content if it does."""
    url = base_url.rstrip('/') + '/' + path.lstrip('/')
    return await fetch_markdown(url)

async def find_llms_txt(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Find llms.txt or related files at different potential locations."""
    # Normalize URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Remove trailing slash and get base URL
    base_url_parts = url.split('/')
    if len(base_url_parts) >= 3:  # has protocol and domain
        base_url = '/'.join(base_url_parts[:3])
    else:
        base_url = url
    
    # List of paths to check in priority order
    paths_to_check = [
        'llms.txt',
        'docs/llms.txt',
        'documentation/llms.txt',
        'doc/llms.txt',
        'docs/llms.txt',
        'llms-ctx.txt',
        'llms-ctx-full.txt',
        'api/llms.txt',
        'reference/llms.txt'
    ]
    
    # Check each path
    for path in paths_to_check:
        content = await check_path_exists(base_url, path)
        if content:
            return content, f"{base_url}/{path}"
    
    # Try the URL itself if it might be a direct link to llms.txt
    if url.endswith('.txt'):
        content = await fetch_markdown(url)
        if content:
            return content, url
            
    return None, None

async def is_developer_tool(url: str) -> bool:
    """Use Claude to determine if a URL is likely for a developer tool."""
    # Use Jina with environment variable API key
    content = await use_jina_reader(url)
    if not content: return False
    
    # Use Claude to analyze the clean content
    client = Client(CLAUDE_MODEL)

    def is_dev(val:bool): 
        "Returns True if the webpage is concerning a developer tool, else False."
        return val

    response = client.structured(
        f"""
        Analyze the following webpage content and determine if it appears to be documentation 
        for a developer tool, API, library, framework, or software development resource.
        Focus on identifying technical terminology, code examples, API reference materials,
        installation instructions, or other indicators of developer documentation.
        
        <webpage-content>
        {content[:100000]}
        </webpage-content>
        
        Return TRUE if this is likely developer documentation, or FALSE if not.
        """,
        is_dev  # Return a boolean value
    )
    
    return response[0] if response else False

async def find_docs_links_with_claude(url: str, content: str = None) -> List[Dict]:
    """Use Claude to identify documentation links from a webpage."""
    if not content:
        content = await fetch_markdown(url)
        if not content: return []
    
    # Use structured output to get docs links
    client = Client(CLAUDE_MODEL)
    docs_links = client.structured(
        f"""
        Analyze the following webpage content and identify links that appear to lead to 
        documentation pages, API references, tutorials, or other developer resources.
        
        Webpage content:
        {content[:100000]}  # Limit content length to avoid token limits
        
        Extract all links that appear to point to documentation. For each link, provide:
        1. The URL (if relative, prepend "{url}" if it doesn't start with '/')
        2. A title describing the resource
        3. A brief description of what content you expect to find there
        
        Focus on links that would be most valuable for a developer trying to understand how to use this tool.
        """,
        links
    )
    
    # Resolve relative URLs
    for link in docs_links:
        if not link['url'].startswith(('http://', 'https://')):
            if link['url'].startswith('/'):
                # Extract base URL (protocol + domain)
                base_url_parts = url.split('/')
                if len(base_url_parts) >= 3:
                    base_url = '/'.join(base_url_parts[:3])
                    link['url'] = base_url + link['url']
            else:
                # Handle relative URLs
                if url.endswith('/'):
                    link['url'] = url + link['url']
                else:
                    link['url'] = url + '/' + link['url']
    
    return docs_links

async def use_jina_reader(url: str) -> Optional[str]:
    """Use Jina Reader API to get clean content from a URL."""
    jina_url = "https://r.jina.ai/" + url.replace('https://', '').replace('http://', '')
    
    headers = {"User-Agent": USER_AGENT}
    if JINA_API_KEY: headers["x-api-key"] = JINA_API_KEY
    
    return await fetch_markdown(jina_url, headers)

@mcp.tool()
async def parse_llms_txt(url: str, query: str, ctx: Context = None) -> str:
    """
    Parse an llms.txt file and fetch relevant documentation based on a query.
    
    Args:
        url: URL of the llms.txt file or base URL to search for documentation
        query: User's question or query
    """
    if ctx:
        ctx.info(f"Looking for llms.txt or related files at {url}")
    
    # Step 1: Try to find llms.txt directly
    llms_content, llms_url = await find_llms_txt(url)
    
    # Step 2: If not found, check for documentation links on the page
    if not llms_content:
        if ctx:
            ctx.info("llms.txt not found, looking for documentation links...")
        
        page_content = await fetch_markdown(url)
        if page_content:
            docs_links = await find_docs_links_with_claude(url, page_content)
            
            # Check each discovered docs link for llms.txt
            for link in docs_links:
                if ctx:
                    ctx.info(f"Checking {link['url']} for llms.txt...")
                llms_content, llms_url = await find_llms_txt(link['url'])
                if llms_content:
                    break
    
    # Step 3: If still not found and it's a developer tool, use Jina as fallback
    if not llms_content:
        if ctx:
            ctx.info("No llms.txt found, checking if this is a developer tool...")
        
        is_dev_tool = await is_developer_tool(url)
        if is_dev_tool:
            if ctx:
                ctx.info("URL appears to be a developer tool, using Jina Reader as fallback...")
            
            # Use Jina to get clean content
            jina_content = await use_jina_reader(url)
            
            if jina_content:
                if ctx:
                    ctx.info("Using Claude to extract relevant documentation from Jina-processed content...")
                
                # Important fix: Pass the Jina-processed content directly to Claude
                docs_links = await find_docs_links_with_claude(url, jina_content)
                
                # Initialize results for collecting content
                results = []
                
                # If we found links, fetch and append their content
                if docs_links:
                    for link in docs_links:
                        if ctx:
                            ctx.info(f"Fetching linked content from {link['url']}...")
                        content = await fetch_markdown(link['url'])
                        if content:
                            results.append(f"# {link['title']}\n{link['description']}\n\n{content}\n---\n")
                        else:
                            results.append(f"Could not fetch content from {link['url']}\n---\n")
                
                # If no links or couldn't fetch any content, use the Jina content directly
                if not results:
                    # Use Claude to extract relevant sections based on query
                    chat = Chat(CLAUDE_MODEL)
                    response = chat(
                        f"""Below is documentation content for a developer tool. Based on the user's query, 
                        extract the most relevant sections that would help answer the query.
                        Format your response as markdown and include code examples when available.
                        
                        Documentation content:
                        {jina_content}
                        
                        User query: {query}
                        """
                    )
                    return f"# Relevant information from {url}\n\n{response.content[0].text}"
                
                return "\n".join(results)
    
    # If we have llms.txt content, process it
    if llms_content:
        if ctx:
            ctx.info(f"Found llms.txt at {llms_url}, parsing with Claude...")
        
        # Parse proper llms.txt format using Claude
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
        
        # Fetch relevant documentation
        results = []
        for link in relevant_links:
            if ctx:
                ctx.info(f"Fetching linked content from {link['url']}...")
            content = await fetch_markdown(link['url'])
            if content:
                results.append(f"# {link['title']}\n{link['description']}\n\n{content}\n---\n")
            else:
                results.append(f"Could not fetch content from {link['url']}\n---\n")
        
        return "\n".join(results) if results else "No relevant documentation found in llms.txt."
    
    return f"Could not find llms.txt or extract documentation from {url}."

if __name__ == "__main__":
    mcp.run(transport='stdio')