import { getTop10Stocks } from '../api.js?v=2.6';
import { formatVND } from '../utils.js?v=2.6';

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : "--";
}

export async function loadTop10(onSelectTicker) {
  try {
    const result = await getTop10Stocks();
    safeSetText("topUpdateDate", `Cập nhật: ${result.date}`);
    const tbody = document.getElementById("topTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!result.data || result.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="py-4 text-center text-slate-500 text-xs">Chưa có dữ liệu bảng lọc hôm nay.</td></tr>`;
      return;
    }

    result.data.forEach((item, idx) => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/60 transition cursor-pointer";
      tr.innerHTML = `
        <td class="py-3 px-3 font-mono font-bold text-white flex items-center gap-2">
          <span class="w-5 h-5 flex items-center justify-center rounded bg-slate-800 text-[10px] text-slate-400 font-bold">${idx + 1}</span>
          <span class="text-blue-400 font-black text-sm">${item.ticker}</span>
        </td>
        <td class="py-3 px-3 text-slate-300 font-medium text-xs max-w-[150px] truncate">${item.name || item.ticker}</td>
        <td class="py-3 px-3 font-mono font-semibold text-slate-100">${formatVND(item.price)} đ</td>
        <td class="py-3 px-3 font-mono font-bold ${item.pctChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${item.change}</td>
        <td class="py-3 px-3">
          <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold ${item.volRatio >= 1.4 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-slate-800 text-slate-300'}">
            ${item.volSignal}
          </span>
        </td>
        <td class="py-3 px-3 font-mono text-slate-300">${item.rsi}</td>
        <td class="py-3 px-3 text-slate-400 text-xs font-mono">${item.trend}</td>
        <td class="py-3 px-3 font-mono text-emerald-400 font-medium">${item.entry}</td>
        <td class="py-3 px-3 font-mono text-blue-400 font-bold">${item.target}</td>
        <td class="py-3 px-3 text-center">
          <button data-ticker="${item.ticker}" class="view-detail-btn px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition whitespace-nowrap shadow-md shadow-blue-600/20">
            Xem chi tiết
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll(".view-detail-btn").forEach(button => {
      button.addEventListener("click", (e) => {
        const t = e.target.getAttribute("data-ticker");
        if (onSelectTicker) onSelectTicker(t);
      });
    });
  } catch (err) {
    console.error("Lỗi tải Top 10:", err);
  }
}
