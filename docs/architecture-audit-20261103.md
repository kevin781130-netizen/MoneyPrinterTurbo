# MoneyPrinterTurbo — 架構審核與輕量化方案（2026-11-03）

狀態：**SOURCE_AUDIT_ONLY / NOT_RUNTIME_VERIFIED**  
範圍：Fork `kevin781130-netizen/MoneyPrinterTurbo`、支線 `dev/mpt-slim-20261103`。本次僅讀取 GitHub 原始碼與測試目錄，未安裝相依、未執行測試、未呼叫付費 API、未更動主程式。

## 1. 已確認的核心流程

- 入口：`app/controllers/v1/video.py` 的 `POST /videos` → `create_task()` → `app/services/task.py::start()`。
- 編排：`task.py::_run_pipeline()` 完成 preflight → script → terms → audio → subtitle → materials → rendering → task complete；跨平台發佈為成片後可選的背景作業。
- 文案：`app/services/llm.py`；旁白：`app/services/voice.py`。
- 素材：`app/services/material.py`；合成：`app/services/video.py`（MoviePy / FFmpeg）。
- 輸入模型：`app/models/schema.py::VideoParams`；WebUI：`webui/Main.py`；CLI：`cli.py`。
- 單獨的修訂渲染器：`app/services/video_project.py`，具備場景依賴圖、素材指紋及本機 FFmpeg 修訂重渲染功能；不是整個主流程的替代品。

## 2. 重要發現

1. **MiniMax H3 已有上游接入**：`app/services/metaso_minimax.py` + `material.py::_download_videos_metaso_minimax_on_demand()`；`task.py` 也做 API Key preflight 和遠端 task_id 失敗留存。是秘塔（Metaso）代理，不等於已接通使用者獨立的 H3 導演台。
2. **結構重心過大**：`material.py` 約 3,349 行、`video.py` 約 2,121 行、`task.py` 約 2,039 行、`voice.py` 單檔約 162 KB、`webui/Main.py` 約 411 KB。大量供應商及 UI 邏輯集中在同一檔，存在變更擴散風險；**僅憑大小不能判定為冗餘或安全可刪**。
3. **現成測試資產**：`test/services/` 有主流程、素材、H3/Metaso、WebUI、`video_project`、發佈及失敗恢復等測試。不可先刪測試或假稱已有 PASS。
4. **Docker 不是唯一操作路徑**：有 `pyproject.toml`、`uv.lock`、`app.launcher`、CLI/WebUI 啟動程式；可設計非 Docker 的本機驗收，但尚未驗證環境可用性。

## 3. 最小化產品邊界（建議，非已實作）

**保留且優先驗證**
- 腳本 → 旁白（含使用者提供音檔）→ 素材（先本地 / stock）→ 字幕 → MP4。
- 現有 `/videos` HTTP 合約與 `VideoParams`；已存在的 H3/Metaso provider 不重寫。
- FFmpeg 成片與既有回歸測試。

**暫時不擴展、不得直接刪除**
- 眾多雲端影片供應商、社群自動發佈、多種 TTS、帳號 OAuth 與複雜設定。先將 MVP 使用範圍限縮／預設關閉進階路徑；刪除前先做靜態引用與回歸評估。

**H3 / CutPilot 串接原則**
- H3：先重用現成 Metaso provider（需使用者自行設定有效憑證，呼叫會計費）；若需接「獨立 H3 導演台」，另設 *opt-in* 外部介面，傳入已生成的影片路徑/中立 manifest，不複製對方程式碼。
- CutPilot：在 MP4 完成後以檔案 + JSON manifest **交接**，讓 CutPilot 自己處理切片／再剪輯；不把 CutPilot 安裝進核心專案。這是設計提案，**尚未檢查其實際輸入合約**。

## 4. 下一刀建議：建立無付費 API 的最小 smoke test

1. 唯讀確認本地素材 + 自備音訊可走完整路徑、使用者原始 repo 設定是否足夠；不下載容器或呼叫付費接口。
2. 寫隔離測試：以 fixture 模擬素材、音訊，檢查 MP4 產生、SRT、失敗狀態及任務路徑安全。
3. 以明確輸出 `PASS / FAIL / ENVIRONMENT_BLOCKED` 判定；通過前不刪除任何模組、不宣告可封版。

## 5. 保護規則

- 不修改 `main`；只在 `dev/mpt-slim-20261103` 進行隔離驗證。
- 不使用 GitHub Actions；不要求先安裝 Docker。
- 不推送 API Keys / 個人資料；不觸發付費影片生成。
- 保留原始 MIT 授權及原作者版權聲明。
