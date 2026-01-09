# Fairmont 報價單 17 欄位輸出邏輯規格

本文件定義家具 (Furniture) 與面料 (Fabric) 在 17 欄位 Excel 報價單中的資料來源與格式化規則。

---

## 1. 輸出欄位對照表

| 序號 | Excel 欄位 (Fairmont) | 家具 (Furniture) 處理邏輯 | 面料 (Fabric) 處理邏輯 |
|:--- |:--- |:--- |:--- |
| 1 | **NO.** | 系統生成 (Stage 7 排序產生) | 系統生成 (緊跟隨主家具排序) |
| 2 | **Item No.** | PDF `ITEM NO.:` 標籤提取 |  PDF `ITEM NO.:` 標籤提取 |
| 3 | **Description** | 原始 `description` 文字 | 格式：`{material_type} to {target_item_no}` |
| 4 | **Photo** | 在attachment頁 家具立體外觀圖 (去背/去 Logo) |在attachment頁 面料色卡或紋理圖 |
| 5 | **Dimension** | **長寬高數值**<br>`W{w} x D{d} x H{h} mm` | **規格字串組合**<br>`{材質}-{供應商}-{品牌}-{花色}-{寬度}` pattern/plain |
| 6 | **Qty** | 優先取自數量總表，次取規格頁 | 來源不明確先留空白 |
| 7 | **UOM** | `ea`, `set`, `pcs` (預設 `ea`) | `m`, `lm`, `sqft` (預設 `m`) |
| 8 | **Unit Rate** | (空白 - 採購手動填寫) | (空白 - 採購手動填寫) |
| 9 | **Amount** | (空白 - 採購手動填寫) | (空白 - 採購手動填寫) |
| 10 | **Unit CBM** | (空白 - 採購手動填寫) | (空白 - 採購手動填寫) |
| 11 | **Total CBM** | (空白 - 採購手動填寫) | (空白 - 採購手動填寫) |
| 12 | **Note** | (空白 - 採購手動填寫) |  (空白 - 採購手動填寫) |
| 13 | **Location** | index中的原始 `description` @之後文字 | PDF `ITEM:`提取 `@` 之後的家具 |
| 14 | **Materials Used / Specs** | 原始材質/規格的`description`詳細描述 | **規格字串組合**<br>`Pattern: {pattern}. Color: {color}. Rub Test: {abrasion}`<br>`Fire Rating: {fire_rating}` |
| 15 | **Brand** | **Null (強制留空)** | **必填** (取 `brand`) |
| 16 | **Category** | **1** (家具分類代號) | **5** (面料分類代號) |
| 17 | **Affiliate** | **Null (留空)** | **所屬家具編號** (多個用 `, ` 分隔，如 `DLX-102, DLX-106`) |

---

## 2. 核心處理差異說明

### A. Dimension 欄位定義
*   **家具**：必須是物理尺寸，優先取自 PDF 中的 `Overall Dimensions` 欄位。只取尺寸數值部分（如 `L2130 x W1930 x HT290mm`），不包含後面的說明文字。若為圓形家具，格式改為 `Dia.{d} x H{h} mm`。
*   **面料**：並非實體長寬，而是為了在 17 欄位中展示面料身份。系統會組合 `Content` (成份), `Vendor`, `Brand`, `Pattern` (花色), `Color` (顏色), `Fabric Width` (幅寬) 成為一個完整的描述字串。

### B. Brand 欄位定義
*   **家具**：在惠而蒙格式中，家具通常視為 OEM 產品，不特別標註品牌，故設為 `Null`。
*   **面料**：面料品牌 (如 JAB, Kvadrat 等) 是報價與採購的關鍵，系統會透過專門的 Prompt 強制提取並顯示。

### C. Materials Used / Specs 欄位定義
*   **家具**：從 PDF 的 DESCRIPTION 區塊提取原始材質規格描述。
*   **面料**：組合多個規格欄位成為完整描述字串，格式為：
    ```
    Pattern: {pattern}. Color: {color}. Rub Test: {abrasion}
    Fire Rating: {fire_rating}
    ```
    可選欄位（若有）：`Horizontal Repeat`, `Vertical Repeat`, `Pattern Direction`

### D. Category 欄位定義
產品分類代號，用於區分不同類型的產品：
*   **1**: 家具 (Furniture)
*   **5**: 面料 (Fabric)

未來可擴充更多分類代號，如燈具、窗簾等。

### E. Affiliate 欄位定義
標示面料所屬的家具項目：
*   **家具**：此欄位留空 (Null)
*   **面料**：填入所屬的家具 Item No.，若面料關聯多個家具，使用 `, ` (逗號加空格) 分隔
    *   範例：`DLX-102` (單一家具)
    *   範例：`DLX-102, DLX-106` (多個家具)

### F. 排序邏輯 (Fabric-Follows-Furniture)
在匯出 Excel 時，系統會自動偵測面料所屬的家具項目。面料項目會被安排在對應家具項目的下一列，NO. 序號會連號，以利檢核。