
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
#from langchain_google_genai import ChatGoogleGenerativeAI
from MarketInsight.utils.tools import *
from MarketInsight.utils.logger import get_logger
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

load_dotenv()
logger = get_logger(__name__)

# ============================================================
# Original TheSys/OpenAI configuration (keep for later)
# ============================================================

# model = ChatOpenAI(
#     model="c1/openai/gpt-5/v-20250930",
#     base_url="https://api.thesys.dev/v1/embed/",
#     api_key=os.getenv("THESYS_API_KEY")
# )

# ============================================================
# Grok API (xAI) configuration - keep for later
# ============================================================

# model = ChatOpenAI(
#     model="grok-2",
#     base_url="https://api.x.ai/v1",
#     api_key=os.getenv("GROK_API_KEY")
# )

# ============================================================
# Gemini API configuration - keep for later
# ============================================================

# model = ChatGoogleGenerativeAI(
#     model="gemini-2.0-flash",
#     google_api_key=os.getenv("GEMINI_API_KEY"),
#     temperature=0
# )

# ============================================================
# OpenAI API configuration (ACTIVE)
# ============================================================

openai_api_key = os.getenv("OPENAI_API_KEY", "")

if not openai_api_key:
    raise ValueError(
        "OPENAI_API_KEY environment variable is not set."
    )

model = ChatOpenAI(
    model="gpt-4o",
    api_key=openai_api_key,
    temperature=0
)

# ============================================================
# Force tool outputs to string
# ============================================================

def patch_tool(tool):
    original_func = tool.func

    def safe_func(*args, **kwargs):
        try:
            result = original_func(*args, **kwargs)

            if result is None:
                return "No data found."

            return str(result)

        except Exception as e:
            logger.error(
                f"Tool {tool.name} failed: {str(e)}"
            )
            return f"Tool error: {str(e)}"

    tool.func = safe_func
    return tool


# ============================================================
# Patch all tools
# ============================================================

tools = [
    patch_tool(get_stock_price),
    patch_tool(get_historical_data),
    patch_tool(get_stock_news),
    patch_tool(get_balance_sheet),
    patch_tool(get_income_statement),
    patch_tool(get_cash_flow),
    patch_tool(get_company_info),
    patch_tool(get_dividends),
    patch_tool(get_splits),
    patch_tool(get_institutional_holders),
    patch_tool(get_major_shareholders),
    patch_tool(get_mutual_fund_holders),
    patch_tool(get_insider_transactions),
    patch_tool(get_analyst_recommendations),
    patch_tool(get_analyst_recommendations_summary),
    patch_tool(get_ticker),
    patch_tool(get_market_indices),
    patch_tool(get_market_movers),
    patch_tool(get_sector_performance),
    patch_tool(screen_stocks_by_price),
    patch_tool(generate_stock_graph),
]

# ============================================================
# Agent creation
# ============================================================

agent = create_agent(
    model,
    tools=tools,
    checkpointer=MemorySaver()
)

logger.info(
    "Agent Initiated Successfully with OpenAI API"
)
