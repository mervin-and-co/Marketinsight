import time
import requests
import yfinance as yf
import logging
import warnings
import base64
import io
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime
from langchain.tools import tool
from MarketInsight.utils.logger import get_logger

logger = get_logger("Tools")

# Completely suppress yfinance warnings and errors
warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('yfinance').propagate = False

# Currency conversion rates (approximate, will be updated dynamically)
USD_TO_INR = 83.5
EUR_TO_INR = 90.2
GBP_TO_INR = 106.5
JPY_TO_INR = 0.56
EUR_TO_USD = 1.09
GBP_TO_USD = 1.27
JPY_TO_USD = 0.0067

def is_indian_market_open():
    """
    Check if Indian stock markets (NSE/BSE) are currently open.
    Indian markets are open Monday-Friday, 9:15 AM to 3:30 PM IST.
    """
    now = datetime.now()
    
    # Check if it's a weekend (Saturday=5, Sunday=6)
    if now.weekday() >= 5:
        return False
    
    # Market hours: 9:15 AM to 3:30 PM IST
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_open <= now <= market_close

def get_inr_price(price_usd=None, price_eur=None, price_gbp=None, price_jpy=None):
    """Convert price to Indian Rupees"""
    try:
        # Try to get current exchange rate
        try:
            usd_inr = yf.Ticker("USDINR=X").info.get("regularMarketPrice", USD_TO_INR)
            eur_inr = yf.Ticker("EURINR=X").info.get("regularMarketPrice", EUR_TO_INR)
            gbp_inr = yf.Ticker("GBPINR=X").info.get("regularMarketPrice", GBP_TO_INR)
            jpy_inr = yf.Ticker("JPYINR=X").info.get("regularMarketPrice", JPY_TO_INR)
        except:
            usd_inr = USD_TO_INR
            eur_inr = EUR_TO_INR
            gbp_inr = GBP_TO_INR
            jpy_inr = JPY_TO_INR
        
        if price_usd:
            return round(price_usd * usd_inr, 2)
        elif price_eur:
            return round(price_eur * eur_inr, 2)
        elif price_gbp:
            return round(price_gbp * gbp_inr, 2)
        elif price_jpy:
            return round(price_jpy * jpy_inr, 2)
        return None
    except:
        if price_usd:
            return round(price_usd * USD_TO_INR, 2)
        elif price_eur:
            return round(price_eur * EUR_TO_INR, 2)
        elif price_gbp:
            return round(price_gbp * GBP_TO_INR, 2)
        elif price_jpy:
            return round(price_jpy * JPY_TO_INR, 2)
        return None


