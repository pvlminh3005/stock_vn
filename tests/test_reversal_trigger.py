# tests/test_reversal_trigger.py
"""Unit tests verifying Mốc XX (Reversal Trigger) and 2-Stage Pyramiding Guardrails.

Protects against whipsaw / bull-traps in heavy downtrends (e.g. FPT bounce under MA50).
"""

import unittest
from backend.domain.technicals import calculate_supertrend
from backend.domain.decision_engine import evaluate_tplus_strategy, evaluate_unified_decision


class TestReversalTriggerAndPyramiding(unittest.TestCase):

  def test_supertrend_returns_reversal_and_invalidation_triggers(self):
    """SuperTrend must calculate and expose reversalTrigger (Upper Band) and invalidationTrigger (Lower Band)."""
    highs = [50000.0, 49500.0, 49000.0, 48500.0, 48000.0]
    lows = [48500.0, 48000.0, 47500.0, 47000.0, 46500.0]
    closes = [49000.0, 48500.0, 48000.0, 47500.0, 47000.0]

    st = calculate_supertrend(highs, lows, closes, period=3, multiplier=2.0)
    self.assertIn('reversalTrigger', st)
    self.assertIn('invalidationTrigger', st)
    self.assertEqual(st['direction'], 'BEARISH')
    self.assertGreater(st['reversalTrigger'], closes[-1])
    self.assertLess(st['invalidationTrigger'], closes[-1])

  def test_probe_reversal_trigger_when_crossing_in_pink_cloud(self):
    """When stock is in Pink Cloud (Downtrend), if intraday price crosses Mốc XX, issue early probe recommendation."""
    current_price = 53800.0
    tech = {
        'ma20': 55000.0,
        'ma50': 61000.0,
        'ema9': 53000.0,
        'ema21': 54500.0,
        'rsi': 45.0,
        'volRatio': 1.1,
        'buyRatio': 52.0,
        'dayChangePct': 2.5,
        'atr14': 1200.0,
        'support': 52500.0,
        'resistance': 59000.0,
        'resistance2': 62000.0,
        'supertrend': {
            'isBullish': False,
            'isFlipBuy': False,
            'isFlipSell': False,
            'bandPrice': 53500.0,
            'reversalTrigger': 53500.0,  # Mốc XX
            'invalidationTrigger': 51200.0,
        },
        'adx': {'adx': 25.0, 'plusDi': 20.0, 'minusDi': 24.0, 'isSideway': False},
    }
    reg = {'regime': 'NEUTRAL', 'coefficient': 0.75}
    risk = {}

    res = evaluate_tplus_strategy('FPT', 'HOSE', current_price, tech, reg, risk)
    new_entry = res['newEntry']

    self.assertEqual(new_entry['action'], 'BUY')
    self.assertEqual(new_entry['subtag'], 'PROBE_REVERSAL_TRIGGER')
    self.assertIn('NHẶT THĂM DÒ (CHỚM VƯỢT MỐC XX', new_entry['badge'])
    self.assertIn('53,500', new_entry['badge'])
    self.assertLessEqual(new_entry['allocatedNowPct'], res['pilotNavPct'])
    self.assertTrue(res['isProbeReversal'])

  def test_probe_reversal_trigger_rejected_if_poor_rr(self):
    """If price crosses Mốc XX but target resistance is too close (R:R < 1.2), block probe."""
    current_price = 53800.0
    tech = {
        'ma20': 55000.0,
        'ma50': 61000.0,
        'ema9': 53000.0,
        'ema21': 54500.0,
        'rsi': 45.0,
        'volRatio': 1.1,
        'buyRatio': 52.0,
        'dayChangePct': 2.5,
        'atr14': 1200.0,
        'support': 51000.0,
        'resistance': 55000.0,  # R1 is only 55,000 (+2.2%), downside is 6.3% -> R:R < 1.2
        'resistance2': 57000.0,
        'supertrend': {
            'isBullish': False,
            'isFlipBuy': False,
            'isFlipSell': False,
            'bandPrice': 53500.0,
            'reversalTrigger': 53500.0,
            'invalidationTrigger': 51200.0,
        },
        'adx': {'adx': 25.0, 'plusDi': 20.0, 'minusDi': 24.0, 'isSideway': False},
    }
    reg = {'regime': 'NEUTRAL', 'coefficient': 0.75}
    risk = {}

    res = evaluate_tplus_strategy('FPT', 'HOSE', current_price, tech, reg, risk)
    new_entry = res['newEntry']

    self.assertEqual(new_entry['action'], 'WAIT')
    self.assertEqual(new_entry['subtag'], 'WAIT_POOR_RR')
    self.assertIn('VƯỢT MỐC XX NHƯNG R:R MỎNG', new_entry['badge'])

  def test_fpt_bounce_under_ma50_triggers_downtrend_bounce_badge(self):
    """When SuperTrend flips green under MA50 with -DI > +DI (FPT case), classify as bounce in downtrend."""
    current_price = 53900.0
    ma50 = 61274.0  # Price is 12% below MA50
    tech = {
        'ma20': 54500.0,
        'ma50': ma50,
        'ema9': 53200.0,
        'ema21': 54800.0,
        'rsi': 48.0,
        'volRatio': 1.3,
        'buyRatio': 54.0,
        'dayChangePct': 3.2,
        'atr14': 1400.0,
        'support': 52500.0,
        'resistance': 59000.0,
        'resistance2': 62000.0,
        'supertrend': {
            'isBullish': True,
            'isFlipBuy': True,  # Just flipped Green
            'isFlipSell': False,
            'bandPrice': 51500.0,
            'reversalTrigger': 53500.0,
            'invalidationTrigger': 51500.0,
        },
        'adx': {'adx': 38.0, 'plusDi': 14.6, 'minusDi': 33.7, 'isSideway': False},
    }
    reg = {'regime': 'NEUTRAL', 'coefficient': 0.75}
    risk = {}

    res = evaluate_tplus_strategy('FPT', 'HOSE', current_price, tech, reg, risk)
    new_entry = res['newEntry']

    self.assertEqual(new_entry['action'], 'BUY')
    self.assertEqual(new_entry['subtag'], 'BUY_BOUNCE_IN_DOWNTREND')
    self.assertIn('HỒI KỸ THUẬT (THĂM DÒ DƯỚI MA50)', new_entry['badge'])
    self.assertIn('TUYỆT ĐỐI KHÔNG MUA ĐUỔI', new_entry['reason'])
    self.assertTrue(res['isBounceInDowntrend'])

  def test_prevent_chasing_on_day_2_of_downtrend_bounce(self):
    """On Day 2+ of a downtrend bounce, system must block buying to avoid the FPT bull trap."""
    current_price = 54800.0
    ma50 = 61274.0
    tech = {
        'ma20': 54000.0,
        'ma50': ma50,
        'ema9': 53800.0,
        'ema21': 54600.0,
        'rsi': 52.0,
        'volRatio': 0.9,
        'buyRatio': 50.0,
        'dayChangePct': -0.5,  # Stalling on day 2
        'atr14': 1400.0,
        'support': 51000.0,
        'resistance': 58000.0,
        'resistance2': 62000.0,
        'supertrend': {
            'isBullish': True,
            'isFlipBuy': False,  # Day 2+
            'isFlipSell': False,
            'bandPrice': 51500.0,
            'reversalTrigger': 51500.0,
            'invalidationTrigger': 51500.0,
        },
        'adx': {'adx': 36.0, 'plusDi': 15.0, 'minusDi': 32.0, 'isSideway': False},
    }
    reg = {'regime': 'NEUTRAL', 'coefficient': 0.75}
    risk = {}

    res = evaluate_tplus_strategy('FPT', 'HOSE', current_price, tech, reg, risk)
    new_entry = res['newEntry']

    self.assertEqual(new_entry['action'], 'WAIT')
    self.assertEqual(new_entry['subtag'], 'WAIT_BOUNCE_EXTENDED')
    self.assertIn('SÓNG HỒI DƯỚI MA50 - TRÁNH MUA ĐUỔI', new_entry['badge'])
    self.assertEqual(new_entry['allocatedNowPct'], 0.0)

  def test_holding_in_pink_cloud_warns_exit_never_hold(self):
    """When a stock is in Pink Cloud, holding position must recommend exiting/reducing, never saying 'GỒNG LÃI'."""
    current_price = 52000.0
    tech = {
        'ma20': 56000.0,
        'ma50': 61000.0,
        'ema9': 53000.0,
        'ema21': 55000.0,
        'rsi': 38.0,
        'volRatio': 1.0,
        'buyRatio': 44.0,
        'dayChangePct': -1.2,
        'atr14': 1200.0,
        'support': 50000.0,
        'resistance': 56000.0,
        'resistance2': 60000.0,
        'supertrend': {
            'isBullish': False,
            'isFlipBuy': False,
            'isFlipSell': False,  # In the middle of pink cloud
            'bandPrice': 55000.0,
            'reversalTrigger': 55000.0,
            'invalidationTrigger': 49000.0,
        },
        'adx': {'adx': 30.0, 'plusDi': 16.0, 'minusDi': 28.0, 'isSideway': False},
    }
    reg = {'regime': 'NEUTRAL', 'coefficient': 0.75}
    risk = {}

    res = evaluate_tplus_strategy('FPT', 'HOSE', current_price, tech, reg, risk)
    holding = res['holding']

    self.assertEqual(holding['action'], 'SELL')
    self.assertEqual(holding['subtag'], 'EXIT_DOWNTREND')
    self.assertIn('VÙNG HỒNG DOWNTREND', holding['badge'])
    self.assertNotIn('GỒNG LÃI', holding['badge'])

  def test_unified_decision_exposes_reversal_trigger(self):
    """evaluate_unified_decision targets_and_stops must expose reversalTrigger."""
    current_price = 52000.0
    tech = {
        'ma20': 56000.0,
        'ma50': 61000.0,
        'ema9': 53000.0,
        'ema21': 55000.0,
        'rsi': 38.0,
        'volRatio': 1.0,
        'buyRatio': 44.0,
        'dayChangePct': -1.2,
        'atr14': 1200.0,
        'support': 50000.0,
        'resistance': 56000.0,
        'resistance2': 60000.0,
        'supertrend': {
            'isBullish': False,
            'isFlipBuy': False,
            'isFlipSell': False,
            'bandPrice': 55000.0,
            'reversalTrigger': 55000.0,
            'invalidationTrigger': 49000.0,
        },
        'adx': {'adx': 30.0, 'plusDi': 16.0, 'minusDi': 28.0, 'isSideway': False},
    }
    fund = {'faScore': 80, 'pe': 18.0, 'pb': 4.0, 'roe': 25.0}
    decision = evaluate_unified_decision('FPT', 'HOSE', current_price, fund, tech)
    ts = decision.get('targetsAndStops', {})

    self.assertIn('reversalTrigger', ts)
    self.assertEqual(ts['reversalTrigger']['price'], 55000.0)
    self.assertIn('Mốc XX', ts['reversalTrigger']['label'])

  def test_supertrend_requires_ma20_confirmation_to_flip_bullish(self):
    """SuperTrend must not flip to Green (BULLISH) when price crosses finalUpper if price remains below MA20."""
    # Build 25 candles in a downtrend from 60,000 down to 50,000
    closes = [60000.0 - i * 400.0 for i in range(24)]  # Day 0 to 23: ends at 50,800. MA20 is ~55,000
    highs = [c + 500.0 for c in closes]
    lows = [c - 500.0 for c in closes]

    # Candle 24 (Day 25): A technical bounce to 53,900.
    # It crosses final_upper (~53,600), but MA20 is still around 55,000 (Close 53,900 < MA20 55,000)
    highs.append(54000.0)
    lows.append(50500.0)
    closes.append(53900.0)

    st = calculate_supertrend(highs, lows, closes, period=10, multiplier=1.8)

    # Must stay BEARISH (Pink Cloud) because price is below MA20
    self.assertEqual(st['direction'], 'BEARISH')
    self.assertFalse(st['isBullish'])
    self.assertTrue(st['isBearish'])
    self.assertFalse(st['isFlipBuy'])

    # Now simulate candle 25 closing ABOVE MA20 (e.g. 58,000 > MA20 ~55,000)
    highs.append(58500.0)
    lows.append(54000.0)
    closes.append(58000.0)

    st_confirmed = calculate_supertrend(highs, lows, closes, period=10, multiplier=1.8)
    # Must now flip to BULLISH (Green Cloud) with MA20 confirmation
    self.assertEqual(st_confirmed['direction'], 'BULLISH')
    self.assertTrue(st_confirmed['isBullish'])
    self.assertTrue(st_confirmed['isFlipBuy'])


if __name__ == '__main__':
  unittest.main()
