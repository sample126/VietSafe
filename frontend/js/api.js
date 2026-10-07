/** Client gọi API backend. Tự gắn token phiên, header X-VietSafe (chống CSRF) và timeout 12 giây. */
import { authState } from "./state.js";

/** GET (hoặc method tùy ý qua options). Ném Error(message tiếng Việt) khi lỗi. */
export async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  const authHeaders = authState.token ? { "X-VietSafe-Session": authState.token } : {};
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        "X-VietSafe": "local",
        ...authHeaders,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Không thể xử lý yêu cầu.");
    return data;
  } catch (e) {
    if (e.name === "AbortError")
      throw new Error("Máy chủ phản hồi chậm. Hãy thử lại.", { cause: e });
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}

/** POST JSON. */
export const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