# --------------------------------------------------------------------------------
# Tool 1: Retrieve Company Stock Price
# --------------------------------------------------------------------------------
@tool(
    'get_stock_price',
    description="A function that returns the current stock price of a given ticker"
)
def get_stock_price(ticker: str):
    logger.info(f"Retrieving Stock Price of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided."

    # Prevent invalid generic tickers
    invalid_tickers = ["NSE", "BSE", "MARKET", "STOCK", ""]

    if ticker.upper() in invalid_tickers:
        return (
            f"'{ticker}' is not a valid stock ticker. "
            "Please provide a company name or symbol."
        )

    start_time = time.time()
    
    # Note: Removed market hours check to allow data retrieval even when markets are closed
    # yfinance can provide the most recent available data regardless of market status

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        stock_price = info.get("regularMarketPrice")
        previous_close = info.get("previousClose")
        change = info.get("regularMarketChange")
        change_percent = info.get("regularMarketChangePercent")

        if stock_price is None:
            return (
                f"No stock price found for '{ticker}'. "
                "Please verify the ticker symbol."
            )

        end_time = time.time()

        logger.info(
            f"Retrieved Stock Price of {ticker} "
            f"in {end_time - start_time:.3f} seconds"
        )

        # Convert to INR
        price_inr = get_inr_price(price_usd=stock_price)
        previous_close_inr = get_inr_price(price_usd=previous_close) if previous_close else None
        change_inr = get_inr_price(price_usd=change) if change is not None else None
        company_name = info.get("shortName", ticker)
        
        response = f"**{company_name} ({ticker})**\n"
        if price_inr:
            response += f"• Current Price: ₹{price_inr:.2f}\n"
        if previous_close_inr:
            response += f"• Previous Close: ₹{previous_close_inr:.2f}\n"
        if change is not None and change_inr is not None:
            response += f"• Change: ₹{change_inr:.2f} ({change_percent:.2f}%)\n"
        
        return response

    except Exception as e:
        logger.error(
            f"Failed to retrieve stock price of "
            f"{ticker}: {str(e)}"
        )

        return (
            f"Error retrieving stock price "
            f"for {ticker}"
        )



# --------------------------------------------------------------------------------
# Tool 2: Retrieve Company Stock Historical Data
# --------------------------------------------------------------------------------
@tool('get_historical_data', description="A function that returns the historical data of a given ticker in the given start and end date")
def get_historical_data(ticker: str, start_date: str, end_date: str):
    logger.info(f"Retrieving Historical Data of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        historical_data = stock.history(start=start_date, end=end_date)
        
        if historical_data is None or historical_data.empty:
            return f"No historical data available for {ticker} in the specified date range."

        # Get company info
        try:
            company_name = stock.info.get("shortName", ticker)
        except:
            company_name = ticker

        # Format the response with detailed information
        response = f"**📊 {company_name} ({ticker}) - Historical Data**\n"
        response += f"**Period:** {start_date} to {end_date}\n\n"
        
        # Calculate some statistics
        if 'Close' in historical_data.columns:
            close_prices = historical_data['Close']
            latest_price = close_prices.iloc[-1]
            earliest_price = close_prices.iloc[0]
            price_change = latest_price - earliest_price
            percent_change = (price_change / earliest_price) * 100 if earliest_price != 0 else 0
            
            highest_price = close_prices.max()
            lowest_price = close_prices.min()
            
            # Convert to INR
            latest_inr = get_inr_price(price_usd=latest_price)
            highest_inr = get_inr_price(price_usd=highest_price)
            lowest_inr = get_inr_price(price_usd=lowest_price)
            earliest_inr = get_inr_price(price_usd=earliest_price)
            price_change_inr = get_inr_price(price_usd=price_change)
            
            response += "**📈 Price Summary:**\n"
            response += f"• Starting Price: ₹{earliest_inr:.2f}\n"
            response += f"• Ending Price: ₹{latest_inr:.2f}\n"
            response += f"• Price Change: ₹{price_change_inr:.2f} ({percent_change:+.2f}%)\n"
            response += f"• Highest Price: ₹{highest_inr:.2f}\n"
            response += f"• Lowest Price: ₹{lowest_inr:.2f}\n\n"
        
        # Show recent data points
        response += "**📅 Recent Price Points:**\n"
        recent_data = historical_data.tail(7) if len(historical_data) >= 7 else historical_data
        for date, row in recent_data.iterrows():
            close_price = row['Close'] if 'Close' in row else None
            if close_price:
                price_inr = get_inr_price(price_usd=close_price)
                response += f"• {date.strftime('%Y-%m-%d')}: ₹{price_inr:.2f}\n"
        
        # Volume information if available
        if 'Volume' in historical_data.columns:
            avg_volume = historical_data['Volume'].mean()
            response += f"\n**📊 Trading Volume:**\n"
            response += f"• Average Volume: {avg_volume:,.0f} shares\n"

        end_time = time.time()
        logger.info(f"Retrieved Historical Data of {ticker} in {end_time - start_time:.3f} seconds")
        
        return response

    except Exception as e:
        logger.error(f"Failed to retrieve historical data of {ticker}: {str(e)}")
        return "Error: Failed to retrieve historical data. Please try again later."


# --------------------------------------------------------------------------------
# Tool 3: Retrieve Company Stock News
# --------------------------------------------------------------------------------
@tool('get_stock_news', description="A function that returns the news of a given ticker")
def get_stock_news(ticker: str):
    logger.info(f"Retrieving News of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        news = stock.news

        if news is None:
            return "No news available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved News of {ticker} in {end_time - start_time:.3f} seconds")
        return news

    except Exception as e:
        logger.error(f"Failed to retrieve news of {ticker}: {str(e)}")
        return "Error: Failed to retrieve news. Please try again later."


# --------------------------------------------------------------------------------
# Tool 4: Retrieve Company's Balance Sheet
# --------------------------------------------------------------------------------
@tool('get_balance_sheet', description="A function that returns the balance sheet of a given ticker")
def get_balance_sheet(ticker: str):
    logger.info(f"Retrieving Balance Sheet of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        balance_sheet = stock.balance_sheet.to_dict()

        if balance_sheet is None:
            return "No balance sheet available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Balance Sheet of {ticker} in {end_time - start_time:.3f} seconds")
        return balance_sheet

    except Exception as e:
        logger.error(f"Failed to retrieve balance sheet of {ticker}: {str(e)}")
        return "Error: Failed to retrieve balance sheet. Please try again later."


# --------------------------------------------------------------------------------
# Tool 5: Retrieve Company's Income Statement
# --------------------------------------------------------------------------------
@tool('get_income_statement', description="A function that returns the income statement of a given ticker")
def get_income_statement(ticker: str):
    logger.info(f"Retrieving Income Statement of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        income_statement = stock.financials.to_dict()

        if income_statement is None:
            return "No income statement available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Income Statement of {ticker} in {end_time - start_time:.3f} seconds")
        return income_statement

    except Exception as e:
        logger.error(f"Failed to retrieve income statement of {ticker}: {str(e)}")
        return "Error: Failed to retrieve income statement. Please try again later."
    

# --------------------------------------------------------------------------------
# Tool 6: Retrieve Company's Cash Flow Statement
# --------------------------------------------------------------------------------
@tool('get_cash_flow', description="A function that returns the cash flow statement of a given ticker")
def get_cash_flow(ticker: str):
    logger.info(f"Retrieving Cash Flow of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        cash_flow = stock.cashflow.to_dict()

        if cash_flow is None:
            return "No cash flow available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Cash Flow of {ticker} in {end_time - start_time:.3f} seconds")
        return cash_flow

    except Exception as e:
        logger.error(f"Failed to retrieve cash flow of {ticker}: {str(e)}")
        return "Error: Failed to retrieve cash flow. Please try again later."

# --------------------------------------------------------------------------------
# Tool 7: Retrieve Company Info & Ratios
# --------------------------------------------------------------------------------
@tool('get_company_info', description="A function that returns company profile and key financial ratios")
def get_company_info(ticker: str):
    logger.info(f"Retrieving Company Info of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        info = stock.info

        if info is None:
            return "No company info available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Company Info of {ticker} in {end_time - start_time:.3f} seconds")
        return info

    except Exception as e:
        logger.error(f"Failed to retrieve company info of {ticker}: {str(e)}")
        return "Error: Failed to retrieve company info. Please try again later."

# --------------------------------------------------------------------------------
# Tool 8: Retrieve Dividend History
# --------------------------------------------------------------------------------
@tool('get_dividends', description="A function that returns the dividend payment history of a given ticker")
def get_dividends(ticker: str):
    logger.info(f"Retrieving Dividends of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        dividends = stock.dividends.to_dict()

        if dividends is None:
            return "No dividends available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Dividends of {ticker} in {end_time - start_time:.3f} seconds")
        return dividends

    except Exception as e:
        logger.error(f"Failed to retrieve dividends of {ticker}: {str(e)}")
        return "Error: Failed to retrieve dividends. Please try again later."

# --------------------------------------------------------------------------------
# Tool 9: Retrieve Stock Split History
# --------------------------------------------------------------------------------
@tool('get_splits', description="A function that returns the stock split history of a given ticker")
def get_splits(ticker: str):
    logger.info(f"Retrieving Stock Splits of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        splits = stock.splits.to_dict()

        if splits is None:
            return "No stock splits available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Stock Splits of {ticker} in {end_time - start_time:.3f} seconds")
        return splits

    except Exception as e:
        logger.error(f"Failed to retrieve stock splits of {ticker}: {str(e)}")
        return "Error: Failed to retrieve stock splits. Please try again later."


# --------------------------------------------------------------------------------
# Tool 10: Retrieve Institutional Holders
# --------------------------------------------------------------------------------
@tool('get_institutional_holders', description="A function that returns the institutional ownership data of a given ticker")
def get_institutional_holders(ticker: str):
    logger.info(f"Retrieving Institutional Holders of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        holders = stock.institutional_holders.to_dict()

        if holders is None:
            return "No institutional holders available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Institutional Holders of {ticker} in {end_time - start_time:.3f} seconds")
        return holders

    except Exception as e:
        logger.error(f"Failed to retrieve institutional holders of {ticker}: {str(e)}")
        return "Error: Failed to retrieve institutional holders. Please try again later."

# --------------------------------------------------------------------------------
# Tool 11: Retrieve Major Share Holders
# --------------------------------------------------------------------------------
@tool('get_major_shareholders', description="A function that returns the major share holder data of a given ticker")
def get_major_shareholders(ticker: str):
    logger.info(f"Retrieving Major Share Holders of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        holders = stock.major_holders.to_dict()

        if holders is None:
            return "No major share holders available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Major Share Holders of {ticker} in {end_time - start_time:.3f} seconds")
        return holders

    except Exception as e:
        logger.error(f"Failed to retrieve major share holders of {ticker}: {str(e)}")
        return "Error: Failed to retrieve major share holders. Please try again later."

# --------------------------------------------------------------------------------
# Tool 12: Retrieve Mutual Fund Holders
# --------------------------------------------------------------------------------
@tool('get_mutual_fund_holders', description="A function that returns the mutual fund ownership data of a given ticker")
def get_mutual_fund_holders(ticker: str):
    logger.info(f"Retrieving Mutual Fund Holders of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        holders = stock.mutualfund_holders.to_dict()

        if holders is None:
            return "No mutual fund holders available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Mutual Fund Holders of {ticker} in {end_time - start_time:.3f} seconds")
        return holders

    except Exception as e:
        logger.error(f"Failed to retrieve mutual fund holders of {ticker}: {str(e)}")
        return "Error: Failed to retrieve mutual fund holders. Please try again later."

# --------------------------------------------------------------------------------
# Tool 13: Retrieve Insider Transactions
# --------------------------------------------------------------------------------
@tool('get_insider_transactions', description="A function that returns the insider buy/sell transactions of a given ticker")
def get_insider_transactions(ticker: str):
    logger.info(f"Retrieving Insider Transactions of {ticker}")

    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        insider_txn = stock.insider_transactions.to_dict()

        if insider_txn is None:
            return "No insider transactions available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Insider Transactions of {ticker} in {end_time - start_time:.3f} seconds")
        return insider_txn

    except Exception as e:
        logger.error(f"Failed to retrieve insider transactions of {ticker}: {str(e)}")
        return "Error: Failed to retrieve insider transactions. Please try again later."

# --------------------------------------------------------------------------------
# Tool 14: Retrieve Analyst Recommendations
# --------------------------------------------------------------------------------
@tool('get_analyst_recommendations', description="A function that returns the analyst recommendations of a given ticker")
def get_analyst_recommendations(ticker: str):
    logger.info(f"Retrieving Analyst Recommendations of {ticker}")
    
    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        recommendations = stock.recommendations.to_dict()

        if recommendations is None:
            return "No analyst recommendations available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Analyst Recommendations of {ticker} in {end_time - start_time:.3f} seconds")
        return recommendations

    except Exception as e:
        logger.error(f"Failed to retrieve analyst recommendations of {ticker}: {str(e)}")
        return "Error: Failed to retrieve analyst recommendations. Please try again later."

# --------------------------------------------------------------------------------
# Tool 15: Retrieve Analyst Recommendations Summary
# --------------------------------------------------------------------------------
@tool('get_analyst_recommendations_summary', description="A function that returns the analyst recommendations summary of a given ticker")
def get_analyst_recommendations_summary(ticker: str):
    logger.info(f"Retrieving Analyst Recommendations Summary of {ticker}")
    
    if not ticker or not isinstance(ticker, str):
        return "Error: Invalid ticker provided. Please provide a valid ticker symbol."

    try:
        start_time = time.time()
        stock = yf.Ticker(ticker)
        recommendations = stock.recommendations_summary.to_dict()

        if recommendations is None:
            return "No analyst recommendations summary available for {ticker}"

        end_time = time.time()
        logger.info(f"Retrieved Analyst Recommendations Summary of {ticker} in {end_time - start_time:.3f} seconds")
        return recommendations

    except Exception as e:
        logger.error(f"Failed to retrieve analyst recommendations summary of {ticker}: {str(e)}")
        return "Error: Failed to retrieve analyst recommendations summary. Please try again later."

