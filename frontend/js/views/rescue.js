/**
 * Trang "Ứng cứu": hotline cứu hộ và form yêu cầu cứu hộ.
 * Hiện CHỈ chạy ở phía trình duyệt (tra dịch vụ theo loại xe rồi hướng dẫn gọi hotline);
 * chưa có API điều phối ở backend.
 */
import { rescueProblemTypes, rescueServices } from "../data/rescue.js";
import { state } from "../state.js";
import { $, esc, icon, toast } from "../utils.js";

export function initRescue() {
  const rescueLocBtn = $("#rescue-loc-btn");
  if (rescueLocBtn) {
    rescueLocBtn.addEventListener("click", () => {
      if (!navigator.geolocation) {
        toast("Trình duyệt không hỗ trợ định vị GPS.");
        return;
      }
      rescueLocBtn.disabled = true;
      rescueLocBtn.innerHTML = "Đang định vị GPS…";
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          let nearestName = "";
          if (state.data && state.data.roads) {
            let minDist = Infinity;
            for (const r of state.data.roads) {
              const d = Math.hypot(
                (r.coordinates[0][0] + r.coordinates[1][0]) / 2 - lat,
                (r.coordinates[0][1] + r.coordinates[1][1]) / 2 - lng,
              );
              if (d < minDist) {
                minDist = d;
                nearestName = r.name;
              }
            }
          }
          const text = nearestName
            ? `Gần ${nearestName} (Tọa độ: ${lat.toFixed(4)}, ${lng.toFixed(4)})`
            : `Tọa độ: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
          $("#rescue-address").value = text;
          rescueLocBtn.disabled = false;
          rescueLocBtn.innerHTML = `${icon("target")}Lấy vị trí GPS hiện tại`;
          toast("Đã định vị thành công: " + text);
        },
        (err) => {
          rescueLocBtn.disabled = false;
          rescueLocBtn.innerHTML = `${icon("target")}Lấy vị trí GPS hiện tại`;
          toast("Không thể lấy vị trí GPS: " + (err.message || "Quyền truy cập bị từ chối"));
        },
        { enableHighAccuracy: true, timeout: 8000 },
      );
    });
  }
  const rescueForm = $("#rescue-request-form");
  if (rescueForm) {
    rescueForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const vehicle = $("#rescue-vehicle").value;
      const typeKey = $("#rescue-type").value;
      const address = $("#rescue-address").value.trim();
      const phone = $("#rescue-phone").value.trim();
      const note = $("#rescue-note").value.trim();
      const srv = rescueServices[vehicle] || rescueServices.car;
      const probLabel = rescueProblemTypes[typeKey] || "Sự cố ngập nước";

      const resultBox = $("#rescue-form-result");
      resultBox.hidden = false;
      resultBox.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
          <span style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#087f72;color:white;flex-shrink:0;">${icon("check")}</span>
          <div>
            <strong style="font-size:14px;color:#087f72;display:block;">Đã tiếp nhận yêu cầu ứng cứu!</strong>
            <span style="font-size:11px;color:#537365;">Đơn vị phụ trách đề xuất: <b>${esc(srv.name)}</b></span>
          </div>
        </div>
        <div style="font-size:11px;line-height:1.6;background:white;padding:10px 12px;border-radius:8px;border:1px solid #d0e7dc;margin-bottom:12px;color:#354e43;">
          <div>📍 <b>Vị trí:</b> ${esc(address)}</div>
          <div>📞 <b>SĐT liên hệ:</b> ${esc(phone)}</div>
          <div>⚠️ <b>Tình trạng:</b> ${esc(probLabel)}${note ? " (" + esc(note) + ")" : ""}</div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <a href="${srv.tel}" class="button primary" style="background:#de4c3c!important;flex:1;min-height:38px;justify-content:center;text-decoration:none;">
            ${icon("phone")}Bấm gọi Hotline: ${srv.hotline}
          </a>
          <a href="${srv.url}" target="_blank" rel="noopener" class="button secondary" style="min-height:38px;justify-content:center;text-decoration:none;">
            ${icon("external")}Mở website
          </a>
        </div>
        <div style="margin-top:10px;font-size:10px;color:#6b8577;line-height:1.5;">
          💡 <b>Lưu ý an toàn:</b> Nhấn nút <i>"Bấm gọi Hotline"</i> để tổng đài viên điều xe cứu hộ gần nhất tiếp cận hiện trường nhanh nhất (15–20 phút).
        </div>
      `;

      toast(`Đã tiếp nhận! Vui lòng gọi hotline ${srv.hotline} để được cứu hộ hỗ trợ tức thì.`);
    });
  }
}
