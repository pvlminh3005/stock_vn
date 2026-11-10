"""
Stock RT - Portfolio DTO Models
Định nghĩa các Class Data Transfer Objects (DTO) có kiểu dữ liệu tường minh:
- PortfolioHolding: Vị thế gom nhóm của một mã cổ phiếu (VWAP, lãi/lỗ đã chốt & chưa chốt)
- PortfolioSummary: Tổng kết tài chính danh mục (NAV, sức mua, tổng lãi, tỷ lệ %)
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class PortfolioHolding:
    """Model Vị thế cổ phiếu đã gom nhóm theo mã."""
    symbol: str
    holding_volume: int = 0
    total_cost: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    total_buy_vol: int = 0
    total_sell_vol: int = 0
    total_buy_val: float = 0.0
    total_sell_val: float = 0.0
    buy_trades_count: int = 0
    sell_trades_count: int = 0
    first_trade_date: str = ''
    last_trade_date: str = ''
    current_price: float = 0.0
    ref_price: float = 0.0
    change_pct: float = 0.0
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    weight_pct: float = 0.0
    exchange: str = 'HOSE'
    is_holding: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert sang dict chuẩn để trả về API."""
        return asdict(self)


@dataclass
class PortfolioSummary:
    """Model Tổng kết chỉ số tài chính của danh mục cá nhân."""
    total_nav: float = 0.0
    total_buy_cost: float = 0.0
    current_market_val: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    available_nav: float = 0.0
    holdings_count: int = 0
    closed_count: int = 0
    total_trades_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert sang dict chuẩn để trả về API."""
        return asdict(self)