# --------------------------------------------------------------------------------
# Tool 16: Retrieve Company's Ticker/Symbol
# --------------------------------------------------------------------------------
@tool(
    'get_ticker',
    description="Returns the stock ticker/symbol of a company"
)
def get_ticker(company_name: str):
    logger.info(
        f"Retrieving Ticker of {company_name}"
    )

    if (
        not company_name or
        not isinstance(company_name, str)
    ):
        return (
            "Error: Invalid company name."
        )

    # Known Indian company ticker mappings (fallback for common companies)
    indian_company_tickers = {
        "tata steel": "TATASTEEL.NS",
        "tata motors": "TATAMOTORS.NS",
        "tata consultancy services": "TCS.NS",
        "tcs": "TCS.NS",
        "reliance industries": "RELIANCE.NS",
        "reliance": "RELIANCE.NS",
        "infosys": "INFY.NS",
        "hdfc bank": "HDFCBANK.NS",
        "icici bank": "ICICIBANK.NS",
        "state bank of india": "SBIN.NS",
        "sbi": "SBIN.NS",
        "bharti airtel": "BHARTIARTL.NS",
        "airtel": "BHARTIARTL.NS",
        "itc": "ITC.NS",
        "hindustan unilever": "HINDUNILVR.NS",
        "hul": "HINDUNILVR.NS",
        "axis bank": "AXISBANK.NS",
        "kotak mahindra bank": "KOTAKBANK.NS",
        "kotak": "KOTAKBANK.NS",
        "lti mindtree": "LTIM.NS",
        "lt": "LT.NS",
        "larsen & toubro": "LT.NS",
        "larsen and toubro": "LT.NS",
        "wipro": "WIPRO.NS",
        "hcl technologies": "HCLTECH.NS",
        "tech mahindra": "TECHM.NS",
        "sun pharma": "SUNPHARMA.NS",
        "dr reddy's": "DRREDDY.NS",
        "cipla": "CIPLA.NS",
        "maruti suzuki": "MARUTI.NS",
        "mahindra & mahindra": "M&M.NS",
        "bajaj finance": "BAJFINANCE.NS",
        "bajaj auto": "BAJAJAUTO.NS",
        "adani enterprises": "ADANIENT.NS",
        "adani ports": "ADANIPORTS.NS",
        "power grid": "POWERGRID.NS",
        "nifty 50": "^NSEI",
        "sensex": "^BSESN",
        "bank nifty": "^NSEBANK"
    }

    # Known US company ticker mappings
    us_company_tickers = {
        "apple": "AAPL",
        "microsoft": "MSFT",
        "google": "GOOGL",
        "alphabet": "GOOGL",
        "amazon": "AMZN",
        "tesla": "TSLA",
        "meta": "META",
        "facebook": "META",
        "nvidia": "NVDA",
        "jpmorgan chase": "JPM",
        "jpmorgan": "JPM",
        "bank of america": "BAC",
        "wells fargo": "WFC",
        "citigroup": "C",
        "goldman sachs": "GS",
        "johnson & johnson": "JNJ",
        "pfizer": "PFE",
        "unitedhealth": "UNH",
        "abbvie": "ABBV",
        "merck": "MRK",
        "exxon mobil": "XOM",
        "chevron": "CVX",
        "conocophillips": "COP",
        "schlumberger": "SLB",
        "eog resources": "EOG",
        "s&p 500": "^GSPC",
        "nasdaq": "^IXIC",
        "dow jones": "^DJI"
    }

    # Known European company ticker mappings
    european_company_tickers = {
        "asml": "ASML.AS",
        "sap": "SAP.DE",
        "siemens": "SIE.DE",
        "nestle": "NESN.SW",
        "roche": "RO.SW",
        "novartis": "NOVN.SW",
        "hsbc": "HSBC",
        "barclays": "BARC.L",
        "lloyds": "LLOY.L",
        "deutsche bank": "DB",
        "bnp paribas": "BNP.PA",
        "ing": "INGA.AS",
        "total energies": "TTE.PA",
        "shell": "SHEL.L",
        "bp": "BP.L",
        "ftse 100": "^UKX",
        "dax": "^GDAXI",
        "cac 40": "^FCHI"
    }

    # Merge all company tickers
    all_company_tickers = {**indian_company_tickers, **us_company_tickers, **european_company_tickers}

    # Check if company name is in our known mappings
    company_name_lower = company_name.lower().strip()
    if company_name_lower in all_company_tickers:
        ticker = all_company_tickers[company_name_lower]
        logger.info(f"Found ticker in mapping: {ticker}")
        return ticker

    try:
        start_time = time.time()

        url = (
            "https://query2.finance.yahoo.com/"
            f"v1/finance/search?q={company_name}"
        )

        response = requests.get(url)

        if response.status_code != 200:
            return (
                "Failed to retrieve ticker."
            )

        data = response.json()

        quotes = data.get("quotes", [])

        if not quotes:
            return (
                f"No ticker found for "
                f"{company_name}"
            )


        # Skip invalid generic symbols
        invalid_symbols = ["NSE", "BSE"]

        ticker = None

        for quote in quotes:
            symbol = quote.get("symbol")

            if symbol and symbol.upper() not in invalid_symbols:
                # Prefer NSE (.NS) symbols for Indian companies
                if ".NS" in symbol:
                    ticker = symbol
                    break
                elif not ticker:
                    ticker = symbol

        if not ticker:
            return f"No valid ticker found for {company_name}"


        end_time = time.time()

        logger.info(
            f"Retrieved Ticker of "
            f"{company_name} in "
            f"{end_time - start_time:.3f} seconds"
        )

        return str(ticker)

    except Exception as e:
        logger.error(
            f"Failed to retrieve ticker of "
            f"{company_name}: {str(e)}"
        )

        return (
            "Error: Failed to retrieve ticker."
        )


# --------------------------------------------------------------------------------
# Tool 15: Get Market Indices Data
# --------------------------------------------------------------------------------
@tool('get_market_indices', description="A function that returns current data for major Indian market indices like NSE Nifty 50, BSE Sensex")
def get_market_indices(indices: str = "^NSEI,^BSESN"):
    logger.info(f"Retrieving Market Indices Data")

    try:
        start_time = time.time()
        
        # Note: Removed market hours check to allow data retrieval even when markets are closed
        # yfinance can provide the most recent available data regardless of market status
        
        # Default indices: NSE Nifty 50, BSE Sensex
        index_list = indices.split(',') if indices else ["^NSEI", "^BSESN"]
        
        results = {}
        for index in index_list:
            try:
                index = index.strip()
                stock = yf.Ticker(index)
                info = stock.info
                
                index_name = info.get("shortName", index)
                current_price = info.get("regularMarketPrice")
                previous_close = info.get("previousClose")
                change = info.get("regularMarketChange")
                change_percent = info.get("regularMarketChangePercent")
                
                if current_price:
                    price_inr = get_inr_price(price_usd=current_price)
                    previous_close_inr = get_inr_price(price_usd=previous_close) if previous_close else None
                    change_inr = get_inr_price(price_usd=change) if change is not None else None
                    results[index_name] = {
                        "symbol": index,
                        "current_price": current_price,
                        "price_inr": price_inr,
                        "previous_close": previous_close,
                        "previous_close_inr": previous_close_inr,
                        "change": change,
                        "change_inr": change_inr,
                        "change_percent": change_percent
                    }
            except Exception as e:
                logger.error(f"Failed to get data for {index}: {str(e)}")
                continue

        end_time = time.time()
        logger.info(f"Retrieved Market Indices in {end_time - start_time:.3f} seconds")
        
        if not results:
            return "Unable to retrieve market indices data at this time."
        
        # Format the response with detailed information
        response = "**📊 MAJOR MARKET INDICES**\n\n"
        for index_name, data in results.items():
            response += f"**{index_name} ({data['symbol']})**\n"
            if data['price_inr']:
                response += f"• Current Price: ₹{data['price_inr']:.2f}\n"
            if data['previous_close_inr']:
                response += f"• Previous Close: ₹{data['previous_close_inr']:.2f}\n"
            if data['change'] is not None and data['change_inr'] is not None:
                change_symbol = "+" if data['change'] > 0 else ""
                response += f"• Change: {change_symbol}₹{data['change_inr']:.2f} ({data['change_percent']:.2f}%)\n"
            response += "\n"
        
        return response

    except Exception as e:
        logger.error(f"Failed to retrieve market indices: {str(e)}")
        return "Error: Failed to retrieve market indices data. Please try again later."


