"""
skills.py — Deterministic data-fetching tools for the Argus agent.

All skills use yfinance (free, no API key needed) to pull real financial data
from Yahoo Finance. They are registered as @app.skill decorators so AgentField
exposes them as REST endpoints AND the Reasoners can call them directly.

Skills intentionally return plain JSON-serialisable dicts/lists so the LLM
can reason over them without needing to understand yfinance objects.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf

from src import app


def _df_to_records(df) -> dict:
    """Convert a pandas DataFrame (yfinance financials) to a clean dict."""
    if df is None or df.empty:
        return {}
    # Transpose so rows = metrics, cols = dates; convert to string keys
    try:
        df = df.fillna(0)
        return {
            str(col.date()): df[col].to_dict() for col in df.columns
        }
    except Exception:
        return df.to_dict()


@app.skill()
async def validate_ticker(ticker: str) -> dict:
    """
    Check whether a ticker is actively tradable on a major exchange.

    Returns a dict with:
      - valid (bool): True if the ticker has live market data
      - reason (str): human-readable explanation if invalid
      - current_price (float | None): last known price
      - quote_type (str): EQUITY / ETF / CRYPTOCURRENCY / MUTUALFUND / etc.
      - exchange (str): exchange name
    """
    app.note(f"[skill] Validating ticker: {ticker}")

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        try:
            info = t.info or {}
        except Exception as exc:
            return {
                "valid": False,
                "reason": f"yfinance raised an error: {exc}",
                "current_price": None,
                "quote_type": None,
                "exchange": None,
            }

        if not info:
            return {
                "valid": False,
                "reason": (
                    f"No data returned for '{ticker}'. "
                    "It may be delisted, never listed, private, or misspelled."
                ),
                "current_price": None,
                "quote_type": None,
                "exchange": None,
            }

        price = info.get("regularMarketPrice") or info.get("currentPrice")
        quote_type = info.get("quoteType", "UNKNOWN")
        exchange = info.get("exchange") or info.get("fullExchangeName", "")

        if not price:
            try:
                fi = t.fast_info
                price = fi.get("lastPrice") if hasattr(fi, "get") else getattr(fi, "last_price", None)
            except Exception:
                pass

        if not price:
            try:
                hist = t.history(period="5d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        if not price:
            name = info.get("longName") or info.get("shortName") or ticker
            return {
                "valid": False,
                "reason": (
                    f"'{ticker}' ({name}) has no live market price. "
                    "It is likely delisted, suspended, or no longer trading."
                ),
                "current_price": None,
                "quote_type": quote_type,
                "exchange": exchange,
            }

        return {
            "valid": True,
            "reason": "OK",
            "current_price": price,
            "quote_type": quote_type,
            "exchange": exchange,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


@app.skill()
async def get_income_statement(ticker: str, period: str = "annual") -> dict:
    """
    Fetch income statement data for a ticker using yfinance.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        period: 'annual' or 'quarterly'.

    Returns:
        Dict mapping date → {metric: value} for revenue, net income, EBITDA, etc.
    """
    app.note(f"[skill] Fetching income statement: {ticker} ({period})")

    def _fetch():
        t = yf.Ticker(ticker)
        df = t.income_stmt if period == "annual" else t.quarterly_income_stmt
        return _df_to_records(df)

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def get_balance_sheet(ticker: str, period: str = "annual") -> dict:
    """
    Fetch balance sheet data for a ticker.

    Args:
        ticker: Stock ticker symbol.
        period: 'annual' or 'quarterly'.

    Returns:
        Dict mapping date → {metric: value} for assets, liabilities, equity, etc.
    """
    app.note(f"[skill] Fetching balance sheet: {ticker} ({period})")

    def _fetch():
        t = yf.Ticker(ticker)
        df = t.balance_sheet if period == "annual" else t.quarterly_balance_sheet
        return _df_to_records(df)

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def get_cash_flow_statement(ticker: str, period: str = "annual") -> dict:
    """
    Fetch cash flow statement for a ticker.

    Args:
        ticker: Stock ticker symbol.
        period: 'annual' or 'quarterly'.

    Returns:
        Dict mapping date → {metric: value} for operating/investing/financing CF.
    """
    app.note(f"[skill] Fetching cash flow: {ticker} ({period})")

    def _fetch():
        t = yf.Ticker(ticker)
        df = t.cashflow if period == "annual" else t.quarterly_cashflow
        return _df_to_records(df)

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def search_market_news(ticker: str, limit: int = 10) -> list[dict]:
    """
    Fetch recent news articles for a ticker via yfinance.

    Args:
        ticker: Stock ticker symbol.
        limit: Max number of articles to return (default 10).

    Returns:
        List of dicts with keys: title, publisher, link, providerPublishTime, type.
    """
    app.note(f"[skill] Fetching news: {ticker} (limit={limit})")

    def _fetch():
        t = yf.Ticker(ticker)
        news = t.news or []
        clean = []
        for article in news[:limit]:
            clean.append({
                "title": article.get("title", ""),
                "publisher": article.get("publisher", ""),
                "link": article.get("link", ""),
                "published_at": article.get("providerPublishTime", 0),
                "type": article.get("type", ""),
                "summary": article.get("summary", ""),
            })
        return clean

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def get_company_facts(ticker: str) -> dict:
    """
    Fetch key company facts and fundamentals for a ticker.

    Includes: sector, industry, market cap, P/E ratio, EPS, dividend yield,
    52-week range, description, and analyst recommendations.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Dict of fundamental metrics.
    """
    app.note(f"[skill] Fetching company facts: {ticker}")

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        info = t.info or {}
        # Extract the most useful fields for financial analysis
        fields = [
            "shortName", "longName", "sector", "industry",
            "country", "website", "longBusinessSummary",
            "marketCap", "enterpriseValue",
            "trailingPE", "forwardPE", "priceToBook", "priceToSalesTrailing12Months",
            "trailingEps", "forwardEps",
            "revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins", "profitMargins",
            "totalRevenue", "ebitda", "totalDebt", "totalCash",
            "currentRatio", "debtToEquity",
            "dividendYield", "payoutRatio",
            "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice",
            "recommendationMean", "recommendationKey", "numberOfAnalystOpinions",
            "beta", "sharesOutstanding", "floatShares",
        ]
        return {k: info.get(k) for k in fields if info.get(k) is not None}

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def get_analyst_targets(ticker: str) -> dict:
    """
    Fetch sell-side analyst price targets and recommendation consensus.

    Returns:
        Dict with current price, mean/low/high targets, upside %, and
        recommendation distribution (strongBuy/buy/hold/sell/strongSell counts).
    """
    app.note(f"[skill] Fetching analyst targets: {ticker}")

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        info = t.info or {}

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        mean_target   = info.get("targetMeanPrice")
        low_target    = info.get("targetLowPrice")
        high_target   = info.get("targetHighPrice")

        upside = None
        if current_price and mean_target:
            upside = round((mean_target - current_price) / current_price * 100, 1)

        # Recommendation trend (last period)
        rec_trend = {}
        try:
            trend_df = t.recommendations_summary
            if trend_df is not None and not trend_df.empty:
                latest = trend_df.iloc[0]
                rec_trend = {
                    "strongBuy":  int(latest.get("strongBuy",  0)),
                    "buy":        int(latest.get("buy",        0)),
                    "hold":       int(latest.get("hold",       0)),
                    "sell":       int(latest.get("sell",       0)),
                    "strongSell": int(latest.get("strongSell", 0)),
                }
        except Exception:
            pass

        return {
            "current_price":          current_price,
            "target_mean":            mean_target,
            "target_low":             low_target,
            "target_high":            high_target,
            "implied_upside_percent": upside,
            "analyst_count":          info.get("numberOfAnalystOpinions"),
            "consensus_rating":       info.get("recommendationKey"),
            "consensus_score":        info.get("recommendationMean"),  # 1=strong buy, 5=strong sell
            "recommendation_breakdown": rec_trend,
        }

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def get_insider_transactions(ticker: str, limit: int = 10) -> list[dict]:
    """
    Fetch recent insider buy/sell transactions for a ticker.

    Insider buying is a bullish signal; heavy insider selling is bearish.

    Args:
        ticker: Stock ticker symbol.
        limit:  Max number of transactions to return.

    Returns:
        List of dicts with insider name, title, transaction type, shares, and value.
    """
    app.note(f"[skill] Fetching insider transactions: {ticker}")

    def _fetch() -> list:
        t = yf.Ticker(ticker)
        try:
            df = t.insider_transactions
            if df is None or df.empty:
                return []
            records = []
            for _, row in df.head(limit).iterrows():
                records.append({
                    "insider":      str(row.get("Insider", "")),
                    "title":        str(row.get("Position", "")),
                    "transaction":  str(row.get("Transaction", "")),
                    "shares":       int(row.get("Shares", 0) or 0),
                    "value_usd":    float(row.get("Value", 0) or 0),
                    "date":         str(row.get("Start Date", row.get("Date", ""))),
                })
            return records
        except Exception:
            return []

    result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return result


@app.skill()
async def get_technical_indicators(ticker: str, period: str = "6mo") -> dict:
    """
    Compute technical indicators: SMA (20, 50, 200), EMA (9, 21),
    RSI (14), MACD, Bollinger Bands, ATR, and volume analysis.
    """
    app.note(f"[skill] Computing technical indicators: {ticker} ({period})")

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        df = t.history(period=period)
        if df is None or df.empty:
            return {"error": f"No price history for {ticker}"}

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        current = float(close.iloc[-1])

        sma_20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
        sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        ema_9 = float(close.ewm(span=9).mean().iloc[-1])
        ema_21 = float(close.ewm(span=21).mean().iloc[-1])

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if len(rsi_series) >= 14 else None

        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9).mean()
        macd_hist = macd_line - signal_line

        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std

        tr = (high - low).combine_first(
            (high - close.shift(1)).abs()
        ).combine_first((low - close.shift(1)).abs())
        atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else None

        avg_vol_20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else None
        current_vol = float(volume.iloc[-1])
        vol_ratio = round(current_vol / avg_vol_20, 2) if avg_vol_20 else None

        recent_high = float(high.tail(20).max())
        recent_low = float(low.tail(20).min())

        signals = []
        if sma_50 and sma_200:
            if sma_50 > sma_200:
                signals.append("Golden Cross (SMA50 > SMA200) — bullish")
            else:
                signals.append("Death Cross (SMA50 < SMA200) — bearish")
        if rsi:
            if rsi > 70:
                signals.append(f"RSI overbought ({rsi:.1f})")
            elif rsi < 30:
                signals.append(f"RSI oversold ({rsi:.1f})")
        if len(macd_hist) > 1:
            if float(macd_hist.iloc[-1]) > 0 and float(macd_hist.iloc[-2]) <= 0:
                signals.append("MACD bullish crossover")
            elif float(macd_hist.iloc[-1]) < 0 and float(macd_hist.iloc[-2]) >= 0:
                signals.append("MACD bearish crossover")
        if bb_upper.iloc[-1] and current > float(bb_upper.iloc[-1]):
            signals.append("Price above upper Bollinger Band — overbought")
        elif bb_lower.iloc[-1] and current < float(bb_lower.iloc[-1]):
            signals.append("Price below lower Bollinger Band — oversold")

        return {
            "current_price": round(current, 2),
            "sma_20": round(sma_20, 2) if sma_20 else None,
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "sma_200": round(sma_200, 2) if sma_200 else None,
            "ema_9": round(ema_9, 2),
            "ema_21": round(ema_21, 2),
            "rsi_14": round(rsi, 2) if rsi else None,
            "macd": round(float(macd_line.iloc[-1]), 4),
            "macd_signal": round(float(signal_line.iloc[-1]), 4),
            "macd_histogram": round(float(macd_hist.iloc[-1]), 4),
            "bollinger_upper": round(float(bb_upper.iloc[-1]), 2) if bb_upper.iloc[-1] else None,
            "bollinger_mid": round(float(bb_mid.iloc[-1]), 2) if bb_mid.iloc[-1] else None,
            "bollinger_lower": round(float(bb_lower.iloc[-1]), 2) if bb_lower.iloc[-1] else None,
            "atr_14": round(atr, 2) if atr else None,
            "volume_current": int(current_vol),
            "volume_avg_20": int(avg_vol_20) if avg_vol_20 else None,
            "volume_ratio": vol_ratio,
            "support_20d": round(recent_low, 2),
            "resistance_20d": round(recent_high, 2),
            "trend_signals": signals,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


@app.skill()
async def get_options_chain(ticker: str, weeks_out: int = 6) -> dict:
    """
    Fetch options chain data: expirations, ATM calls/puts, IV, volume,
    open interest, and put/call ratios for near-term expirations.
    """
    app.note(f"[skill] Fetching options chain: {ticker} (within {weeks_out} weeks)")

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        info = t.info or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        try:
            expirations = list(t.options)
        except Exception:
            return {"error": f"No options data for {ticker}", "expirations": []}

        if not expirations:
            return {"error": f"No options expirations for {ticker}", "expirations": []}

        cutoff = datetime.now() + timedelta(weeks=weeks_out)
        near_exps = [e for e in expirations if datetime.strptime(e, "%Y-%m-%d") <= cutoff]
        if not near_exps:
            near_exps = expirations[:2]

        chains = []
        for exp in near_exps[:3]:
            try:
                opt = t.option_chain(exp)
            except Exception:
                continue

            def _safe_int(val):
                import math
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    return 0
                return int(val)

            def _safe_float(val, default=0.0):
                import math
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    return default
                return float(val)

            def _parse_chain(df, side):
                if df is None or df.empty:
                    return []
                records = []
                for _, row in df.iterrows():
                    records.append({
                        "strike": _safe_float(row.get("strike")),
                        "lastPrice": _safe_float(row.get("lastPrice")),
                        "bid": _safe_float(row.get("bid")),
                        "ask": _safe_float(row.get("ask")),
                        "volume": _safe_int(row.get("volume")),
                        "openInterest": _safe_int(row.get("openInterest")),
                        "impliedVolatility": round(_safe_float(row.get("impliedVolatility")), 4),
                        "inTheMoney": bool(row.get("inTheMoney", False)),
                        "side": side,
                    })
                return records

            calls = _parse_chain(opt.calls, "call")
            puts = _parse_chain(opt.puts, "put")

            atm_calls = [c for c in calls if abs(c["strike"] - (current_price or 0)) / max(current_price or 1, 1) < 0.05]
            atm_puts = [p for p in puts if abs(p["strike"] - (current_price or 0)) / max(current_price or 1, 1) < 0.05]

            chains.append({
                "expiration": exp,
                "days_to_expiry": (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days,
                "total_calls": len(calls),
                "total_puts": len(puts),
                "put_call_ratio": round(
                    sum(p["openInterest"] for p in puts) /
                    max(sum(c["openInterest"] for c in calls), 1), 2
                ),
                "atm_calls": atm_calls[:5],
                "atm_puts": atm_puts[:5],
                "highest_oi_calls": sorted(calls, key=lambda x: x["openInterest"], reverse=True)[:5],
                "highest_oi_puts": sorted(puts, key=lambda x: x["openInterest"], reverse=True)[:5],
                "avg_call_iv": round(
                    sum(c["impliedVolatility"] for c in atm_calls) / max(len(atm_calls), 1), 4
                ) if atm_calls else None,
                "avg_put_iv": round(
                    sum(p["impliedVolatility"] for p in atm_puts) / max(len(atm_puts), 1), 4
                ) if atm_puts else None,
            })

        return {
            "ticker": ticker,
            "current_price": current_price,
            "all_expirations": expirations,
            "near_term_chains": chains,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


@app.skill()
async def get_fundamental_deep_dive(ticker: str) -> dict:
    """
    Deep fundamental analysis: moat indicators, R&D intensity,
    catalyst pipeline, and floor-to-ceiling valuation framework.
    """
    app.note(f"[skill] Deep fundamental analysis: {ticker}")

    def _fetch() -> dict:
        t = yf.Ticker(ticker)
        info = t.info or {}
        inc = t.income_stmt
        cf = t.cashflow

        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        market_cap = info.get("marketCap") or 0

        gross_margin = info.get("grossMargins")
        op_margin = info.get("operatingMargins")
        roe = info.get("returnOnEquity")
        revenue_growth = info.get("revenueGrowth")
        earnings_growth = info.get("earningsGrowth")

        moat_signals = []
        if gross_margin and gross_margin > 0.40:
            moat_signals.append(f"High gross margin ({gross_margin:.1%}) — pricing power")
        if op_margin and op_margin > 0.20:
            moat_signals.append(f"Strong operating margin ({op_margin:.1%}) — cost advantage")
        if roe and roe > 0.20:
            moat_signals.append(f"High ROE ({roe:.1%}) — capital efficiency")
        if info.get("debtToEquity") and info["debtToEquity"] < 50:
            moat_signals.append(f"Low D/E ({info['debtToEquity']:.1f}) — financial fortress")

        rd_ratio = None
        total_revenue = info.get("totalRevenue")
        if inc is not None and not inc.empty:
            for col in inc.columns[:1]:
                rd_val = inc[col].get("Research And Development") or inc[col].get("ResearchAndDevelopment")
                if rd_val and total_revenue:
                    rd_ratio = round(float(rd_val) / total_revenue, 4)

        fcf = None
        fcf_yield = None
        if cf is not None and not cf.empty:
            for col in cf.columns[:1]:
                op_cf = cf[col].get("Operating Cash Flow") or cf[col].get("Total Cash From Operating Activities") or 0
                capex = abs(cf[col].get("Capital Expenditure") or cf[col].get("Capital Expenditures") or 0)
                fcf = float(op_cf) - float(capex)
                if market_cap > 0:
                    fcf_yield = round(fcf / market_cap, 4)

        book_value_ps = info.get("bookValue")
        floor_price = book_value_ps

        ceiling_price = None
        forward_pe = info.get("forwardPE")
        forward_eps = info.get("forwardEps")
        if forward_pe and forward_eps and revenue_growth:
            growth_premium = max(1.0, 1.0 + revenue_growth)
            ceiling_price = round(forward_eps * forward_pe * growth_premium, 2)

        catalysts = []
        if revenue_growth and revenue_growth > 0.15:
            catalysts.append(f"Revenue accelerating ({revenue_growth:.1%} YoY)")
        if earnings_growth and earnings_growth > 0.20:
            catalysts.append(f"Earnings growth strong ({earnings_growth:.1%})")
        if rd_ratio and rd_ratio > 0.10:
            catalysts.append(f"Heavy R&D investment ({rd_ratio:.1%} of revenue) — innovation pipeline")
        mean_target = info.get("targetMeanPrice")
        if mean_target and current_price:
            target_upside = round((mean_target - current_price) / current_price * 100, 1)
            if target_upside > 15:
                catalysts.append(f"Analyst consensus target {target_upside:.0f}% upside")

        return {
            "ticker": ticker,
            "current_price": current_price,
            "market_cap": market_cap,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "moat_signals": moat_signals,
            "moat_strength": "strong" if len(moat_signals) >= 3 else "moderate" if len(moat_signals) >= 1 else "weak",
            "gross_margin": gross_margin,
            "operating_margin": op_margin,
            "roe": roe,
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            "rd_to_revenue_ratio": rd_ratio,
            "free_cash_flow": fcf,
            "fcf_yield": fcf_yield,
            "floor_price_book_value": floor_price,
            "ceiling_price_growth": ceiling_price,
            "upside_to_ceiling_pct": round((ceiling_price - current_price) / current_price * 100, 1) if ceiling_price and current_price else None,
            "downside_to_floor_pct": round((floor_price - current_price) / current_price * 100, 1) if floor_price and current_price else None,
            "forward_pe": forward_pe,
            "trailing_pe": info.get("trailingPE"),
            "price_to_book": info.get("priceToBook"),
            "debt_to_equity": info.get("debtToEquity"),
            "catalysts": catalysts,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _fetch)
