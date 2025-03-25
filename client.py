import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os

# Set your token
GITHUB_TOKEN = ""  # optional: use .env too

# Define server parameters to launch the GitHub MCP server via npx
server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-github"],
    env={"GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN},
)

async def run_client():
    async with stdio_client(server_params) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("🛠️ Tools:", tools)

            # Call a valid tool: search_repositories
            result = await session.call_tool(
                name="search_repositories",
                arguments={"query": "mcp", "perPage": 5}
            )
            print("🔁 Result:", result)

asyncio.run(run_client())