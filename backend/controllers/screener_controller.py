"""
Stock RT - Screener Controller
Bộ lọc cổ phiếu và tìm kiếm:
- /api/search: Tìm kiếm mã theo ký tự
- /api/screener: Bộ lọc cổ phiếu theo thanh khoản và biến động thực tế từ SSI
- /api/top-tplus: Danh sách cổ phiếu thanh khoản cao dẫn dắt
"""

from backend.data_providers.ssi_provider import get_ssi_board_data


def handle_search(query):
  """Tìm kiếm mã cổ phiếu từ bảng giá SSI."""
  q = (query or '').strip().upper()
  if not q:
    return []
  board = get_ssi_board_data()
  results = []
  for sym, item in board.items():
    if sym.startswith(q) or q in str(item.get('companyNameVi', '')).upper():
      results.append({
          'symbol': sym,
          'name': item.get('companyNameVi', item.get('clientName', sym)),
          'exchange': item.get('exchange', 'HOSE'),
          'price': item.get('matchedPrice', item.get('refPrice', 0)),
          'change': item.get('priceChange', 0),
          'percentChange': item.get('priceChangePercent', 0),
      })
      if len(results) >= 15:
        break
  return results


def handle_screener():
  """Bộ lọc cổ phiếu thanh khoản cao và tích cực trong phiên."""
  board = get_ssi_board_data()
  stocks = [
      v for v in board.values()
      if v.get('stockType') == 's' and len(str(v.get('stockSymbol', ''))) == 3
  ]
  # Sắp xếp theo giá trị giao dịch
  sorted_stocks = sorted(
      (s for s in stocks if (s.get('nmTotalTradedValue') or 0) > 0),
      key=lambda s: -(s.get('nmTotalTradedValue') or 0),
  )
  items = []
  for s in sorted_stocks[:50]:
    items.append({
        'symbol': s.get('stockSymbol'),
        'name': s.get('companyNameVi', s.get('clientName', '')),
        'exchange': s.get('exchange', 'HOSE'),
        'price': s.get('matchedPrice', s.get('refPrice', 0)),
        'change': s.get('priceChange', 0),
        'percentChange': s.get('priceChangePercent', 0),
        'volume': s.get('stockVol', 0),
        'value': s.get('nmTotalTradedValue', 0),
        'foreignNet': (s.get('buyForeignQtty', 0) - s.get('sellForeignQtty', 0)),
    })
  return {'stocks': items}


def handle_top_tplus():
  """Top 10 cổ phiếu có xung lực dòng tiền và tăng giá mạnh nhất."""
  res = handle_screener()
  stocks = res.get('stocks', [])
  gainers = [s for s in stocks if s.get('percentChange', 0) > 0]
  gainers.sort(key=lambda s: -(s.get('percentChange', 0)))
  return {'top': gainers[:10]}
