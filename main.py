import json
import os
import re
import base64
import uvicorn
from fastapi import FastAPI
from langfuse import Langfuse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import SystemMessage, HumanMessage


from config.config import RequestObject
from MarketInsight.components.agent import agent
from MarketInsight.utils.logger import get_logger

logger = get_logger(__name__)
app = FastAPI()

# ============================================================
# Helper function to format response with images
# ============================================================

def format_response_with_images(response_text: str) -> dict:
    """Format response to handle base64 images separately for frontend"""
    
    # Pattern to match base64 encoded images
    image_pattern = r'data:image/(png|jpg|jpeg|gif);base64,([A-Za-z0-9+/=]+)'
    
    # Find all images in the response
    images = re.findall(image_pattern, response_text)
    
    if images:
        # Split the response by image markers
        parts = re.split(image_pattern, response_text)
        
        formatted_response = {
            "text": "",
            "images": []
        }
        
        # Process text parts and images
        for i, part in enumerate(parts):
            if part and not re.match(r'^png|jpg|jpeg|gif$', part):
                # This is text content
                formatted_response["text"] += part
            elif i < len(images) and i > 0:
                # This is an image (format, base64_data)
                image_format, base64_data = images[i-1]
                formatted_response["images"].append({
                    "format": image_format,
                    "data": base64_data
                })
        
        return formatted_response
    else:
        # No images found, return simple text response
        return {"text": response_text, "images": []}

# ============================================================
# CORS Middleware
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your Vercel URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Langfuse Configuration
# ============================================================

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL")
)

# ============================================================
# Health Check Endpoint
# ============================================================

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Service is running"
    }


# ============================================================
# Chat Endpoint
# ============================================================