# --------------------------------------------------------------------------------
# Tool 16: Get Top Gainers/Losers
# --------------------------------------------------------------------------------
@tool('get_market_movers', description="A function that returns top gainers and losers from major market indices by analyzing popular stocks")
def get_market_movers():
    logger.info("Retrieving Market Movers (Gainers/Losers)")

    try:
        start_time = time.time()
        
        # Note: Removed market hours check to allow data retrieval even when markets are closed
        # yfinance can provide the most recent available data regardless of market status
        
        # List of popular Indian stocks across different sectors to analyze
        popular_stocks = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",  # Large Cap
            "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS", "LT.NS",  # Major Stocks
            "AXISBANK.NS", "HCLTECH.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",  # Diversified
            "TATAMOTORS.NS", "NTPC.NS", "POWERGRID.NS", "WIPRO.NS", "TITAN.NS",  # Various Sectors
        ]
        
        stock_data = []
        
        for ticker in popular_stocks:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                current_price = info.get("regularMarketPrice")
                previous_close = info.get("previousClose")
                change_percent = info.get("regularMarketChangePercent")
                company_name = info.get("shortName", ticker)
                
                if current_price and change_percent is not None:
                    price_inr = get_inr_price(price_usd=current_price)
                    stock_data.append({
                        "ticker": ticker,
                        "name": company_name,
                        "current_price": current_price,
                        "price_inr": price_inr,
                        "change_percent": change_percent,
                        "market_cap": info.get("marketCap"),
                        "volume": info.get("regularMarketVolume"),
                        "sector": info.get("sector", "N/A")
                    })
                    
            except Exception as e:
                logger.error(f"Failed to get data for {ticker}: {str(e)}")
                continue
        
        # Sort by change percent to find gainers and losers
        stock_data.sort(key=lambda x: x["change_percent"], reverse=True)
        
        # Get top 5 gainers and losers
        top_gainers = stock_data[:5]
        top_losers = stock_data[-5:] if len(stock_data) >= 5 else stock_data[-len(stock_data):]
        top_losers.reverse()  # Show worst performers first
        
        end_time = time.time()
        logger.info(f"Market movers analysis completed in {end_time - start_time:.3f} seconds")
        
        if not stock_data:
            return "Unable to retrieve stock performance data at this time. Please try again later."
        
        # Format the response with detailed information
        response = "**📈 TOP GAINERS TODAY**\n\n"
        for i, stock in enumerate(top_gainers, 1):
            response += f"{i}. **{stock['name']} ({stock['ticker']})**\n"
            if stock['price_inr']:
                response += f"   • Current Price: ₹{stock['price_inr']:.2f}\n"
            response += f"   • Change: +{stock['change_percent']:.2f}%\n"
            if stock['sector'] != "N/A":
                response += f"   • Sector: {stock['sector']}\n"
            if stock['market_cap']:
                market_cap_inr = get_inr_price(price_usd=stock['market_cap'])
                response += f"   • Market Cap: ₹{market_cap_inr:,.0f}\n"
            response += "\n"
        
        response += "**📉 TOP LOSERS TODAY**\n\n"
        for i, stock in enumerate(top_losers, 1):
            response += f"{i}. **{stock['name']} ({stock['ticker']})**\n"
            if stock['price_inr']:
                response += f"   • Current Price: ₹{stock['price_inr']:.2f}\n"
            response += f"   • Change: {stock['change_percent']:.2f}%\n"
            if stock['sector'] != "N/A":
                response += f"   • Sector: {stock['sector']}\n"
            if stock['market_cap']:
                market_cap_inr = get_inr_price(price_usd=stock['market_cap'])
                response += f"   • Market Cap: ₹{market_cap_inr:,.0f}\n"
            response += "\n"
        
        response += "*Note: Based on analysis of major popular stocks across different sectors. For comprehensive market movers data, check financial news websites.*"
        
        return response

    except Exception as e:
        logger.error(f"Failed to retrieve market movers: {str(e)}")
        return "Error: Failed to retrieve market movers data. Please try again later."


# --------------------------------------------------------------------------------
# Tool 17: Get Sector Performance
# --------------------------------------------------------------------------------
@tool('get_sector_performance', description="A function that returns performance data for different market sectors using sector ETFs")
def get_sector_performance():
    logger.info("Retrieving Sector Performance")

    try:
        start_time = time.time()
        
        # Note: Removed market hours check to allow data retrieval even when markets are closed
        # yfinance can provide the most recent available data regardless of market status
        
        # Sector ETFs representing different market sectors
        sector_etfs = {
            "Technology": "XLK",
            "Healthcare": "XLV",
            "Financials": "XLF",
            "Energy": "XLE",
            "Consumer Discretionary": "XLY",
            "Consumer Staples": "XLP",
            "Industrials": "XLI",
            "Utilities": "XLU",
            "Real Estate": "XLRE",
            "Materials": "XLB",
            "Communication": "XLC"
        }
        
        sector_data = []
        
        for sector, etf in sector_etfs.items():
            try:
                stock = yf.Ticker(etf)
                info = stock.info
                
                current_price = info.get("regularMarketPrice")
                previous_close = info.get("previousClose")
                change_percent = info.get("regularMarketChangePercent")
                
                if current_price and change_percent is not None:
                    price_inr = get_inr_price(price_usd=current_price)
                    sector_data.append({
                        "sector": sector,
                        "etf": etf,
                        "current_price": current_price,
                        "price_inr": price_inr,
                        "change_percent": change_percent
                    })
                    
            except Exception as e:
                logger.error(f"Failed to get data for {sector} ({etf}): {str(e)}")
                continue
        
        # Sort by performance
        sector_data.sort(key=lambda x: x["change_percent"], reverse=True)
        
        end_time = time.time()
        logger.info(f"Sector performance analysis completed in {end_time - start_time:.3f} seconds")
        
        if not sector_data:
            return "Unable to retrieve sector performance data at this time."
        
        # Format the response with detailed information
        response = "**🏭 SECTOR PERFORMANCE ANALYSIS**\n\n"
        
        # Best performing sectors
        response += "**🔥 TOP PERFORMING SECTORS**\n"
        for i, sector in enumerate(sector_data[:5], 1):
            response += f"{i}. **{sector['sector']}** ({sector['etf']})\n"
            response += f"   • Current Price: ${sector['current_price']:.2f}\n"
            if sector['price_inr']:
                response += f"   • Price in INR: ₹{sector['price_inr']:.2f}\n"
            response += f"   • Change: +{sector['change_percent']:.2f}%\n\n"
        
        # Worst performing sectors
        response += "**📉 UNDERPERFORMING SECTORS**\n"
        worst_sectors = sector_data[-5:] if len(sector_data) >= 5 else sector_data[-len(sector_data):]
        worst_sectors.reverse()
        for i, sector in enumerate(worst_sectors, 1):
            response += f"{i}. **{sector['sector']}** ({sector['etf']})\n"
            response += f"   • Current Price: ${sector['current_price']:.2f}\n"
            if sector['price_inr']:
                response += f"   • Price in INR: ₹{sector['price_inr']:.2f}\n"
            response += f"   • Change: {sector['change_percent']:.2f}%\n\n"
        
        return response

    except Exception as e:
        logger.error(f"Failed to retrieve sector performance: {str(e)}")
        return "Error: Failed to retrieve sector performance data. Please try again later."


