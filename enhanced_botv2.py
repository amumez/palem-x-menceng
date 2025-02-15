import time
from telegram.ext import Updater, CommandHandler
import telegram
import asyncio
from telegram.error import NetworkError
import logging
from tradingview_ta import TA_Handler, Interval
import requests
import matplotlib.pyplot as plt

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramChartAnalyzer:
    def __init__(self):
        # Replace with your bot token
        self.bot_token = '7246489444:AAHxlr_tvWm9CvrBoYZ1r0CaXOI03lroEAg'
        self.bot = telegram.Bot(token=self.bot_token)
        self.chat_id = None
        # TradingView timeframes mapping
        self.timeframes = {
            '15m': Interval.INTERVAL_15_MINUTES,
            '1h': Interval.INTERVAL_1_HOUR,
            '2h': Interval.INTERVAL_2_HOURS,
            '4h': Interval.INTERVAL_4_HOURS,
            '1d': Interval.INTERVAL_1_DAY,
            '1W': Interval.INTERVAL_1_WEEK,
        }

    async def send_telegram_message(self, message, chat_id=None):
        try:
            if chat_id:
                await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')
            elif self.chat_id:
                await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error sending telegram message: {e}")

    def get_tradingview_analysis(self, symbol, interval):
        try:
            handler = TA_Handler(
                symbol=symbol,
                exchange="BINANCE",
                screener="crypto",
                interval=interval
            )
            analysis = handler.get_analysis()
            if not analysis or not hasattr(analysis, 'summary') or not hasattr(analysis, 'indicators'):
                raise ValueError("Invalid or incomplete analysis data")
            return analysis
        except Exception as e:
            logger.error(f"Error getting TradingView analysis for {symbol}: {e}")
            return None

    def get_signal_emoji(self, signal):
        if 'STRONG_BUY' in signal:
            return '🟢 STRONG BUY'
        elif 'BUY' in signal:
            return '🟢 BUY'
        elif 'STRONG_SELL' in signal:
            return '🔴 STRONG SELL'
        elif 'SELL' in signal:
            return '🔴 SELL'
        else:
            return '⚪ NEUTRAL'

    def calculate_pivot_points(self, high, low, close):
        """
        Calculate pivot points for support and resistance.
        :param high: High price.
        :param low: Low price.
        :param close: Close price.
        :return: Dictionary containing support and resistance levels.
        """
        pp = (high + low + close) / 3
        s1 = (2 * pp) - high
        s2 = pp - (high - low)
        r1 = (2 * pp) - low
        r2 = pp + (high - low)
        return {
            "support": [round(s1, 2), round(s2, 2)],
            "resistance": [round(r1, 2), round(r2, 2)]
        }

    def get_historical_data(self, symbol, interval='1h', limit=50):
        """
        Fetch historical price data from Binance.
        :param symbol: Cryptocurrency symbol (e.g., BTCUSDT).
        :param interval: Timeframe (e.g., '1h', '4h').
        :param limit: Number of candles to fetch.
        :return: List of closing prices.
        """
        try:
            url = f"https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            response = requests.get(url, params=params)
            data = response.json()
            if not data or not isinstance(data, list):
                raise ValueError("Invalid or incomplete historical data")
            close_prices = [float(candle[4]) for candle in data]
            return close_prices
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return []

    def calculate_rsi(self, prices, period=14):
        """
        Calculate the Relative Strength Index (RSI).
        :param prices: List of closing prices.
        :param period: RSI period (default is 14).
        :return: List of RSI values.
        """
        if len(prices) < period:
            raise ValueError("Not enough data to calculate RSI")
        deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        rs_values = [avg_gain / avg_loss if avg_loss != 0 else 0]
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / avg_loss if avg_loss != 0 else 0
            rs_values.append(rs)

        rsi_values = [100 - (100 / (1 + rs)) for rs in rs_values]
        return rsi_values

    def plot_rsi(self, rsi_values, symbol):
        """
        Generate an RSI chart and save it as an image.
        :param rsi_values: List of RSI values.
        :param symbol: Cryptocurrency symbol (e.g., BTCUSDT).
        """
        plt.figure(figsize=(8, 4))
        plt.plot(rsi_values, label="RSI", color="blue")
        plt.axhline(70, color="red", linestyle="--", label="Overbought")
        plt.axhline(30, color="green", linestyle="--", label="Oversold")
        plt.title(f"RSI Chart for {symbol}")
        plt.xlabel("Time")
        plt.ylabel("RSI Value")
        plt.legend()
        plt.grid(True)
        # Save the chart as an image
        plt.savefig(f"{symbol}_rsi_chart.png")
        plt.close()

    async def perform_analysis(self, symbol, chat_id=None):
        try:
            # Fetch historical data
            close_prices = self.get_historical_data(symbol, interval='1h', limit=50)
            if not close_prices:
                await self.send_telegram_message(f"❌ Could not fetch historical data for {symbol}", chat_id)
                return
            
            # Calculate RSI
            rsi_values = self.calculate_rsi(close_prices, period=14)
            
            # Generate and save RSI chart
            self.plot_rsi(rsi_values, symbol)
            
            # Create analysis message
            latest_rsi = rsi_values[-1]
            message = f"📊 Analysis for {symbol}\n\n"
            message += f"📈 Latest RSI Value: {latest_rsi:.2f}\n"
            if latest_rsi > 70:
                message += "Status: 🔴 Overbought (Potential reversal to the downside)\n"
            elif latest_rsi < 30:
                message += "Status: 🟢 Oversold (Potential reversal to the upside)\n"
            else:
                message += "Status: ⚪ Neutral\n"
            
            # Send the message
            await self.send_telegram_message(message, chat_id)
            
            # Send the RSI chart
            with open(f"{symbol}_rsi_chart.png", "rb") as photo:
                await self.bot.send_photo(chat_id=chat_id, photo=photo)
        except Exception as e:
            logger.error(f"Error in analysis: {e}")
            await self.send_telegram_message(f"Error in analysis: {str(e)}", chat_id)

    async def generate_trading_signal(self, symbol, chat_id=None):
        try:
            await self.send_telegram_message("🔄 Analyzing multiple timeframes, please wait...", chat_id)
            # Check multiple timeframes for confirmation
            analysis_15m = self.get_tradingview_analysis(symbol, Interval.INTERVAL_15_MINUTES)
            analysis_1h = self.get_tradingview_analysis(symbol, Interval.INTERVAL_1_HOUR)
            analysis_4h = self.get_tradingview_analysis(symbol, Interval.INTERVAL_4_HOURS)
            analysis_1d = self.get_tradingview_analysis(symbol, Interval.INTERVAL_1_DAY)

            if analysis_15m and analysis_1h and analysis_4h and analysis_1d:
                # Get signals from different timeframes
                signal_15m = analysis_15m.summary['RECOMMENDATION']
                signal_1h = analysis_1h.summary['RECOMMENDATION']
                signal_4h = analysis_4h.summary['RECOMMENDATION']
                signal_1d = analysis_1d.summary['RECOMMENDATION']

                # Determine trend strength
                short_term_bullish = all(x in ['STRONG_BUY', 'BUY'] for x in [signal_15m, signal_1h])
                long_term_bullish = all(x in ['STRONG_BUY', 'BUY'] for x in [signal_4h, signal_1d])
                short_term_bearish = all(x in ['STRONG_SELL', 'SELL'] for x in [signal_15m, signal_1h])
                long_term_bearish = all(x in ['STRONG_SELL', 'SELL'] for x in [signal_4h, signal_1d])

                # Determine direction and strategy
                if short_term_bullish and not long_term_bullish:
                    strategy = "SCALP"
                    direction = "LONG"
                    confidence = "HIGH"
                elif long_term_bullish:
                    strategy = "SWING"
                    direction = "LONG"
                    confidence = "HIGH"
                elif short_term_bearish and not long_term_bearish:
                    strategy = "SCALP"
                    direction = "SHORT"
                    confidence = "HIGH"
                elif long_term_bearish:
                    strategy = "SWING"
                    direction = "SHORT"
                    confidence = "HIGH"
                else:
                    strategy = "NONE"
                    direction = "NONE"
                    confidence = "LOW"

                # Calculate entry, targets, and stop loss using 1H timeframe
                current_price = float(analysis_1h.indicators['close'])
                atr = current_price * 0.01  # Using 1% as a tighter ATR
                if direction == "LONG":
                    entry = current_price
                    entry_range_low = entry - atr
                    entry_range_high = entry + atr
                    stop_loss = entry * 0.98  # 2% below entry
                    target1 = entry * 1.02    # 2% above entry
                    target2 = entry * 1.04    # 4% above entry
                    target3 = entry * 1.06    # 6% above entry
                elif direction == "SHORT":
                    entry = current_price
                    entry_range_low = entry - atr
                    entry_range_high = entry + atr
                    stop_loss = entry * 1.02  # 2% above entry
                    target1 = entry * 0.98    # 2% below entry
                    target2 = entry * 0.96    # 4% below entry
                    target3 = entry * 0.94    # 6% below entry
                else:
                    entry = stop_loss = target1 = target2 = target3 = current_price
                    entry_range_low = entry_range_high = current_price

                # Get support and resistance levels using 4H timeframe
                analysis_4h = self.get_tradingview_analysis(symbol, Interval.INTERVAL_4_HOURS)
                if analysis_4h:
                    high = float(analysis_4h.indicators['high'])
                    low = float(analysis_4h.indicators['low'])
                    close = float(analysis_4h.indicators['close'])
                    pivot_levels = self.calculate_pivot_points(high, low, close)
                    support = pivot_levels['support']
                    resistance = pivot_levels['resistance']
                else:
                    support = ["N/A", "N/A"]
                    resistance = ["N/A", "N/A"]

                # Create detailed message
                message = f"🎯 SIGNAL ALERT: {symbol}\n"
                message += "─" * 25 + "\n\n"
                message += f"Strategy: {strategy}\n"
                message += f"Direction: {'🟢' if direction == 'LONG' else '🔴' if direction == 'SHORT' else '⚪'} {direction}\n"
                message += f"Confidence: {confidence}\n\n"
                message += f"💠 ENTRY: {entry:.2f} (Range: {int(entry_range_low)} - {int(entry_range_high)})\n"
                message += "🎯 TARGETS:\n"
                message += f"1️⃣ {target1:.2f}\n"
                message += f"2️⃣ {target2:.2f}\n"
                message += f"3️⃣ {target3:.2f}\n\n"
                message += f"🛑 STOP LOSS: {stop_loss:.2f}\n"
                message += f"📉 Support: {support[0]} (S1), {support[1]} (S2)\n"
                message += f"📈 Resistance: {resistance[0]} (R1), {resistance[1]} (R2)\n"

                # Add timeframe analysis
                message += "\n📊 Timeframe Analysis:\n"
                message += f"15m: {self.get_signal_emoji(signal_15m)}\n"
                message += f"1h:  {self.get_signal_emoji(signal_1h)}\n"
                message += f"4h:  {self.get_signal_emoji(signal_4h)}\n"
                message += f"1d:  {self.get_signal_emoji(signal_1d)}\n"

                # Add risk management tips
                message += "\n⚠️ Risk Management:\n"
                message += "• Use proper position sizing\n"
                message += "• Don't risk more than 1-2% per trade\n"
                message += "• Always use stop loss\n"

                await self.send_telegram_message(message, chat_id)
            else:
                await self.send_telegram_message(f"❌ Could not get complete analysis for {symbol}", chat_id)
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            await self.send_telegram_message(f"Error generating signal: {str(e)}", chat_id)

    async def analyze_coin_for_hot_signal(self, symbol):
        try:
            analysis_data = {}
            total_score = 0
            # Use only these timeframes for hot signal analysis
            hot_signal_timeframes = {
                '15m': Interval.INTERVAL_15_MINUTES,
                '1h': Interval.INTERVAL_1_HOUR,
                '4h': Interval.INTERVAL_4_HOURS
            }
            for tf_name, tf_value in hot_signal_timeframes.items():
                analysis = self.get_tradingview_analysis(symbol, tf_value)
                if analysis:
                    # Store recommendation
                    analysis_data[tf_name] = analysis.summary['RECOMMENDATION']
                    # Calculate score
                    buy_signals = analysis.summary['BUY']
                    sell_signals = analysis.summary['SELL']
                    score = buy_signals - sell_signals
                    total_score += score
                    # Add small delay to avoid rate limiting
                    await asyncio.sleep(0.5)
            if not analysis_data:
                return None

            # Calculate signal strength and direction
            avg_score = total_score / len(analysis_data)
            bullish_count = sum(1 for x in analysis_data.values() if x in ['STRONG_BUY', 'BUY'])
            bearish_count = sum(1 for x in analysis_data.values() if x in ['STRONG_SELL', 'SELL'])

            # Determine confidence
            if abs(avg_score) >= 2 and (bullish_count >= 2 or bearish_count >= 2):
                confidence = "HIGH"
            elif abs(avg_score) >= 1:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            # Determine direction
            direction = "LONG" if avg_score > 0 else "SHORT"
            return {
                'symbol': symbol,
                'direction': direction,
                'confidence': confidence,
                'score': abs(avg_score),
                'timeframes': analysis_data
            }
        except Exception as e:
            logger.error(f"Error in analyze_coin_for_hot_signal for {symbol}: {e}")
            return None

    async def get_top_coins(self):
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 50,
                "page": 1
            }
            response = requests.get(url, params=params)
            data = response.json()
            if not data or not isinstance(data, list):
                raise ValueError("Invalid or incomplete data from CoinGecko")
            return [f"{coin['symbol'].upper()}USDT" for coin in data]
        except Exception as e:
            logger.error(f"Error fetching top coins: {e}")
            return []

    async def handle_hot_signal_command(self, chat_id):
        try:
            await self.send_telegram_message("🔍 Scanning top cryptocurrencies for potential signals...", chat_id)
            # Get top coins
            symbols = await self.get_top_coins()
            # Limit the number of coins to analyze for performance
            symbols = symbols[:10]  # Analyze only the top 10 coins
            # Analyze each coin
            hot_signals = []
            for symbol in symbols:
                try:
                    analysis = await self.analyze_coin_for_hot_signal(symbol)
                    if analysis and analysis['confidence'] in ['HIGH', 'MEDIUM']:
                        hot_signals.append(analysis)
                except Exception as e:
                    logger.error(f"Error analyzing {symbol}: {e}")
                    continue

            # Sort by confidence and score
            sorted_signals = sorted(
                hot_signals,
                key=lambda x: (
                    {'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}[x['confidence']],
                    x['score']
                ),
                reverse=True
            )[:3]  # Get top 3 signals

            if not sorted_signals:
                await self.send_telegram_message("No significant signals found, but here are some potential opportunities:", chat_id)

            # Prepare a single message
            message = "🔥 POTENTIAL SIGNALS FOUND!\n" + "─" * 25 + "\n"
            for i, signal in enumerate(sorted_signals, 1):
                message += f"Signal #{i}:\n"
                message += f"🎯 {signal['symbol']}\n"
                message += "─" * 25 + "\n"
                message += f"Direction: {'🟢' if signal['direction'] == 'LONG' else '🔴'} {signal['direction']}\n"
                message += f"Confidence: {signal['confidence']}\n"
                message += f"Signal Strength: {signal['score']:.2f}\n\n"
                message += "📊 Timeframe Analysis:\n"
                for tf, recommendation in signal['timeframes'].items():
                    emoji = '🟢' if 'BUY' in recommendation else '🔴' if 'SELL' in recommendation else '⚪'
                    message += f"{tf}: {emoji} {recommendation}\n"
                message += "\n"

            # Add footer
            message += "⚠️ Risk Management Tips:\n"
            message += "• Always use stop loss\n"
            message += "• Don't risk more than 1-2% per trade\n"
            message += "• Confirm signals with your own analysis\n"

            # Send the consolidated message
            await self.send_telegram_message(message, chat_id)
        except Exception as e:
            logger.error(f"Error processing hot signals: {e}")
            await self.send_telegram_message(f"Error processing hot signals: {str(e)}", chat_id)

    def handle_command(self, update, context):
        try:
            self.chat_id = update.message.chat_id
            command = update.message.text.split()
            if command[0] == '/start':
                update.message.reply_text(
                    "Welcome to TradingView Chart Analyzer Bot! 📊\n\n"
                    "Available commands:\n"
                    "├ /analyze BTCUSDT - Market sentiment analysis\n"
                    "├ /signal BTCUSDT - Trading signal\n"
                    "├ /hotsignal - Find best trading opportunities\n\n"
                    "Example: /signal BTCUSDT"
                )
            elif command[0] == '/analyze':
                if len(command) > 1:
                    asyncio.run(self.perform_analysis(command[1], self.chat_id))
                else:
                    update.message.reply_text("Please provide a symbol. Example: /analyze BTCUSDT")
            elif command[0] == '/signal':
                if len(command) > 1:
                    asyncio.run(self.generate_trading_signal(command[1], self.chat_id))
                else:
                    update.message.reply_text("Please provide a symbol. Example: /signal BTCUSDT")
            elif command[0] == '/hotsignal':
                asyncio.run(self.handle_hot_signal_command(self.chat_id))
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            update.message.reply_text(f"Error processing command: {str(e)}")

    def run_bot(self):
        updater = Updater(self.bot_token, use_context=True)
        dp = updater.dispatcher
        # Add command handlers
        dp.add_handler(CommandHandler("start", self.handle_command))
        dp.add_handler(CommandHandler("analyze", self.handle_command))
        dp.add_handler(CommandHandler("signal", self.handle_command))
        dp.add_handler(CommandHandler("hotsignal", self.handle_command))
        # Start the bot
        updater.start_polling()
        print("Bot is running... Press Ctrl+C to stop")
        updater.idle()

if __name__ == "__main__":
    analyzer = TelegramChartAnalyzer()
    analyzer.run_bot()