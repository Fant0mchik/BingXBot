import time
from collections import deque
import logging

# Налаштування логування для тесту (щоб бачити виводи)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

# Мок функції notify (щоб симулювати сповіщення без реального надсилання)
def mock_notify(event, details):
    print(f"NOTIFY CALLED: Event={event}, Details={details}")

# Мок функції get_funding_rate (для контролю funding rate в тестах)
def mock_get_funding_rate(symbol):
    # За замовчуванням повертаємо None, але в тестах можемо перевизначити
    return None

# Копіюємо клас MarketAnalyzer з test.py (з деякими модифікаціями для тесту)
class MarketAnalyzer:
    def __init__(self, symbol):
        self.symbol = symbol
        self.prices = deque(maxlen=300)
        self.volumes = deque(maxlen=300)
        self.times = deque(maxlen=300)

        self.candles = None
        self.orderbook = None
        self.last_peak = None
        self.last_peak_time = None

    def update_price(self, price, custom_time=None):
        self.prices.append(price)
        if custom_time is None:
            self.times.append(time.time())
        else:
            self.times.append(custom_time)  # Для тесту дозволяємо задавати фіксований час
        self.detect_events()

    def update_volume(self, volume):
        self.volumes.append(volume)

    def detect_events(self):
        if len(self.prices) < 20:
            return

        start = self.prices[0]
        cur = self.prices[-1]
        delta = (cur - start) / start * 100
        duration = self.times[-1] - self.times[0]
        speed = abs(delta) / duration if duration else 0

        if -30 <= delta <= -10:
            logging.warning("Dump detected")
            mock_notify("DUMP", self.details(cur))
            self.reset()
            return  # Додано return, щоб уникнути продовження після reset

        if delta >= 5 and speed > 0.02:
            logging.warning("Pump detected")
            mock_notify("PUMP", self.details(cur))
            self.reset()
            return  # Додано return, щоб уникнути продовження після reset

        if 8 <= delta <= 30 and speed > 0.03:
            self.last_peak = cur
            self.last_peak_time = self.times[-1]  # Використовуємо останній час

        if self.last_peak and self.times[-1] - self.last_peak_time >= 15:
            funding = mock_get_funding_rate(self.symbol)
            vwap = sum(self.prices) / len(self.prices)

            if funding and funding > 0.01 and cur > vwap * 1.03:
                logging.warning("OVERPump detected")
                mock_notify("OVERPUMP — SHORT ZONE", self.details(cur, funding))
                self.reset()

    def details(self, price, funding=None):
        return {
            "symbol": self.symbol,
            "price": price,
            "volume": sum(self.volumes),
            "candle": self.candles,
            "orderbook": self.orderbook,
            "funding_rate": funding
        }

    def reset(self):
        self.prices.clear()
        self.times.clear()
        self.last_peak = None
        self.last_peak_time = None

# Функція для симуляції даних з вебсокету (додає ціни та об'єми з затримками або фіксованим часом)
def simulate_ws_data(analyzer, prices_sequence, volumes_sequence=None, time_increments=1, use_real_sleep=False):
    if volumes_sequence is None:
        volumes_sequence = [0] * len(prices_sequence)  # За замовчуванням нулі

    current_time = time.time()  # Початковий час
    for price, volume in zip(prices_sequence, volumes_sequence):
        analyzer.update_volume(volume)
        if use_real_sleep:
            analyzer.update_price(price)  # Використовує реальний час
            time.sleep(time_increments)  # Реальна затримка
        else:
            analyzer.update_price(price, custom_time=current_time)  # Фіксований час
            current_time += time_increments  # Імітуємо приріст часу