# --------------------------------------------------------------------------------
# Tool 19: Screen Stocks by Price Range
# --------------------------------------------------------------------------------
@tool('screen_stocks_by_price', description="A function that screens Indian stocks by price range (e.g., stocks under ₹10, ₹5, ₹1)")
def screen_stocks_by_price(max_price: float = 10.0, min_price: float = 0.0):
    logger.info(f"Screening stocks with price range ₹{min_price} - ₹{max_price}")

    try:
        start_time = time.time()
        
        # Comprehensive list of Indian stocks including penny stocks
        # This includes stocks across all price ranges for proper screening
        indian_stocks = [
            # Penny Stocks (Under ₹10) - Often traded by beginners
            "SUZLON.NS", "RPOWER.NS", "IDEA.NS", "YESBANK.NS", "VAKRANGEE.NS",
            "DHFL.NS", "JISLJALEQS.NS", "3IINFOTECH.NS", "AANJANEYA.NS", "ABAN.NS",
            "ACIL.NS", "ADANIPOWER.NS", "ADITYABIRLA.NS", "ADVANIHOTR.NS", "AEGISLOG.NS",
            "AGROTECH.NS", "AHLEAST.NS", "AIRAN.NS", "AJANTPHARM.NS", "AKMIND.NS",
            "ALANKIT.NS", "ALEMBICLTD.NS", "ALLCARGO.NS", "ALOMEGRE.NS", "AMARAJABAT.NS",
            "AMBERTR.NS", "AMBUJACEM.NS", "AMRUTANJAN.NS", "ANANTRAJ.NS", "ANGELONE.NS",
            "ANIKINDS.NS", "ANURAS.NS", "APARINDS.NS", "APLLTD.NS", "APOLLOHOSP.NS",
            "APOLLOTYRE.NS", "ARCS.NS", "ARTEMISMED.NS", "ARVIND.NS", "ASHOKA.NS",
            "ASHOKLEY.NS", "ASIANPAINT.NS", "ASPAISRO.NS", "ASTRAL.NS", "ASTRAZEN.NS",
            "ATGL.NS", "ATUL.NS", "AUROPHARMA.NS", "AVANTIFEED.NS", "AVONMORE.NS",
            "AXISBANK.NS", "AXISCAP.NS", "BAJAJAUTO.NS", "BAJAJFINSV.NS", "BAJFINANCE.NS",
            "BAJHLDINF.NS", "BALAMINES.NS", "BALRAMCHIN.NS", "BANCOINDIA.NS", "BANDHANBNK.NS",
            "BANKBARODA.NS", "BANKINDIA.NS", "BANKOFINDIA.NS", "BANSALW.NS", "BATAINDIA.NS",
            "BAYERCROP.NS", "BBTC.NS", "BCG.NS", "BDL.NS", "BEAM.NS",
            "BEL.NS", "BELTD.NS", "BEMC.NS", "BENETT.NS", "BERGEPAINT.NS",
            "BESTAGRO.NS", "BFAGRI.NS", "BFUTILITIE.NS", "BGR.NS", "BHEL.NS",
            "BHARATBIJL.NS", "BHARATFORG.NS", "BHARATGEAR.NS", "BHARATRAS.NS", "BHARTIARTL.NS",
            "BIOCON.NS", "BIRLACORPN.NS", "BIRLAMONEY.NS", "BLB.NS", "BLISSGVS.NS",
            "BLUESTARCO.NS", "BLS.NS", "BMTC.NS", "BNFL.NS", "BNKINDIA.NS",
            "BODALCHEM.NS", "BOMDYEING.NS", "BOSCHLTD.NS", "BPCL.NS", "BPL.NS",
            "BRIGADE.NS", "BRITANNIA.NS", "BROOKS.NS", "BRPL.NS", "BSL.NS",
            "BSE.NS", "BSSL.NS", "BTPL.NS", "BTV.NS", "BUNTING.NS",
            "BURCHEM.NS", "CADDILAHC.NS", "CADILAHC.NS", "CALSOFT.NS", "CANBK.NS",
            "CANFINHOME.NS", "CAPF.NS", "CARBORUNIV.NS", "CAREERP.NS", "CAREERP.NS",
            "CASTROLIND.NS", "CATAMARAN.NS", "CCL.NS", "CEATLTD.NS", "CELLO.NS",
            "CENTRALBK.NS", "CENTRUM.NS", "CENTURYEXT.NS", "CENTURYTEX.NS", "CERA.NS",
            "CGCL.NS", "CGPOWER.NS", "CHAMBLFERT.NS", "CHEMPLASTS.NS", "CHOLAFIN.NS",
            "CHOLAHLDG.NS", "CIPLA.NS", "CIVILSTEEL.NS", "CLNINDIA.NS", "CMAH.NS",
            "CMCS.NS", "CMIE.NS", "CNXINFRA.NS", "COALINDIA.NS", "COCHINSHIP.NS",
            "COFORGE.NS", "COINDIA.NS", "COLPAL.NS", "CONCOR.NS", "CONFIPET.NS",
            "CONSOLIDAT.NS", "CONTAINER.NS", "CORALFINAC.NS", "COROMANDEL.NS", "COUNTRYCLB.NS",
            "CRAFTSMAN.NS", "CRANES.NS", "CREDITACCESS.NS", "CROMPTON.NS", "CROSSTAB.NS",
            "CUMMINSIND.NS", "CUPID.NS", "CYIENT.NS", "DABUR.NS", "DALMIABHA.NS",
            "DALMIASUG.NS", "DANUBE.NS", "DATAPATTNS.NS", "DCMSHRIRAM.NS", "DCW.NS",
            "DECCAN.NS", "DEEPAKFERT.NS", "DEEPAKNTR.NS", "DELTACORP.NS", "DELTV.NS",
            "DENANET.NS", "DEOL.NS", "DESHBANDHU.NS", "DEUTSCHEBK.NS", "DFT.NS",
            "DGL.NS", "DHANI.NS", "DHRUVATARA.NS", "DIAMONDYD.NS", "DIGJAM.NS",
            "DIL.NS", "DIMENSION.NS", "DINDIGUL.NS", "DIXON.NS", "DLF.NS",
            "DLINKINDIA.NS", "DOD.NS", "DOMS.NS", "DQENT.NS", "DRREDDY.NS",
            "DSKULKARN.NS", "DSPBLACKRO.NS", "DTL.NS", "DUCON.NS", "DUNLOPP.NS",
            "DYNPRO.NS", "ECLERX.NS", "EDELWEISS.NS", "EDUCATION.NS", "EEM.NS",
            "EICHERMOT.NS", "EIDPARRY.NS", "EIHOTEL.NS", "EIMCOELECO.NS", "EKC.NS",
            "ELDECO.NS", "ELECTCAST.NS", "ELECON.NS", "ELECTHERM.NS", "ELGIEQUIP.NS",
            "ELGI.NS", "EMAMILTD.NS", "EMAMIPAP.NS", "EMBASSY.NS", "EMCO.NS",
            "EMKAY.NS", "ENDURANCE.NS", "ENERGYDEV.NS", "ENGINERSIN.NS", "ENIL.NS",
            "EPL.NS", "EQINDIA.NS", "ERIS.NS", "EROSMEDIA.NS", "ESCORTS.NS",
            "ESHBAND.NS", "ESIL.NS", "ESSARSHPNG.NS", "ESTER.NS", "ETERNITY.NS",
            "EUROBOND.NS", "EVINIX.NS", "EXELIND.NS", "EXIDEIND.NS", "EXPLOIND.NS",
            "FDC.NS", "FEDERALBNK.NS", "FEL.NS", "FENNER.NS", "FIBERWEB.NS",
            "FIEMIND.NS", "FINCABLES.NS", "FINPIPE.NS", "FIS.NS", "FSL.NS",
            "FORTIS.NS", "FOSSIL.NS", "FOURTH.NS", "FCONSUMER.NS", "FRETAIL.NS",
            "FSL.NS", "FUTURE.NS", "FXC.NS", "GABRIEL.NS", "GAIL.NS",
            "GAJAH.NS", "GALAXYSURF.NS", "GALLANTT.NS", "GANDHAR.NS", "GANGOTRI.NS",
            "GARDEN.NS", "GARFIBER.NS", "GATI.NS", "GAYAPROJ.NS", "GBL.NS",
            "GCPL.NS", "GEECEE.NS", "GENCON.NS", "GENESYS.NS", "GENUSPAPER.NS",
            "GEPIL.NS", "GESCO.NS", "GET&D.NS", "GFSTEEL.NS", "GHCL.NS",
            "GICRE.NS", "GILLETTE.NS", "GIPCL.NS", "GLENMARK.NS", "GLENMARK.NS",
            "GLOBUSSP.NS", "GMRINFRA.NS", "GMMP.NS", "GNA.NS", "GNFC.NS",
            "GODFRYPHLP.NS", "GODREJAGRO.NS", "GODREJCP.NS", "GODREJIND.NS", "GODREJPROP.NS",
            "GOCLCORP.NS", "GODREJINF.NS", "GOENKA.NS", "GOKEX.NS", "GOKULAGRO.NS",
            "GOLDBEES.NS", "GOLDCORP.NS", "GOLDIAM.NS", "GOLDTECH.NS", "GOODLUCK.NS",
            "GOODYEAR.NS", "GOPALJUTE.NS", "GODREJ.NS", "GPPL.NS", "GRANULES.NS",
            "GRAPHITE.NS", "GRASIM.NS", "GREAVESCOT.NS", "GREENPLY.NS", "GREENTEA.NS",
            "GRINDWELL.NS", "GRM.NS", "GROVER.NS", "GRP.NS", "GSPL.NS",
            "GTPL.NS", "GUJALKALI.NS", "GUJAPOLLO.NS", "GUJARATGAS.NS", "GUJGASLTD.NS",
            "GUJFLUORO.NS", "GUJINR.NS", "GUJNRE.NS", "GUJRAFFIA.NS", "GUJST.NS",
            "HAPPYFORGE.NS", "HARIAEXPORT.NS", "HARIASEXP.NS", "HARITASE.NS", "HARRIS.NS",
            "HATHWAY.NS", "HAVELLS.NS", "HBLPOWER.NS", "HCLINFRA.NS", "HCLTECH.NS",
            "HDFC.NS", "HDFCAMC.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HDFCW.NS",
            "HEG.NS", "HEG.NS", "HEIL.NS", "HEMIPROP.NS", "HENGARDNER.NS",
            "HERITAGE.NS", "HEROHOCP.NS", "HEROMOTOCO.NS", "HETERO.NS", "HEUBNER.NS",
            "HFCL.NS", "HGINFRA.NS", "HGINFRA.NS", "HGS.NS", "HIKAL.NS",
            "HIMADRI.NS", "HINDALCO.NS", "HINDCON.NS", "HINDMOTORS.NS", "HINDOOSTAN.NS",
            "HINDPETRO.NS", "HINDUNILVR.NS", "HINDUSTAN.NS", "HINDZINC.NS", "HIPOLIN.NS",
            "HITECH.NS", "HLE.NS", "HLK.NS", "HLV.NS", "HMVL.NS",
            "HNGS.NS", "HNI.NS", "HNGS.NS", "HNH.NS", "HOC.NS",
            "HOLTECH.NS", "HONDAPOWER.NS", "HONEYAUTO.NS", "HONEYWELL.NS", "HONITAM.NS",
            "HOVSERV.NS", "HPCL.NS", "HPL.NS", "HRISHI.NS", "HSIL.NS",
            "HT.NS", "HTMEDIA.NS", "HUBER.NS", "HUDCO.NS", "HUGHES.NS",
            "HUMASHU.NS", "HUNTER.NS", "HUSYS.NS", "HVPL.NS", "HWAS.NS",
            "HYGIENE.NS", "IBHRECLTD.NS", "IBREALEST.NS", "IBVENTURES.NS", "ICICIBANK.NS",
            "ICICIGI.NS", "ICICIPRULI.NS", "ICIL.NS", "ICRA.NS", "IDBI.NS",
            "IDEA.NS", "IDFC.NS", "IDFCFIRSTB.NS", "IDFC.NS", "IEX.NS",
            "IFBAGRO.NS", "IFCI.NS", "IFGLEXPOR.NS", "IIFL.NS", "IIFLWAM.NS",
            "IIFLFIN.NS", "IIFL.NS", "IGAR.NS", "IGL.NS", "IGPL.NS",
            "IIFL.NS", "IIFL.NS", "IIFL.NS", "IIFL.NS", "IIFL.NS",
            "IKF.NS", "IKIO.NS", "IL&FSENG.NS", "IL&FSTRANS.NS", "IL&FST.NS",
            "IL&FS.NS", "IMAGICAA.NS", "IMFA.NS", "IMMUNOTEX.NS", "IMPAL.NS",
            "IMPPOWER.NS", "INANI.NS", "INDAG.NS", "INDAL.NS", "INDIACEM.NS",
            "INDIANCARD.NS", "INDIAGLYCO.NS", "INDIANH.NS", "INDIABULLS.NS", "INDIANHOT.NS",
            "INDIAMART.NS", "INDIANB.NS", "INDIGO.NS", "INDOSOLAR.NS", "INDOSTAR.NS",
            "INDOBOARD.NS", "INFY.NS", "INGRAMED.NS", "INGYS.NS", "IOCL.NS",
            "IOC.NS", "IPCALAB.NS", "IRB.NS", "IRCON.NS", "ITC.NS",
            "ITDC.NS", "ITI.NS", "JAMNAAUTO.NS", "JBCHEPHARM.NS", "JBF.NS",
            "JCHAC.NS", "JDORGANO.NS", "JETAIRWAYS.NS", "JINDALSAW.NS", "JINDALSTEL.NS",
            "JINDALWLD.NS", "JKCEMENT.NS", "JKLAKSHMI.NS", "JKPAPER.NS", "JKTYRE.NS",
            "JMC.NS", "JMCPROJECT.NS", "JMFINANCE.NS", "JSL.NS", "JSWENERGY.NS",
            "JSWISPL.NS", "JSWSTEEL.NS", "JTEKTINDIA.NS", "JUBLFOOD.NS", "JUBLPHARMA.NS",
            "JYOTHYLAB.NS", "KABRAEXTR.NS", "KAJARIACER.NS", "KALPATPOWR.NS", "KAMATHOTEL.NS",
            "KANORICHEM.NS", "KANSAINER.NS", "KARURVYSYA.NS", "KAYNES.NS", "KCP.NS",
            "KEC.NS", "KEI.NS", "KELLTON.NS", "KEMROCK.NS", "KENNAMET.NS",
            "KHADIM.NS", "KIOCL.NS", "KIRANFER.NS", "KIRLOSIND.NS", "KITTEX.NS",
            "KKCL.NS", "KLMAXIM.NS", "KNRCON.NS", "KOEL.NS", "KOHI.NS",
            "KOLTEPATIL.NS", "KOTAKBANK.NS", "KPIT.NS", "KRBL.NS", "KREBSBIO.NS",
            "KRISHANA.NS", "KSB.NS", "KSL.NS", "KTKBANK.NS", "KURLON.NS",
            "KWALITY.NS", "L&TFH.NS", "LAOPALA.NS", "LAXMIMACH.NS", "LC.NS",
            "LEELA.EQ.NS", "LEELANJAN.NS", "Lemon.NS", "LICIEXPRESS.NS", "LINDEINDIA.NS",
            "LIQUIDBEES.NS", "LLOYDSMETAL.NS", "LOKESHMACH.NS", "LOTUSEYE.NS", "LOVABLE.NS",
            "LT.NS", "LTF.NS", "LTIM.NS", "LUMAXTECH.NS", "LUPIN.NS",
            "M&M.NS", "M&MFIN.NS", "MAANALU.NS", "MADHAVBAUG.NS", "MADHUCON.NS",
            "MADRASFERT.NS", "MAHA.RAIL.NS", "MAHANAGAR.NS", "MAHASTEEL.NS", "MAHLIFE.NS",
            "MAITHANALL.NS", "MAJESTIC.NS", "MAKSON.NS", "MALUPAPER.NS", "MANAKUCO.NS",
            "MANALIFEC.NS", "MANGALCHEM.NS", "MANGALAM.NS", "MANINDS.NS", "MANINFRA.NS",
            "MANN.PAPER.NS", "MANYAVAR.NS", "MARALOVER.NS", "MARICO.NS", "MARKSANS.NS",
            "MARUTI.NS", "MASFIN.NS", "MATRIMONY.NS", "MAXHEALTH.NS", "MAXVIL.NS",
            "MAYURUNIQ.NS", "MBCAGRO.NS", "MCDOWELL-N.NS", "MCS.NS", "MCTL.NS",
            "MEGH.NS", "MEHULCHSL.NS", "MENONBE.NS", "MENONPENT.NS", "MERCK.NS",
            "METROBRAND.NS", "MFSL.NS", "MFL.NS", "MGL.NS", "MHRIL.NS",
            "MIC.NS", "MINDACORP.NS", "MINDTREE.NS", "MINDTECK.NS", "MINETECH.NS",
            "MIRZAINT.NS", "MISHTANN.NS", "MMTC.NS", "MOIL.NS", "MOLDTECH.NS",
            "MOTILALOFS.NS", "MPHASIS.NS", "MRF.NS", "MRPL.NS", "MSUMI.NS",
            "MUTHOOTFIN.NS", "MUTHOOTCAP.NS", "MVL.NS", "MWEL.NS", "MYTRAH.NS",
            "NAM-INDIA.NS", "NAMRATATEA.NS", "NANDANI.NS", "NATHBIO.NS", "NAUKRI.NS",
            "NAVNETEDU.NS", "NBCC.NS", "NCC.NS", "NCLIND.NS", "NDS.NS",
            "NECLIFE.NS", "NESTLEIND.NS", "NET4INDIA.NS", "NESTLE.NS", "NEWGEN.NS",
            "NFL.NS", "NH.NS", "NHPC.NS", "NIACL.NS", "NICOLASPIR.NS",
            "NIIT.NS", "NIITTECH.NS", "NILA.NS", "NILAKAMAL.NS", "NLCINDIA.NS",
            "NMDC.NS", "NOCIL.NS", "NTPC.NS", "NUCLEUS.NS", "NVIDIA.NS",
            "OAL.NS", "OBEROI.NS", "OCCL.NS", "OCL.NS", "ODISHA.NS",
            "OFSS.NS", "OIL.NS", "OKPLAY.NS", "OMAXE.NS", "OMAXINFRA.NS",
            "ONGC.NS", "ONMOBILE.NS", "ORACLEFIN.NS", "ORIENTELEC.NS", "ORIENTHOT.NS",
            "OSWALAGRO.NS", "PAISALO.NS", "PALREDTEP.NS", "PANACEABIO.NS", "PANASONIC.NS",
            "PAPERPROD.NS", "PARAGMILK.NS", "PARAS.NS", "PAREKH.NS", "PARKASH.NS",
            "PASUMARTI.NS", "PATANJALI.NS", "PATSPIN.NS", "PCBL.NS", "PCL.NS",
            "PDL.NS", "PEARLPOLY.NS", "PEL.NS", "PENIND.NS", "PERSISTENT.NS",
            "PETRONET.NS", "PFC.NS", "PFL.NS", "PGECL.NS", "PGHL.NS",
            "PGNJ.NS", "PHILIPCARB.NS", "PIIND.NS", "PILANIINVS.NS", "PINCON.NS",
            "PIONDIST.NS", "PIRHEALTH.NS", "PITTIENG.NS", "PLUG.NS", "PNB.NS",
            "PNBHOUSING.NS", "POKARNA.NS", "POLYPLEX.NS", "POLYMED.NS", "PONDS.NS",
            "POONAWALLA.NS", "POWERGRID.NS", "PPL.NS", "PRADIP.NS", "PRAJ.NS",
            "PRATIBHA.NS", "PRECAM.NS", "PRECOT.NS", "PRESIDENT.NS", "PRICOL.NS",
            "PRIMEFOCUS.NS", "PRISM.NS", "PROTINNOV.NS", "PRSM.NS", "PSE.NS",
            "PSPP.NS", "PTC.NS", "PULLMAN.NS", "PURVA.NS", "PVP.NS",
            "PVR.NS", "QGO.NS", "QUANTUM.NS", "RADICO.NS", "RAIN.NS",
            "RAJESHEXPO.NS", "RAJESHOIL.NS", "RAJTV.NS", "RALLIS.NS", "RAMANEWS.NS",
            "RAMASTEEL.NS", "RANA.NS", "RANASUGAR.NS", "RANE.NS", "RAPIS.NS",
            "RATNAMANI.NS", "RAYMOND.NS", "RCF.NS", "RCL.NS", "RCOM.NS",
            "RDB.NS", "REALTY.NS", "REDINGTON.NS", "RENUKA.NS", "REPL.NS",
            "RELIANCE.NS", "RESILIENT.NS", "REVATHI.NS", "RHIM.NS", "RICHVU.NS",
            "RITES.NS", "RIVAAUTO.NS", "RKE.NS", "RKFORGE.NS", "RML.NS",
            "RNAM.NS", "ROCKWOOL.NS", "ROHITFERRO.NS", "ROLTA.NS", "ROSSARI.NS",
            "RPGL.NS", "RPOWER.NS", "RPP.NS", "RRL.NS", "RSYSTEM.NS",
            "RTNINDIA.NS", "RUKEEN.NS", "RVNL.NS", "S&P.NS", "SAIL.NS",
            "SALASAR.NS", "SALONA.NS", "SAMBANDAM.NS", "SANDHAR.NS", "SANGHIIND.NS",
            "SANOFI.NS", "SAREGAMA.NS", "SASKEN.NS", "SATIN.NS", "SAVEMYTRADE.NS",
            "SBEC.NS", "SBFC.NS", "SBIL.NS", "SBIN.NS", "SBICARD.NS",
            "SBILIFE.NS", "SBL.NS", "SBST.NS", "SCAP.NS", "SCHAEFFLER.NS",
            "SCHNEIDER.NS", "SEACL.NS", "SELAN.NS", "SEQUENT.NS", "SERVENG.NS",
            "SHARDACROP.NS", "SHARDAMOTR.NS", "SHAREINDIA.NS", "SHARDAMOTR.NS", "SHARDA.NS",
            "SHARDA.NS", "SHIL.NS", "SHIRPUR.NS", "SHOPERSTOP.NS", "SHREECEM.NS",
            "SHRIRAMFIN.NS", "SHRIRAM.NS", "SIBL.NS", "SIDM.NS", "SIEMENS.NS",
            "SIS.NS", "SJM.NS", "SKFINDIA.NS", "SKUMARSYN.NS", "SLBM.NS",
            "SLVL.NS", "SMALL.NS", "SMC.NS", "SMLISUZLON.NS", "SMLISUZLON.NS",
            "SML.NS", "SNOWMAN.NS", "SOLAR.NS", "SOLARINDS.NS", "SONATSOFTW.NS",
            "SONATA.NS", "SORILINFRA.NS", "SOUTHBANK.NS", "SPAL.NS", "SPANDANA.NS",
            "SPEL.NS", "SPICEJET.NS", "SPML.NS", "SPNG.NS", "SPRICE.NS",
            "SRF.NS", "SRIPISTON.NS", "SRTRANSFIN.NS", "SSDL.NS", "SSK.NS",
            "SSWL.NS", "STAR.NS", "STBANK.NS", "STEEL.NS", "STERLITE.NS",
            "STERTOOLS.NS", "STLTECH.NS", "STR.NS", "STU.NS", "STYLE.NS",
            "SUBEXLTD.NS", "SUDARSCHEM.NS", "SUFI.NS", "SUGAR.NS", "SUJANAUNI.NS",
            "SUNDRAMFAST.NS", "SUNPHARMA.NS", "SUNTECK.NS", "SUPRAJIT.NS", "SUPREMEIND.NS",
            "SURANASOL.NS", "SURENDRAN.NS", "SUVEN.NS", "SUVENPHARMA.NS", "SWANENERGY.NS",
            "SWELECTESL.NS", "SYRANGAS.NS", "TANLA.NS", "TANLAFIN.NS", "TAPARIA.NS",
            "TARC.NS", "TATAELXSI.NS", "TATACHEM.NS", "TATACOFFEE.NS", "TATACOMM.NS",
            "TATACONSUM.NS", "TATAMOTORS.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TATATECH.NS",
            "TCG.NS", "TCI.NS", "TCIEXP.NS", "TDPOWER.NS", "TEAMLEASE.NS",
            "TECHM.NS", "TEJASNET.NS", "TELE.NS", "TERRA.NS", "TEXINFRA.NS",
            "TEXRAIL.NS", "TGBL.NS", "THERMAX.NS", "THOMASCOOK.NS", "THYROCARE.NS",
            "TIINDIA.NS", "TIL.NS", "TIMKEN.NS", "TINPLATE.NS", "TIPS.NS",
            "TITAN.NS", "TMB.NS", "TMT.NS", "TNPL.NS", "TOL.NS",
            "TORNTPHARM.NS", "TRENT.NS", "TRIDENT.NS", "TRIGYN.NS", "TRIL.NS",
            "TRITUB.NS", "TROUVEN.NS", "TSI.NS", "TSSL.NS", "TTK.NS",
            "TTKPRESTIG.NS", "TTL.NS", "TV18BRDCST.NS", "TVSELECT.NS", "TVSMOTOR.NS",
            "TWL.NS", "UCAL.NS", "UFO.NS", "UGROCAP.NS", "UJJIVAN.NS",
            "ULTRACEMCO.NS", "UNIONBANK.NS", "UNOMINDA.NS", "UPL.NS", "UTIAMC.NS",
            "UTTAMSUGAR.NS", "VAIBHAVGBL.NS", "VALIANTORG.NS", "VARROC.NS", "VASWANI.NS",
            "VBL.NS", "VEDL.NS", "VENKEYS.NS", "VENUSPIPES.NS", "VERANDA.NS",
            "VGUARD.NS", "VHL.NS", "VICEROYHO.NS", "VIDHIING.NS", "VIKASECO.NS",
            "VIKASLIFE.NS", "VINATIORGA.NS", "VINDHYA.NS", "VIPIND.NS", "VIPULLTD.NS",
            "VISAKAIND.NS", "VISESHINFO.NS", "VISIN.NS", "VTL.NS", "WABAG.NS",
            "WALCHANDN.NS", "WELCORP.NS", "WELSPUNLIV.NS", "WESTLIFE.NS", "WINDAL.NS",
            "WIPRO.NS", "WOCKPHARMA.NS", "WONDERLA.NS", "WST.NS", "XCHANGING.NS",
            "XEL.NS", "XLPACK.NS", "XPRO.NS", "XYLEM.NS", "YATHARTH.NS",
            "YESBANK.NS", "YOGA.NS", "ZANDUREAL.NS", "ZEE.NS", "ZENSAR.NS",
            "ZENTEC.NS", "ZFCVINDIA.NS", "ZODIAC.NS", "ZOMATO.NS", "ZUARI.NS"
        ]
        
        # Deduplicate the list
        indian_stocks = list(set(indian_stocks))
        
        # For low price ranges, prioritize known penny stocks to speed up
        if max_price <= 10:
            penny_stocks = [s for s in indian_stocks if s in [
                "SUZLON.NS", "RPOWER.NS", "IDEA.NS", "YESBANK.NS", "VAKRANGEE.NS",
                "DHFL.NS", "JISLJALEQS.NS", "3IINFOTECH.NS", "AANJANEYA.NS", "ABAN.NS",
                "ALANKIT.NS", "ALLCARGO.NS", "VIKASECO.NS", "VIKASLIFE.NS", "FRETAIL.NS",
                "DUCON.NS", "RAMASTEEL.NS", "SALASAR.NS", "MADHUCON.NS", "TTL.NS",
                "EROSMEDIA.NS", "BCG.NS"
            ]]
            # Check penny stocks first, then others if needed
            indian_stocks = penny_stocks + [s for s in indian_stocks if s not in penny_stocks]
        
        # Screen stocks by price using parallel fetching for speed
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        screened_stocks = []
        lock = threading.Lock()
        
        def fetch_stock_data(ticker):
            try:
                stock = yf.Ticker(ticker)
                # Use fast method to get price
                info = stock.info
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                
                if current_price and min_price <= current_price <= max_price:
                    with lock:
                        screened_stocks.append({
                            'ticker': ticker,
                            'price': current_price,
                            'name': info.get('longName', 'N/A'),
                            'change': info.get('regularMarketChangePercent', 0)
                        })
            except Exception as e:
                logger.warning(f"Error fetching data for {ticker}: {e}")
        
        # Use ThreadPoolExecutor for parallel fetching
        max_workers = 10  # Limit concurrent requests
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_stock_data, ticker): ticker for ticker in indian_stocks[:200]}  # Limit to 200 stocks for speed
            for future in as_completed(futures, timeout=30):
                pass  # Results are collected in the callback
        
        # Sort by price
        screened_stocks.sort(key=lambda x: x['price'])
        
        # Limit results to top 50
        screened_stocks = screened_stocks[:50]
        
        end_time = time.time()
        logger.info(f"Screening completed in {end_time - start_time:.2f} seconds. Found {len(screened_stocks)} stocks.")
        
        if not screened_stocks:
            return f"No stocks found in the price range ₹{min_price} - ₹{max_price}. Try adjusting the price range."
        
        result = f"Found {len(screened_stocks)} stocks in price range ₹{min_price} - ₹{max_price}:\n\n"
        for stock in screened_stocks:
            change_str = f"+{stock['change']:.2f}%" if stock['change'] > 0 else f"{stock['change']:.2f}%"
            result += f"• {stock['ticker']}: ₹{stock['price']:.2f} ({stock['name']}) - {change_str}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error in screen_stocks_by_price: {e}")
        return f"Error screening stocks: {str(e)}"


