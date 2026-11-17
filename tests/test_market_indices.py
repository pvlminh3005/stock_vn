import unittest
from unittest.mock import patch
from backend.data_providers.market_board_provider import get_vnindex_summary


class TestVNIndexSummary(unittest.TestCase):

  @patch('backend.data_providers.market_board_provider.fetch_json')
  def test_get_vnindex_summary_vps_success(self, mock_fetch):
    # Mock VPS API response
    mock_fetch.return_value = [{
        'id': 1101,
        'mc': '10',
        'cIndex': 1743.27,
        'oIndex': 1734.93,
        'vol': 180704894,
        'ot': '8.34|0.48%|4207246.793|115|176|56',
    }]

    res = get_vnindex_summary()
    self.assertEqual(res['index'], 'VNINDEX')
    self.assertEqual(res['price'], 1743.27)
    self.assertEqual(res['ref'], 1734.93)
    self.assertEqual(res['change'], 8.34)
    self.assertEqual(res['changePercent'], 0.48)
    self.assertEqual(res['volume'], 180704894)
    self.assertEqual(res['source'], 'VPS_REALTIME')
    self.assertEqual(res['advances'], 115)
    self.assertEqual(res['declines'], 176)
    self.assertEqual(res['noChange'], 56)

  @patch('backend.data_providers.market_board_provider.fetch_json')
  def test_get_vnindex_summary_entrade_fallback(self, mock_fetch):
    # First call (VPS) raises Exception, then Entrade 1D and 1m return valid data
    def side_effect(url, **kwargs):
      if 'vps.com.vn' in url:
        raise ConnectionError('VPS timeout')
      if 'resolution=1D' in url:
        return {
            'c': [1730.0, 1734.93],
            't': [1794400000, 1794500000],  # past days
        }
      if 'resolution=1' in url:
        import time
        now_ts = int(time.time())
        return {
            'c': [1740.0, 1743.20],
            't': [now_ts - 120, now_ts - 60],
            'v': [50000, 60000],
        }
      return {}

    mock_fetch.side_effect = side_effect

    res = get_vnindex_summary()
    self.assertEqual(res['index'], 'VNINDEX')
    self.assertEqual(res['price'], 1743.20)
    self.assertEqual(res['ref'], 1734.93)
    self.assertEqual(res['change'], 8.27)
    self.assertEqual(res['source'], 'ENTRADE_1M')
    self.assertEqual(res['volume'], 110000)

  @patch('backend.data_providers.market_board_provider.fetch_json')
  def test_get_vnindex_summary_error_fallback(self, mock_fetch):
    mock_fetch.side_effect = Exception('All networks down')
    res = get_vnindex_summary()
    self.assertEqual(res['index'], 'VNINDEX')
    self.assertEqual(res['price'], 1250.0)
    self.assertEqual(res['change'], 0.0)


if __name__ == '__main__':
  unittest.main()