# Тестові сценарії
def run_tests():
    global mock_get_funding_rate  # Дозволяємо перевизначати в тестах

    print("\n=== Тест 1: Перевірка deque (фіксована довжина черги) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    for i in range(350):
        analyzer.update_price(1.0 + i * 0.0001, custom_time=i)
    print(f"Довжина prices після 350 додавань (maxlen=300): {len(analyzer.prices)}")  # Повинно бути 300
    print(f"Перша ціна: {analyzer.prices[0]} (очікується 51-ша додана, тобто 1.0 + 50*0.0001 ≈ 1.005)")  # Оскільки перші 50 видалено

    print("\n=== Тест 2: Dump (падіння на 15% за 10 сек) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices = [1.0] * 19 + [0.85]  # 20 цін: перші 19=1.0, остання=0.85 (delta=-15%)
    simulate_ws_data(analyzer, prices, time_increments=0.5)  # Загальна duration=9.5 сек, speed=15/9.5≈1.58 >0 (але для dump speed не перевіряється)
    # Очікується: Dump detected, NOTIFY DUMP

    print("\n=== Тест 3: Pump (зростання на 6% за 10 сек, speed>0.02) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices = [1.0] * 19 + [1.06]  # delta=6%, duration=9.5 сек, speed=6/9.5≈0.63 >0.02
    simulate_ws_data(analyzer, prices, time_increments=0.5)
    # Очікується: Pump detected, NOTIFY PUMP

    print("\n=== Тест 4: Pump з недостатньою швидкістю (зростання на 6% за 400 сек, speed<0.02) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices = [1.0] * 19 + [1.06]  # delta=6%, але duration=400 сек, speed=6/400=0.015 <0.02
    simulate_ws_data(analyzer, prices, time_increments=20)
    # Очікується: Нічого (не Pump)

    print("\n=== Тест 5: Last peak (зростання на 10% за 5 сек, speed>0.03) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices = [1.0] * 19 + [1.10]  # delta=10%, duration=9.5, speed=10/9.5≈1.05 >0.03 → last_peak=1.10
    simulate_ws_data(analyzer, prices, time_increments=0.5)
    print(f"Last peak after simulation: {analyzer.last_peak}")  # Очікується 1.10

    print("\n=== Тест 6: Overpump (після peak, минув 15+ сек, funding>0.01, cur>vwap*1.03) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    # Спочатку симулюємо peak
    prices_for_peak = [1.0] * 19 + [1.10]  # delta=10%, speed високий → last_peak=1.10
    simulate_ws_data(analyzer, prices_for_peak, time_increments=0.5)
    
    # Перевизначаємо funding
    def high_funding(symbol):
        return 0.015  # >0.01
    mock_get_funding_rate = high_funding
    
    # Додаємо ще дані: минув 15 сек, cur=1.15 (вище vwap)
    additional_prices = [1.15]  # cur=1.15, vwap буде близько 1.0-1.10, 1.15 > vwap*1.03
    simulate_ws_data(analyzer, additional_prices, time_increments=15)  # +15 сек
    # Очікується: OVERPump detected, NOTIFY OVERPUMP

    print("\n=== Тест 7: Overpump не спрацьовує (funding низький) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices_for_peak = [1.0] * 19 + [1.10]
    simulate_ws_data(analyzer, prices_for_peak, time_increments=0.5)
    
    def low_funding(symbol):
        return 0.005  # <0.01
    mock_get_funding_rate = low_funding
    
    additional_prices = [1.15]
    simulate_ws_data(analyzer, additional_prices, time_increments=15)
    # Очікується: Нічого (funding низький)

    print("\n=== Тест 8: Reset після події (deque очищається) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices = [1.0] * 19 + [0.85]  # Dump
    simulate_ws_data(analyzer, prices, time_increments=0.5)
    print(f"Довжина prices після reset: {len(analyzer.prices)}")  # Очікується 0

    print("\n=== Тест 9: Імітація реального часу з sleep (Pump) ===")
    analyzer = MarketAnalyzer("TEST-USDT")
    prices = [1.0] * 19 + [1.06]
    simulate_ws_data(analyzer, prices, time_increments=0.1, use_real_sleep=True)  # Реальні затримки 0.1 сек
    # Очікується: Pump (duration≈1.9 сек, speed≈3.16 >0.02)

# Запуск тестів
if __name__ == "__main__":
    run_tests()