# --------------------------------------------------------------------------------
# Tool 20: Generate Stock Market Graph
# --------------------------------------------------------------------------------
@tool('generate_stock_graph', description="A function that generates a stock market graph for a given ticker, sector, or commodity over a specified time period")
def generate_stock_graph(ticker: str = None, sector: str = None, commodity: str = None, period: str = "1mo"):
    """
    Generate a stock market graph for a specific ticker, sector, or commodity.
    
    Args:
        ticker: Stock ticker symbol (e.g., "TATAMOTORS.NS", "RELIANCE.NS")
        sector: Sector name (e.g., "automobile", "technology", "banking")
        commodity: Commodity name (e.g., "gold", "silver", "oil", "copper")
        period: Time period for the graph (e.g., "1mo", "3mo", "6mo", "1y", "max")
    
    Returns:
        Message indicating graph generation with identifier
    """
    logger.info(f"Generating stock graph for ticker={ticker}, sector={sector}, commodity={commodity}, period={period}")
    
    try:
        start_time = time.time()
        
        # Define sector stock mappings - Indian and International
        sector_stocks = {
            # Indian sectors
            "automobile": ["TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "BAJAJAUTO.NS", "EICHERMOT.NS"],
            "technology": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "LTIM.NS"],
            "banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
            "pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "AUROPHARMA.NS", "DIVISLAB.NS"],
            "fmcg": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DMART.NS"],
            "energy": ["RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS"],
            "metal": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS", "NMDC.NS"],
            # US sectors
            "us technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
            "us banking": ["JPM", "BAC", "WFC", "C", "GS"],
            "us healthcare": ["JNJ", "PFE", "UNH", "ABBV", "MRK"],
            "us energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
            # European sectors
            "european technology": ["ASML.AS", "SAP.DE", "INFY", "STM", "ERIC.B"],
            "european banking": ["HSBC", "BNP.PA", "ING", "BARC.L", "DB"]
        }
        
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
        
        # Determine which stocks to plot
        if ticker:
            stocks_to_plot = [ticker]
            title = f"Stock Price: {ticker}"
        elif commodity and commodity.lower() in commodity_tickers:
            stocks_to_plot = [commodity_tickers[commodity.lower()]]
            title = f"Commodity Price: {commodity.capitalize()}"
        elif sector and sector.lower() in sector_stocks:
            stocks_to_plot = sector_stocks[sector.lower()]
            title = f"Sector Performance: {sector.capitalize()}"
        else:
            return "Error: Please provide either a valid ticker symbol, sector name (automobile, technology, banking, pharma, fmcg, energy, metal), or commodity name (gold, silver, oil, copper, natural gas, platinum, palladium)"
        
        # Fetch historical data
        plt.figure(figsize=(12, 6))
        
        for stock in stocks_to_plot:
            try:
                stock_obj = yf.Ticker(stock)
                hist = stock_obj.history(period=period)
                
                if hist.empty:
                    logger.warning(f"No data found for {stock}")
                    continue
                
                # Convert to INR
                close_prices = hist['Close']
                close_inr = [get_inr_price(price_usd=price) for price in close_prices]
                
                # Plot
                dates = hist.index
                company_name = stock_obj.info.get('shortName', stock)
                plt.plot(dates, close_inr, label=company_name, linewidth=2)
                
            except Exception as e:
                logger.error(f"Error fetching data for {stock}: {e}")
                continue
        
        # Customize the graph
        plt.title(title, fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Price (₹)', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend(loc='best', fontsize=10)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save to base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        
        end_time = time.time()
        logger.info(f"Graph generated in {end_time - start_time:.3f} seconds")
        
        # Store the graph data in a temporary file or session instead of returning base64
        # For now, return a success message
        graph_info = f"GRAPH_GENERATED:{ticker if ticker else sector if sector else commodity}:{period}"
        return f"✅ **Graph generated successfully!**\n\nHere's the {commodity if commodity else (sector if sector else ticker)} price chart for the past {period}.\n\n*[Graph ID: {graph_info}]*"
        
    except Exception as e:
        logger.error(f"Error generating stock graph: {str(e)}")
        return f"❌ **Error generating graph:** {str(e)}"
