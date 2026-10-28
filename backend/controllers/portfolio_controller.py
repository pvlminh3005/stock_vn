"""
Stock RT - Portfolio Controller
Xử lý các endpoint gói danh mục đầu tư theo vốn & gợi ý mã thay thế:
- /api/portfolio-bundle: Sinh gói danh mục 2 mã tối ưu theo số vốn
- /api/portfolio-alternatives: Danh sách mã tương đương theo ngành hoặc toàn sàn
- /api/portfolio-sectors: Thống kê các nhóm ngành và khả năng mua lô 100 theo ngân sách
"""

from backend.domain.portfolio_bundler import (
    generate_portfolio_bundle,
    get_alternative_candidates,
    get_available_sectors_for_budget,
)


def handle_portfolio_bundle(capital=20_000_000, style='balanced'):
  """Xử lý yêu cầu tạo gói danh mục theo số vốn (/api/portfolio-bundle)."""
  try:
    cap = float(capital)
  except (ValueError, TypeError):
    cap = 20_000_000.0
  return generate_portfolio_bundle(capital=cap, style=style)


def handle_portfolio_alternatives(
    current_symbol='',
    sector='',
    max_budget=10_000_000,
    exclude_sector=None,
    target_sector=None,
):
  """Xử lý yêu cầu lấy mã thay thế (/api/portfolio-alternatives)."""
  try:
    budget = float(max_budget)
  except (ValueError, TypeError):
    budget = 10_000_000.0
  return get_alternative_candidates(
      current_symbol=current_symbol,
      sector=sector,
      max_budget=budget,
      exclude_sector=exclude_sector,
      target_sector=target_sector,
  )


def handle_portfolio_sectors(max_budget=10_000_000, exclude_sector=None):
  """Xử lý yêu cầu lấy danh sách nhóm ngành khả dụng theo ngân sách (/api/portfolio-sectors)."""
  try:
    budget = float(max_budget)
  except (ValueError, TypeError):
    budget = 10_000_000.0
  return get_available_sectors_for_budget(
      slot_budget=budget,
      exclude_sector=exclude_sector,
  )
