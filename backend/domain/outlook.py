"""
Stock RT - Multi-Source Outlook Engine
Dự báo triển vọng tương lai đa chiều tổng hợp từ GSO, Vietstock, CafeF, VnExpress và SSI.
"""

def build_macro_context(news_list):
  """Bối cảnh vĩ mô chỉ dựa trên tin chung lấy trực tiếp (kèm nguồn và ngày).

  Engine không tự đánh giá môi trường vĩ mô/ngành khi chưa tích hợp số liệu vĩ mô (lãi suất, tỷ giá, CPI...).
  """
  macro_items = [
      n for n in (news_list or [])
      if not n.get('tickerSpecific') and n.get('badge') in ('VĨ MÔ NHÀ NƯỚC', 'THỜI SỰ KINH TẾ (CHUNG)')
  ]
  if macro_items:
    headlines = '; '.join(
        f"'{n.get('title', '')}' ({n.get('source', '')}, {n.get('date') or 'không rõ ngày'})"
        for n in macro_items
    )
    macro_impact = (
        f'Tin vĩ mô mới nhất: {headlines}. '
        'Chưa tích hợp số liệu vĩ mô định lượng (lãi suất, tỷ giá, CPI, tín dụng); engine không tự kết luận môi trường ngành.'
    )
  else:
    macro_impact = 'Dữ liệu chưa ghi nhận (chưa lấy được tin vĩ mô và chưa tích hợp số liệu vĩ mô định lượng).'
  return 'Chưa đánh giá', 'slate', macro_impact


def generate_multi_source_future_outlook(
    ticker, sector, current_price, fundamental_info, technical_info,
    ssi_item=None, ssi_board=None, news_list=None
):
  """Wrapper tương thích ngược tổng hợp phân tích đa nguồn từ SecuritiesRiskAssessmentEngine."""
  from backend.domain.risk_engine import evaluate_securities_risk_engine

  risk_rep = evaluate_securities_risk_engine(
      ticker=ticker,
      sector=sector,
      current_price=current_price,
      fundamental_info=fundamental_info,
      technical_info=technical_info,
      ssi_item=ssi_item or {},
      ssi_board=ssi_board or {},
      news_list=news_list or [],
  )

  fg = risk_rep['marketFlow']
  act = risk_rep['actionConclusion']
  scen = risk_rep['scenarioMatrix']

  return {
      'consensus': act['status'].upper(),
      'consensusColor': act['statusColor'],
      'confidence': f"Fear & Greed: {fg['fearGreedScore']}/100 ({fg['fearGreedLabel']})",
      'macroSummary': f"[{risk_rep['macroSector']['environment']}] {risk_rep['macroSector']['macroImpact']}",
      'fundamentalSummary': f"{risk_rep['fundamentalRisk']['growthQuality']} {risk_rep['fundamentalRisk']['governanceDilutionRisk']}",
      'flowSummary': f"{fg['foreignFlow']} {fg['sentimentLiquidity']}",
      'bullScenario': f"Mục tiêu {scen['bullCase']['targetDisplay']}. Kích hoạt: {scen['bullCase']['trigger']}",
      'bearScenario': f"{scen['bearCase']['supportDisplay']}. Rủi ro kích hoạt: {scen['bearCase']['trigger']}",
      'tailLockRisk': risk_rep.get('tailLockRisk', False),
      'tailLockReasons': risk_rep.get('tailLockReasons', []),
      'dcScore': risk_rep.get('dcScore', 80),
      'dcRating': risk_rep.get('dcRating', 'CAO'),
      'bottomLine': risk_rep.get('bottomLine', ''),
      'riskEngine': risk_rep,
  }
