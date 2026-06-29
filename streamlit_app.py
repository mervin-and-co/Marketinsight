import streamlit as st
import re
import base64
import io
from datetime import datetime

# Lazy imports - only load when needed
@st.cache_resource
def get_agent():
    """Lazy load the agent to improve startup time"""
    from MarketInsight.components.agent import agent
    return agent

@st.cache_resource
def get_logger_instance():
    """Lazy load the logger to improve startup time"""
    from MarketInsight.utils.logger import get_logger
    return get_logger(__name__)

logger = get_logger_instance()

# ============================================================
# Direct Graph Generation Helper
# ============================================================

def generate_graph_directly(ticker: str = None, sector: str = None, commodity: str = None, period: str = "1mo"):
    """Generate graph directly without sending base64 to AI"""
    try:
        # Lazy load heavy libraries only when needed
        import yfinance as yf
        import matplotlib
        matplotlib.use('Agg')  # Set backend before importing pyplot
        import matplotlib.pyplot as plt
        
        # Optimize matplotlib performance
        matplotlib.rcParams['figure.max_open_warning'] = False
        matplotlib.rcParams['agg.path.chunksize'] = 10000
        
        # Define commodity tickers
        commodity_tickers = {
            "gold": "GC=F",
            "silver": "SI=F", 
            "oil": "CL=F",
            "copper": "HG=F",
            "natural gas": "NG=F",
            "platinum": "PL=F",
            "palladium": "PA=F"
        }
        
        # Determine what to plot
        if ticker:
            symbol = ticker
            title = f"Stock Price: {ticker}"
        elif commodity and commodity.lower() in commodity_tickers:
            symbol = commodity_tickers[commodity.lower()]
            title = f"Commodity Price: {commodity.capitalize()}"
        else:
            return None
        
        # Currency conversion function
        def get_inr_price(price_usd=None):
            try:
                usd_inr = yf.Ticker('USDINR=X').info.get('regularMarketPrice', 83.5)
                return round(price_usd * usd_inr, 2) if price_usd else None
            except:
                return round(price_usd * 83.5, 2) if price_usd else None
        
        # Fetch data
        stock = yf.Ticker(symbol)
        hist = stock.history(period=period)
        
        if hist.empty:
            return None
        
        # Convert to INR
        close_prices = hist['Close']
        close_inr = [get_inr_price(price_usd=price) for price in close_prices]
        
        # Create plot
        plt.figure(figsize=(12, 6))
        dates = hist.index
        plt.plot(dates, close_inr, label=title, linewidth=2, color='gold' if commodity else 'blue')
        plt.title(title, fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Price (₹)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend(loc='best', fontsize=10)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf.getvalue()
        
    except Exception as e:
        logger.error(f"Error generating graph directly: {e}")
        return None

# ============================================================
# Image Display Helper
# ============================================================

def display_response_with_images(response_text: str):
    """Display response text and render any base64 encoded images"""
    
    # Check if this is a graph generation response (handle various formats)
    # First normalize the text by removing line breaks
    normalized_text = response_text.replace('\n', ' ').replace('\r', ' ')
    
    graph_patterns = [
        r'GRAPH_GENERATED:([^:]+):([^:]+):(\w+)',  # GRAPH_GENERATED:ticker:sector:period
        r'GRAPH_GENERATED:([^:]+):(\w+)',           # GRAPH_GENERATED:commodity:period
        r'GRAPH\s*_GENERATED:([^:]+):([^:]+):(\w+)', # Handle with underscore
        r'GRAPH\s+GENERATED:([^:]+):([^:]+):(\w+)',  # Handle with space
    ]
    
    for pattern in graph_patterns:
        match = re.search(pattern, normalized_text)
        if match:
            if len(match.groups()) == 3:
                ticker, sector_or_commodity, period = match.groups()
            else:
                sector_or_commodity, period = match.groups()
                ticker = None
            
            # Display the text response (remove the graph ID part)
            text_part = re.sub(r'\[Graph ID:.*?\]', '', response_text).strip()
            # Also remove any failed image display messages
            text_part = re.sub(r'Failed to display image:.*', '', text_part).strip()
            # Remove any GRAPH_GENERATED text (and variations)
            text_part = re.sub(r'GRAPH\s*_?GENERATED:.*', '', text_part).strip()
            # Remove any markdown image links that failed
            text_part = re.sub(r'!\[.*?\]\(.*?\)', '', text_part).strip()
            
            if text_part:
                st.markdown(text_part)
            
            # Generate graph directly
            if ticker and ticker != "None":
                graph_image = generate_graph_directly(ticker=ticker, period=period)
            elif sector_or_commodity:
                # Check if it's a commodity
                commodities = ["gold", "silver", "oil", "copper", "natural gas", "platinum", "palladium"]
                if sector_or_commodity.lower() in commodities:
                    graph_image = generate_graph_directly(commodity=sector_or_commodity, period=period)
                else:
                    graph_image = generate_graph_directly(sector=sector_or_commodity, period=period)
            else:
                graph_image = None
            
            if graph_image:
                st.image(graph_image, width='stretch', caption="Market Graph")
            else:
                st.error("Failed to generate graph")
            return
    
    # Pattern to match base64 encoded images
    image_pattern = r'data:image/(png|jpg|jpeg|gif);base64,([A-Za-z0-9+/=]+)'
    
    # Find all images in the response
    images = re.findall(image_pattern, response_text)
    
    if images:
        # Split the response by image markers
        parts = re.split(image_pattern, response_text)
        
        image_index = 0
        # Display text parts and images alternately
        for i, part in enumerate(parts):
            if part and not re.match(r'^png|jpg|jpeg|gif$', part):
                # This is text content
                if part.strip():  # Only display non-empty text
                    st.markdown(part)
            elif image_index < len(images):
                # This is an image (format, base64_data)
                try:
                    image_format, base64_data = images[image_index]
                    # Decode and display the image
                    image_bytes = base64.b64decode(base64_data)
                    st.image(image_bytes, width='stretch', caption="Market Graph")
                    image_index += 1
                except Exception as e:
                    logger.error(f"Error displaying image: {e}")
                    st.error(f"Failed to display image: {str(e)}")
    else:
        # No images found, display as normal markdown
        st.markdown(response_text)

# ============================================================
# Streamlit Page Config
# ============================================================

st.set_page_config(
    page_title="Market Insight",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Market Insight")
st.markdown("Ask me anything about the stock market!")

# ============================================================
# Initialize Chat History
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

# ============================================================
# Chat Name Generator
# ============================================================

def generate_chat_name(messages):
    """Generate a chat name based on the first user message"""
    if not messages:
        return "New Chat"
    
    # Find the first user message
    for message in messages:
        if message["role"] == "user":
            first_message = message["content"]
            # Take first 3-5 words and clean up
            words = first_message.split()[:4]
            chat_name = " ".join(words)
            # Capitalize and add ellipsis if truncated
            chat_name = chat_name.capitalize()
            if len(first_message.split()) > 4:
                chat_name += "..."
            return chat_name
    
    return "New Chat"

# ============================================================
# Display Chat History
# ============================================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        display_response_with_images(message["content"])

# ============================================================
# Agent Response Handler
# ============================================================

def get_agent_response(prompt: str, thread_id: str) -> str:
    """Get response from agent directly"""
    
    # Lazy load heavy imports only when needed
    from langchain_core.messages import SystemMessage, HumanMessage
    
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    try:
        agent_instance = get_agent()  # Use the cached agent
        response = agent_instance.invoke(
            {
                "messages": [
                    SystemMessage(
                        content="""You are a professional global stock market analyst with access to real-time financial data tools. Your goal is to provide comprehensive, well-formatted responses that help users make informed decisions about stock markets worldwide.

CRITICAL RULE - ALWAYS USE TOOLS FOR DATA:
- You have direct access to real-time stock data through your tools
- NEVER tell users to "check financial news platforms" or "use stock market apps"
- ALWAYS use your tools to fetch actual data and provide it directly
- Your tools ARE the data source - use them proactively for every stock-related query
- Generic advice without actual data is NOT acceptable

DOMAIN FOCUS:
- Your primary focus is stock markets, financial data, investments, commodities, and economic indicators globally
- You should answer ALL questions related to stocks, shares, market analysis, company information, investment advice, trading, and financial markets
- Examples of valid topics: stock prices, market indices, company performance, investment strategies, trading tips, financial ratios, market trends, sector analysis, commodity prices, etc.
- Support for major markets: Indian (NSE/BSE), US (NYSE/NASDAQ), European (LSE, Euronext), Asian (Tokyo, Hong Kong, Singapore), and other global markets
- CRITICAL: Reject any comparisons between stock market and non-stock-market topics (e.g., "fish market vs stock market", "vegetable market vs stock market", "real estate vs stock market")
- If a question asks to compare stock market with unrelated markets or topics, politely decline and explain that you only handle stock market and financial market queries
- Only reject questions that are completely unrelated to finance/investments (e.g., programming help, cooking recipes, personal advice not related to money, general knowledge questions, etc.)
- If a question is clearly outside your domain, politely explain your focus and suggest they ask market-related questions

RESPONSE FORMATTING RULES:

1. Use **bold text** for stock names, company names, and key highlights
2. Use bullet points (•) for listing information and details
3. Use emojis where appropriate to make responses engaging (📈, 📉, 💰, etc.)
4. Organize information in clear sections with headers
5. Show prices in the appropriate currency based on the market:
   - Indian stocks: INR (₹)
   - US stocks: USD ($)
   - European stocks: EUR (€) or GBP (£)
   - Other markets: local currency with USD conversion if helpful
6. Include percentage changes with + or - signs
7. Provide context and analysis, not just raw data

TOOL USAGE RULES:

1. Use get_ticker() when the user mentions a specific company name to get the correct ticker symbol.

VALID:
- Reliance Industries, Infosys, TCS, HDFC Bank, ICICI Bank, Tata Motors, etc.

2. For market-level questions about status, performance, or trends:
   - Use get_market_indices() for Indian indices performance (NSE Nifty 50, BSE Sensex)
   - Use get_market_movers() for top gainers and losers among Indian stocks
   - Use get_sector_performance() for sector-wise performance analysis
   - Provide specific data with percentages and explanations
   - IMPORTANT: Even if markets are closed, use these tools to get the latest available data
   - Always mention that the data is from the most recent market close when markets are not currently open

3. Use tools proactively when you have a valid ticker:
   - get_stock_price for current prices
   - get_historical_data for historical trends
   - get_stock_news for recent news (ONLY when user specifically asks for news)
   - get_company_info for company details
   - Other financial tools as needed

4. For questions about "which stock did well today" or "best performing stock":
   - MUST use get_market_movers() to get actual performance data
   - DO NOT use get_stock_news() for these questions
   - Present the top gainers with their percentage changes and additional details
   - Provide context about market conditions and sector performance

5. For historical data requests (e.g., "last 7 days of Reliance stock"):
   - Use get_ticker() to get the correct symbol
   - Use get_historical_data() with appropriate date range
   - Present the data in a clear, readable format with trends and analysis

6. For questions asking for graphs, charts, or visualizations:
   - Use generate_stock_graph() tool to create visual representations
   - For sector graphs (e.g., "show me automobile sector graph"), use sector parameter with sector name
   - For individual stock graphs, use ticker parameter with stock symbol
   - For commodity graphs (e.g., "graph of gold price"), use commodity parameter with commodity name
   - Supported Indian sectors: automobile, technology, banking, pharma, fmcg, energy, metal
   - Supported US sectors: us technology, us banking, us healthcare, us energy
   - Supported European sectors: european technology, european banking
   - Supported commodities: gold, silver, oil, copper, natural gas, platinum, palladium
   - Supported periods: "1mo", "3mo", "6mo", "1y", "max"
   - The tool returns a success message with a graph identifier - the actual graph will be generated and displayed automatically in the chat interface

7. For questions about stocks in specific price ranges (e.g., "1 rupee stocks", "stocks under ₹10"):
   - Use screen_stocks_by_price() tool with appropriate max_price parameter
   - For "1 rupee stocks", use max_price=1.0
   - For "stocks under ₹10", use max_price=10.0
   - Present the results with company names, prices, and relevant details

8. Never guess stock tickers - use get_ticker() tool to find them.

9. Always try to be helpful and provide actionable insights based on available data.

10. When presenting stock information, always include:
   - Company name in bold
   - Current price ONLY in INR (₹)
   - Percentage change
   - Additional relevant details (market cap, volume, sector) if available

11. Focus exclusively on Indian markets (NSE/BSE). Do not provide international market data unless specifically requested.

12. FOR ANY STOCK PERFORMANCE QUERY:
    - First use get_ticker() to get the symbol
    - Then use get_stock_price() to get current price and performance
    - Then use get_company_info() to get additional details
    - Provide the actual data, not generic advice
"""
                    ),
                    HumanMessage(
                        content=prompt
                    )
                ]
            },
            config=config
        )
        
        # Extract AI response
        messages = response.get("messages", [])
        text_output = ""
        
        for message in reversed(messages):
            if message.__class__.__name__ != "AIMessage":
                continue
            
            content = getattr(message, "content", None)
            if not content:
                continue
            
            if isinstance(content, str):
                text_output = content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text_output += item.get("text", "")
                    elif isinstance(item, str):
                        text_output += item
            break
        
        return text_output if text_output else "No response generated."
        
    except Exception as e:
        logger.exception("Agent error")
        return f"❌ **Error:** {str(e)}"

# ============================================================
# Chat Input Handler
# ============================================================

if prompt := st.chat_input("Ask about stocks..."):
    # Generate thread ID if not exists
    if "thread_id" not in st.session_state:
        import uuid
        st.session_state.thread_id = str(uuid.uuid4())
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generate assistant response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Get response from agent
        with st.spinner("🔍 Analyzing your question and fetching latest market data..."):
            full_response = get_agent_response(prompt, st.session_state.thread_id)
        
        # Display response with images if present
        display_response_with_images(full_response)
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    
    # Force rerun to refresh the chat history display
    st.rerun()

# ============================================================
# Sidebar Info
# ============================================================

with st.sidebar:
    st.header("About")
    st.markdown("This is a stock market analysis assistant powered by AI.")
    
    st.header("Current Chat")
    if st.session_state.messages:
        chat_name = generate_chat_name(st.session_state.messages)
        st.text(f"📝 {chat_name}")
    else:
        st.text("📝 New Chat")
    
    st.header("Tips")
    st.info("💡 Ask about stock prices, market analysis, company information, or investment insights.")
