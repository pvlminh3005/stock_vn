import { formatVND, formatCompactNumber } from '../utils.js?v=2.6';

let currentRiskReportMarkdown = "";

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : "--";
}

export function copyRiskReportMarkdown() {
  if (!currentRiskReportMarkdown) {
    alert("Chưa có nội dung báo cáo Markdown.");
    return;
  }
  navigator.clipboard.writeText(currentRiskReportMarkdown).then(() => {
    const btn = document.getElementById("copyMarkdownBtn");
    if (btn) {
      const oldHtml = btn.innerHTML;
      btn.innerHTML = `<i class="fa-solid fa-check text-emerald-400"></i> <span class="text-emerald-300">Đã copy!</span>`;
      setTimeout(() => { btn.innerHTML = oldHtml; }, 2000);
    }
  }).catch(() => {
    alert("Không thể sao chép vào bộ nhớ tạm.");
  });
}

// Gán hàm vào window để gọi từ thuộc tính onclick trong template HTML
window.copyRiskReportMarkdown = copyRiskReportMarkdown;

export function renderFutureOutlook(outlook, riskEngine, allData) {
  if (!outlook && !riskEngine) return;
  const eng = riskEngine || (outlook && outlook.riskEngine) || {};
  currentRiskReportMarkdown = eng.rawMarkdown || "";

  // 1. Header: Trạng thái & Badge
  const status = (eng.actionConclusion && eng.actionConclusion.status) ? eng.actionConclusion.status : (outlook.consensus || "THEO DÕI");
  const statusColor = (eng.actionConclusion && eng.actionConclusion.statusColor) ? eng.actionConclusion.statusColor : (outlook.consensusColor || "slate");

  const badgeEl = document.getElementById("outlookBadge");
  const actionTextEl = document.getElementById("actionStatusText");
  const colorMap = {
    emerald: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    blue: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    amber: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    rose: "bg-rose-500/20 text-rose-400 border-rose-500/30",
    slate: "bg-slate-800 text-slate-300 border-slate-700",
  };
  const textColMap = {
    emerald: "text-emerald-400",
    blue: "text-blue-400",
    amber: "text-amber-400",
    rose: "text-rose-400",
    slate: "text-slate-300",
  };

  if (badgeEl) {
    badgeEl.innerText = status.toUpperCase();
    badgeEl.className = `text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border ${colorMap[statusColor] || colorMap.slate}`;
  }
  if (actionTextEl) {
    actionTextEl.innerText = status.toUpperCase();
    actionTextEl.className = `text-sm font-black uppercase tracking-wide ${textColMap[statusColor] || textColMap.slate}`;
  }

  // Fear & Greed index
  const fgScore = (eng.marketFlow && typeof eng.marketFlow.fearGreedScore === 'number') ? eng.marketFlow.fearGreedScore : 50;
  const fgLabel = (eng.marketFlow && eng.marketFlow.fearGreedLabel) ? eng.marketFlow.fearGreedLabel : "Cân bằng";
  safeSetText("outlookConfidence", `${fgScore}/100 (${fgLabel})`);

  // Guardrail Alert Banner
  const guardrails = (eng.actionConclusion && eng.actionConclusion.guardrailsTriggered) ? eng.actionConclusion.guardrailsTriggered : [];
  const guardrailBanner = document.getElementById("guardrailAlertBanner");
  const guardrailContent = document.getElementById("guardrailAlertContent");
  if (guardrails && guardrails.length > 0) {
    if (guardrailBanner) guardrailBanner.classList.remove("hidden");
    if (guardrailContent) guardrailContent.innerHTML = guardrails.map(g => `<p class="mt-1 leading-relaxed">• ${g}</p>`).join("");
  } else {
    if (guardrailBanner) guardrailBanner.classList.add("hidden");
  }

  // Phần 1: Vĩ mô & Ngành
  const macroEnv = (eng.macroSector && eng.macroSector.environment) ? eng.macroSector.environment : "Trung lập";
  const macroImpact = (eng.macroSector && eng.macroSector.macroImpact) ? eng.macroSector.macroImpact : (outlook.macroSummary || "--");
  const sectorName = (eng.macroSector && eng.macroSector.sector) || (allData && allData.fundamentals && allData.fundamentals.sector) || "Thị trường";
  safeSetText("macroEnvBadge", macroEnv);
  const macroEnvEl = document.getElementById("macroEnvBadge");
  if (macroEnvEl) {
    macroEnvEl.className = `text-[10px] px-2 py-0.5 rounded font-bold uppercase border ${macroEnv === 'Tích cực' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : (macroEnv === 'Bất lợi' ? 'bg-rose-500/10 text-rose-400 border-rose-500/30' : 'bg-amber-500/10 text-amber-400 border-amber-500/30')}`;
  }
  safeSetText("outlookMacro", macroImpact);
  safeSetText("macroSectorName", sectorName);

  // Phần 2: Nội Tại & Pháp lý
  const fundRisk = eng.fundamentalRisk || {};
  safeSetText("faMetricsQuick", `P/E: ${fundRisk.peDisplay || '--'} | ROE: ${fundRisk.roeDisplay || '--'}`);
  safeSetText("outlookFundamental", fundRisk.growthQuality || (outlook.fundamentalSummary || "--"));
  safeSetText("governanceRiskText", fundRisk.governanceDilutionRisk || "Dữ liệu chưa ghi nhận rủi ro pháp lý hay kế hoạch phát hành pha loãng tiêu cực.");

  // Phần 3: Dòng tiền & Tâm lý
  const mktFlow = eng.marketFlow || {};
  const fNet = typeof mktFlow.foreignNet === 'number' ? mktFlow.foreignNet : (allData ? allData.foreignNet : 0);
  const fNetText = fNet > 0 ? `NN: +${formatCompactNumber(fNet)} cp` : (fNet < 0 ? `NN: -${formatCompactNumber(Math.abs(fNet))} cp` : `NN: 0 cp`);
  safeSetText("foreignNetQuickBadge", fNetText);
  const fNetBadgeEl = document.getElementById("foreignNetQuickBadge");
  if (fNetBadgeEl) {
    fNetBadgeEl.className = `text-[10px] px-2 py-0.5 rounded font-mono font-bold border ${fNet > 0 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : (fNet < 0 ? 'bg-rose-500/10 text-rose-400 border-rose-500/30' : 'bg-slate-800 text-slate-300 border-slate-700')}`;
  }
  safeSetText("outlookFlow", mktFlow.foreignFlow || (outlook.flowSummary || "--"));
  safeSetText("activeBuyQuick", `${mktFlow.buyRatio || (allData && allData.technicals ? allData.technicals.buyRatio : 50)}%`);
  safeSetText("volRatioQuick", `${mktFlow.volRatio || (allData && allData.technicals ? allData.technicals.volRatio : 1.0)}x`);

  // Phần 4: Ma Trận Kịch Bản
  const scen = eng.scenarioMatrix || {};
  const bull = scen.bullCase || {};
  const bear = scen.bearCase || {};
  safeSetText("rrRatioValue", `1:${scen.rrRatio || (allData && allData.technicals ? allData.technicals.rrRatio : 2.0)}`);
  safeSetText("bullTargetBadge", bull.targetDisplay || (bull.targetPrice ? `${formatVND(bull.targetPrice)} đ` : "--"));
  safeSetText("bullScenario", bull.trigger || (outlook.bullScenario || "--"));
  safeSetText("bearSupportBadge", bear.supportDisplay || (bear.supportPrice ? `${formatVND(bear.supportPrice)} đ` : "--"));
  safeSetText("bearScenario", bear.trigger || (outlook.bearScenario || "--"));

  // Phần 5: Kết Luận Hành Động & Cảnh Báo Cốt Lõi
  const act = eng.actionConclusion || {};
  safeSetText("coreWarningText", act.coreWarning || "--");
}