@app.post("/api/chat")
async def chat(request: RequestObject):

    config = {
        "configurable": {
            "thread_id": request.threadId
        }
    }

    async def generate():
        try:
            logger.info("Generate function entered")

            # ====================================================
            # Langfuse Span
            # ====================================================
            with langfuse.start_as_current_observation(
                as_type="span",
                name="chat-request",
                input=request.prompt.content
            ) as span:

                span.update(
                    metadata={
                        "user_id": request.threadId
                    }
                )

                # ====================================================
                # Langfuse Generation
                # ====================================================
                with langfuse.start_as_current_observation(
                    as_type="generation",
                    name="agent-stream",
                    model="agentic-workflow",
                    input=request.prompt.content
                ) as generation:

                    full_response = ""

                    logger.info(
                        "Calling agent.invoke()"
                    )

                    # ====================================================
                    # Agent Call
                    # ====================================================

                    response = agent.invoke(
                        {
                            "messages": [
                                SystemMessage(
                                    content="""
You are a professional global stock market analyst with access to real-time financial data tools. Your goal is to provide comprehensive, well-formatted responses that help users make informed decisions about stock markets worldwide.

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

6. For questions about commodities (gold, silver, oil, etc.):
   - Use get_commodity_price() tool to get current commodity prices
   - Provide prices ONLY in INR (₹) with relevant context

7. For questions asking for graphs, charts, or visualizations:
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

8. For questions about stocks in specific price ranges (e.g., "1 rupee stocks", "stocks under ₹10"):
   - Use screen_stocks_by_price() tool with appropriate max_price parameter
   - For "1 rupee stocks", use max_price=1.0
   - For "stocks under ₹10", use max_price=10.0
   - Present the results with company names, prices, and relevant details

9. Never guess stock tickers - use get_ticker() tool to find them.

10. Always try to be helpful and provide actionable insights based on available data.

11. When presenting stock information, always include:
   - Company name in bold
   - Current price ONLY in INR (₹)
   - Percentage change
   - Additional relevant details (market cap, volume, sector) if available

12. Focus exclusively on Indian markets (NSE/BSE). Do not provide international market data unless specifically requested.
"""
                                ),
                                HumanMessage(
                                    content=request.prompt.content
                                )
                            ]
                        },
                        config=config
                    )
                    logger.info("agent.invoke() completed")
                    logger.info(f"Agent response: {response}")

                    text_output = ""

                    # ====================================================
                    # Extract ONLY AI Response
                    # ====================================================

                    messages = response.get(
                        "messages",
                        []
                    )

                    logger.info(f"Total messages: {len(messages)}")
                    for i, msg in enumerate(messages):
                        logger.info(
                            f"MSG {i}: {msg.__class__.__name__} -> {str(getattr(msg, 'content', ''))[:200]}"
                        )

                    for message in reversed(messages):

                        logger.info(
                            f"Message Type: {message.__class__.__name__}"
                        )

                        if message.__class__.__name__ != "AIMessage":
                            continue

                        content = getattr(
                            message,
                            "content",
                            None
                        )

                        if not content:
                            continue

                        if isinstance(content, str):
                            text_output = content

                        elif isinstance(content, list):

                            for item in content:

                                if isinstance(item, dict):
                                    text_output += item.get(
                                        "text",
                                        ""
                                    )

                                elif isinstance(item, str):
                                    text_output += item

                        break

                    logger.info("=" * 50)
                    logger.info(f"FINAL AI RESPONSE:\n{text_output}")
                    logger.info("=" * 50)



                    # ====================================================
                    # Fallback response
                    # ====================================================

                    if not text_output:
                        text_output = (
                            "No response generated."
                        )

                    full_response += text_output

                    # ====================================================
                    # Stream to frontend (SSE FORMAT)
                    # ====================================================

                    # ====================================================
                    # Stream to frontend
                    # ====================================================

                    if text_output is not None:
                        text_output = str(text_output)

                        if text_output.strip():
                            yield f"data: {json.dumps({'type': 'message', 'content': text_output})}\n\n"

                    # ====================================================
                    # Update Langfuse
                    # ====================================================

                    generation.update(
                        output=full_response
                    )

                span.update(
                    output="Request completed successfully"
                )

        except Exception as e:
            logger.exception(
                "Full chat error"
            )

            if hasattr(e, "response"):
                logger.error(
                    f"Response: {e.response}"
                )

            if hasattr(e, "body"):
                logger.error(
                    f"Body: {e.body}"
                )

            error_message = str(e)
            
            # Handle rate limit errors specifically
            if "rate limit" in error_message.lower() or "429" in error_message:
                # Extract actual wait time from error body if available
                wait_time = "approximately 11 minutes"
                if hasattr(e, "body") and isinstance(e.body, dict):
                    error_msg = e.body.get("message", "")
                    # Pattern to match "Please try again in XmY.ZZZs"
                    match = re.search(r"Please try again in (\d+m)?(\d+\.\d+)?s", error_msg)
                    if match:
                        minutes = match.group(1)
                        seconds = match.group(2)
                        if minutes and seconds:
                            # Round seconds to 2 decimal places
                            seconds_rounded = round(float(seconds), 2)
                            wait_time = f"approximately {minutes} {seconds_rounded} seconds"
                        elif seconds:
                            seconds_rounded = round(float(seconds), 2)
                            wait_time = f"approximately {seconds_rounded} seconds"
                        elif minutes:
                            wait_time = f"approximately {minutes}"
                
                error_message = (
                    "⚠️ **API Rate Limit Reached**\n\n"
                    "You've reached the rate limit for the OpenAI API. "
                    "The system has used nearly all available tokens.\n\n"
                    f"**To continue using the app:**\n"
                    f"• Wait {wait_time} for the rate limit to reset\n"
                    "• Check your OpenAI usage at: https://platform.openai.com/usage\n\n"
                    "We apologize for the inconvenience. The limit will reset automatically."
                )
            elif "timeout" in error_message.lower():
                error_message = (
                    "⏱️ **Request Timeout**\n\n"
                    "The request took too long to process. This could be due to:\n"
                    "• Slow internet connection\n"
                    "• High server load\n"
                    "• Complex query requiring extensive processing\n\n"
                    "Please try again with a simpler question or check your connection."
                )
            else:
                error_message = (
                    f"❌ **An error occurred:** {error_message}\n\n"
                    "Please try again or contact support if the issue persists."
                )
            
            logger.error(error_message)
            yield f"data: {json.dumps({'type': 'error', 'content': error_message})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":
            "no-cache, no-transform",
            "Connection":
            "keep-alive",
            "X-Accel-Buffering":
            "no"
        }
    )


# ============================================================
# Run App
# ============================================================

if __name__ == "__main__":
    try:
        logger.info(
            "App Initiated Successfully"
        )

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
    except Exception as e:
        logger.exception(
            "Failed to start server"
        )
        print(f"Error: {str(e)}")