export function renderNewsReferences(newsList) {
  const container = document.getElementById("newsListContainer");
  if (!container) return;

  if (!newsList || newsList.length === 0) {
    container.innerHTML = `<div class="p-3 bg-slate-950/60 border border-slate-800 rounded-xl text-xs text-slate-500 text-center">Chưa có thông tin sự kiện hoặc BCTC mới nhất.</div>`;
    return;
  }

  const badgeColorMap = {
    amber: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    cyan: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
    purple: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    rose: "bg-rose-500/20 text-rose-400 border-rose-500/30",
    blue: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    emerald: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  };

  container.innerHTML = newsList.map(item => `
    <div class="p-3 bg-slate-950/70 border border-slate-800/90 rounded-xl flex items-start justify-between gap-3 hover:border-slate-700 transition">
      <div class="space-y-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badgeColorMap[item.badgeColor] || 'bg-slate-800 text-slate-300 border-slate-700'}">
            ${item.badge}
          </span>
          <span class="text-xs font-semibold text-slate-400">${item.source}</span>
          <span class="text-[11px] text-slate-500 font-mono">${item.date}</span>
        </div>
        <div class="text-xs text-slate-200 leading-relaxed font-medium">
          ${item.url ? `<a href="${item.url}" target="_blank" rel="noopener noreferrer" class="hover:text-blue-400 transition">${item.title}</a>` : item.title}
        </div>
      </div>
      ${item.url ? `
        <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="text-slate-500 hover:text-blue-400 text-xs mt-1 flex-shrink-0" title="Mở liên kết nguồn">
          <i class="fa-solid fa-arrow-up-right-from-square"></i>
        </a>
      ` : ''}
    </div>
  `).join("");
}
