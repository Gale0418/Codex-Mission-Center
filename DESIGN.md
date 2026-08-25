---
name: Rainbow Singularity Overdrive — Constellation Tactical Plot
description: Codex Mission Center 的彩譜奇點深空任務戰情視覺系統
colors:
  ground: "#000d17"
  mission: "#011320"
  shell: "#061621"
  surface: "#142632"
  rail: "#041622"
  line: "rgba(151, 184, 201, 0.24)"
  line-strong: "rgba(151, 184, 201, 0.52)"
  cyan: "#62a7ce"
  cyan-peak: "#5cf5f4"
  cosmic-pink: "#ff5bb8"
  singularity-violet: "#806aff"
  amber: "#ffc63a"
  white: "#ffffff"
  secondary: "#bac9d3"
  muted: "#78909d"
typography:
  display:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.25rem, 2vw, 1.8rem)"
    fontWeight: 650
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "IBM Plex Mono, Cascadia Mono, SFMono-Regular, Consolas, monospace"
    fontSize: "0.67rem"
    fontWeight: 600
    letterSpacing: "0.12em"
    lineHeight: 1.5
rounded:
  control: "3px"
  card: "4px"
  panel: "5px"
spacing:
  shell: "clamp(14px, 3vw, 40px)"
  panel: "18px"
  canvas: "16px"
  territory: "12px"
components:
  attention-capsule:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.card}"
    padding: "7px 10px"
  task-agent:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.white}"
    rounded: "{rounded.card}"
    padding: "9px 10px"
  evidence-item:
    backgroundColor: "transparent"
    textColor: "{colors.white}"
    rounded: "0"
    padding: "10px 0"
  runtime-drawer:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.white}"
    rounded: "{rounded.panel}"
    padding: "18px"
  active-task:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.white}"
    rounded: "{rounded.card}"
    padding: "9px 10px"
  telemetry-ticker:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.cyan-peak}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  telemetry-rail:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.secondary}"
    rounded: "0"
    padding: "7px 18px"
---

# Design System: Rainbow Singularity Overdrive — Constellation Tactical Plot

## Overview

**Creative North Star: “Constellation Tactical Plot”**

這是一個以 Rainbow Singularity Overdrive 為視覺世界、採 EVE-like 高資訊密度但不複製 EVE trade dress 或 icons 的深空旗艦橋 HUD：鮮艷 cosmic spectrum 圍繞鏡面深色 tactical console，任務仍不是裝飾性卡片，而是落在五個 lifecycle territory（Intake、In Progress、Blocked、Review、Done）的可讀戰術星座。視覺衝擊可以主導畫面，但語意 HTML 仍是任務資料、證據與新鮮度的唯一真相；Runtime 是獨立且預設收合的遙測層。

現行佈局採使用者核准的 **Fleet Command Deck A**：fleet backdrop 保持可見，主 mission panel 使用 `.50/.58` 的真透明階層；canvas 不使用不透明實色底，只保留定位網格與低 alpha 結構層；territory 使用 `.36`，一般 card 保留 `.66`、active card surface 提升至 `.72`。五個 territory 以軍事 phase label `BRIEFING / EXECUTION / HOLD / VERIFICATION / ARCHIVE` 為主標，並保留原 lifecycle 副標 `INTAKE / IN PROGRESS / BLOCKED · NEEDS INTERVENTION / REVIEW / DONE`。

所有可見時間、task/runtime 訊號與 polling 讀值都必須 truthful：horizon 同時顯示 LOCAL/UTC，Task/Runtime rail 只取 snapshot、計數與 polling 常數。畫面 doctrine 只宣告 `FILE SNAPSHOT`、`READ ONLY`、`NO SENSOR FEED`；fleet backdrop、broadcast 與幾何層不得被解讀成感測器資料。EVA-inspired 僅借用高張力的 command rhythm，不使用受保護名稱、logo 或 trade dress。

材質語彙是更實的黑曜石鏡面面板、fleet bridge 主背景中的多艘遠航星艦與下方行星、彩譜色彩參考、離子青/粉紅/紫色 emissive edges 與陶瓷白文字；琥珀仍只代表需要人介入的真實訊號。CSS 幾何層保留逆向同心環、軌道光跡、energy pulse 與邊框 edge flow；移除背景掃描亮帶與全畫面鏡面閃耀。真正 `agent.active` 的 task card 才有卡內 operation scan、emissive edge 與呼吸 aura；footer 則以真實資料驅動 telemetry ticker。

**Key Characteristics:**

- 彩譜奇點與鏡面深色面板形成主視覺；任務資料、證據與 freshness 仍是可追溯的操作真相。
- 黑曜石面板、active task card 光效與真實 telemetry ticker 將「正在發生什麼」變成可掃描的視覺節奏。
- DOM/HTML 保持產品真相，SVG 只畫已驗證依賴與 Runtime 拓撲，raster 只提供背景材質。
- 狀態新鮮度、不可用與 attention 都必須如實呈現。
- 4–6px 小圓角、1px 髮絲線、緊湊等寬標籤，避免 generic SaaS 卡片感。
- 幾何特效是可暫停、可降載的裝飾層，不得改寫 lifecycle 或 runtime state。
- 三層 parallax、geometry structure、depth rails 與 corner brackets 只提供空間對齊感，不暗示依賴關係。
- EVE-like 只代表高密度 telemetry 的掃描節奏與資料層次；品牌、trade dress、icons 與產品畫面維持自有語彙。

## Colors

配色是不可純黑的深墨藍鏡面底，疊加鮮艷 cosmic spectrum；冷青、粉紅與紫色負責奇點能量與邊緣流光，琥珀仍是唯一的人工作業焦點。

### Primary

- **Ion Cyan** (`{colors.cyan}`)：進行中 metadata、lifecycle 數字、scrollbar 與一般 topology 線。
- **Ion Cyan Peak** (`{colors.cyan-peak}`)：focus line、progress bar、task ID、Runtime 節點與奇點掃描高光。
- **Cosmic Pink** (`{colors.cosmic-pink}`)：主奇點 ring、active-card operation scan 與彩譜邊框的高能量段。
- **Singularity Violet** (`{colors.singularity-violet}`)：次級 ring、軌道光跡與邊框流光的冷色段。

### Secondary

- **Intervention Amber** (`{colors.amber}`)：attention、stale 警示與 Runtime `requiresAttention` 的次要 pulse/glow。只有 Blocked task 的主色是 HOLD red；其他 attention task 保留自己的 lifecycle family，不得被琥珀覆蓋。

### Neutral

- **Ground Ink** (`{colors.ground}`)：頁面最底層；不可替換成純黑。
- **Mission Ink** (`{colors.mission}`)：主 mission plot 與 canvas。
- **Bridge Shell** (`{colors.shell}`)：horizon、territory 與按鈕等外層表面。
- **Slate Surface** (`{colors.surface}`)：task agent 卡與 runtime agent 表面。
- **Quiet Rail** (`{colors.rail}`)：evidence rail 與 Runtime drawer。
- **Ceramic White** (`{colors.white}`)：主要標題、任務名稱與高優先文字。
- **Secondary Ceramic** (`{colors.secondary}`)：metadata、次要說明與一般狀態文字。
- **Muted Slate** (`{colors.muted}`)：empty state、read-only 輔助字。
- **Titanium Lines** (`{colors.line}` / `{colors.line-strong}`)：分隔線與 panel 邊框；維持 1px。

**The Amber Coordinate Rule.** 琥珀只回答「哪裡需要人介入」；不得拿來當一般品牌色、裝飾或完成狀態。其他彩譜顏色是視覺能量，不是資料狀態。

**The Task Status Family Rule.** Task card 主色依 lifecycle 固定落在 bounded family：`BRIEFING / Intake` 黃、`EXECUTION / In Progress` 綠、`HOLD / Blocked` 紅、`VERIFICATION / Review` 藍、`ARCHIVE / Done` 低彩度銀灰。每張卡以 task ID 做 deterministic 的細微 hue/saturation/lightness 變體，但不得跨出 family；卡片內可疊加約 8% alpha、由一角漸淡的同色 tint，保留深色底與文字對比；attention 只增加 amber pulse/glow，不改寫 lifecycle family；卡片永遠同時顯示 task ID 與文字狀態。

## Typography

**Display / UI Font:** Inter（fallback：`ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif`）
**Label / Telemetry Font:** IBM Plex Mono（fallback：`Cascadia Mono, SFMono-Regular, Consolas, monospace`）

**Character:** Inter 負責可讀的產品標題、任務與敘述；IBM Plex Mono 負責狀態 horizon、ID、數字與控制標籤，製造精確的設備讀值感。實作只宣告字體 stack，沒有在 HUD 內嵌字體檔。

### Hierarchy

- **Display**（650，`clamp(1.25rem, 2vw, 1.8rem)`，負 tracking `-0.025em`）：產品鎖定標題。
- **Panel heading**（650，約 `0.78rem`，tracking `0.17em`，uppercase）：plot、evidence、Runtime 標題。
- **Horizon label**（600，約 `0.67rem`，tracking `0.12em`，uppercase）：STATUS HORIZON 與來源/新鮮度 metadata。
- **Task title**（560，約 `0.78rem`、`1.25` line-height）：territory 內的 task helper 名稱，最多兩行 clamp；以 ellipsis 保持密度。
- **Task ID / state**（mono，約 `0.65rem` / `0.61rem`）：ID、狀態與可追蹤讀值。
- **Body / evidence**（400，約 `0.7–0.75rem`，`1.4–1.5` line-height）：目標、說明、證據內容與 fallback。

**The Two-Voice Rule.** 顯示型 Inter 與讀值型 mono 各司其職；不要把整頁改成全等寬字，也不要用裝飾性 display font。

## Layout

桌面是單一 HUD shell（`width: min(1800px, 100%)`、最小寬度 320px），內部先有 status horizon，再以約 4:1 的 mission plot / evidence rail 兩欄工作區呈現。彩譜 cosmic field 與 singularity-effects 覆蓋整個 shell；plot 與 rail 使用黑曜石鏡面面板與 masked edge energy flow，不放背景掃描亮帶或全畫面鏡面掃光。plot canvas 使用 64px 間距的極淡網格作定位輔助，並維持 `clamp(400px, 52vh, 560px)` 高度。五個 territory 在寬螢幕橫向排列，task list 可各自捲動，最多渲染 15 個 task helpers。

Deck A 的透明階層是 layout 的硬規格：主 mission plot 的漸層為 `rgba(...,.50)` → `rgba(...,.58)`，canvas 不設不透明實色底；territory 為 `rgba(...,.36)`，一般 card 為 `.66`，active card 才以 `.72` 表面搭配 operation scan、emissive edge 與 aura。這讓 primary fleet vista、行星與底部旗艦窗框保持可見，同時由 1px 邊框、文字陰影與幾何 rails 提供可讀性。

Footer 在 map legend 與 Runtime capsule 之間放置真實 telemetry ticker；它以 status、progress、tasks、blocked、freshness 組成單一訊息，視覺上以重複內容做無縫 CSS transform loop，但 screen reader 只讀一份 polite live announcement。空間層次分成三層：far（Rainbow/星場）、mid（奇點 ring/trail/pulse）、near（geometry structure、depth rails、alignment brackets）；不包含全畫面 specular sweep。

桌面 plot heading 下方另有雙層 telemetry rail：左側 Task Signal、右側 Runtime Signal。兩條 rail 只顯示真實狀態、計數與既定 polling 常數衍生的訊息，不是第二套生命週期真相，也不承擔座標、依賴或虛構資料。

桌面 shell 的裝飾 broadcast 在頂部以 LTR 方向流動（約 34s）；plot footer 的主要 telemetry ticker 以 RTL 方向流動（約 24s，行動版 36s）；左右兩側另有方向相反的 vertical waterfalls（約 30s）。它們只重複 doctrine 與 truthful telemetry 的文字節奏，`<=760px` 全部 secondary broadcast、waterfalls 與雙層 telemetry rail 隱藏，只保留主要 ticker 與可操作內容。

Runtime 展開時是右側 fixed dock（桌面寬度 `min(420px, 30vw)`、距右 18px）；`hud-shell.runtime-dock-open` 會讓 header 與主工作區增加 `calc(min(420px, 30vw) + 14px)` 的右側 margin，避免 dock 遮住主內容。`1080px` 以下不再讓主內容避讓，Runtime 改以 overlay 疊在畫面上；窄螢幕再收窄為左右 10px 的滿寬浮層。

響應式不是單純縮小：

- `1080px` 以下收窄工作區為約 3:0.9，shell padding 為 22px。
- `760px` 以下改為單欄，mission plot 最小高度 560px，evidence rail 至少 260px。
- `620px` 以下 shell padding 14px、header/plot heading/footer 改為縱向；五個 territory 變為單欄堆疊（每列至少 130px），拓撲線與 Runtime map 隱藏；Runtime drawer 改為左右 10px、上下 10px 的滿寬浮層。

## Elevation & Depth

深度由 ground → mission → shell → surface 的黑曜石鏡面深色階、可見 fleet backdrop、彩譜 emissive edge、panel glow 與主動幾何光場共同建立。主 mission panel 只以 `.50/.58` 的半透明漸層承載內容，territory `.36`、card `.66`（active `.72`）；canvas 不用不透明實色底。面板不使用背景掃描亮帶或鏡面閃耀，邊界改為 masked 1px typed-angle edge energy flow。這個 overdrive 讓 fleet vista 成為主視覺；所有光效仍是 `pointer-events: none` 的裝飾層，不得冒充資料。

### Shadow Vocabulary

- **Runtime overlay lift**（`0 18px 40px rgba(0,0,0,.32)`）：只用在可開關的 Runtime drawer。
- **Singularity field glow**（`0 0 28px rgba(92,245,244,.1)` + `inset 0 0 24px rgba(92,245,244,.035)`）：mission plot/evidence rail 的鏡面 emissive lift。
- **Agent interaction lift**：task agent hover/focus 以 `translateY(-1px)`、邊框與表面色變化表達，不新增個別卡片陰影。

**The Active Spectrum Rule.** Rainbow Singularity 的 ring/trail/pulse 與邊界 energy flow 可以明顯、飽和且持續運動；背景不得再加入掃描亮帶或鏡面閃耀。只有真實 active task 才能使用 operation scan；所有視覺層永遠是 pointer-events none，不能承擔任務、依賴、freshness 或 attention 語意。

## Shapes

所有容器使用小而一致的矩形圓角：panel 約 5px、task/territory 約 4–5px、控制約 3px；禁止 oversized pill。panel、territory、task、evidence 與 drawer 都以 1px titanium line 分界；shell 邊框改由 conic-gradient spectrum 流光描繪，focal/attention 邊框仍可提升對比，Blocked task 維持 red 邊框並以 amber pulse/glow 作次要提示，attention Runtime 仍使用 amber 邊框。拓撲 edge 使用 1.4px SVG stroke；逆向同心環與軌道光跡是不可互動的幾何裝飾。

## Components

元件共用 compact rectangle、semantic HTML 與明確狀態；presentation layer 不得取代內容層。

### Rainbow Singularity effects

- **Cosmic field:** 現行 `.rainbow-background` hook 實際載入 `mission-fleet-bridge-background.webp` 作為 primary background，opacity `1`、`saturate(1.24)`、`contrast(1.08)`、`brightness(.9)`，並隨 pointer 以 far-layer `translate3d(... * -3px)`、scale `1.04` 產生 700ms parallax；starfield depth support 另以 `-6px` 移動。`cosmic-spectrum-rainbow.jpg` 僅是色彩/風格 reference，不是目前主背景。
- **Counter-rotating rings:** 三層以中心約 `50% / 46%` 的同心 ring 疊加；primary `min(74vw, 980px)` / 30s 逆向旋轉，secondary `min(56vw, 700px)` / 22s、`scaleY(.7)`，tertiary `min(38vw, 500px)` / 16s、`scaleY(.48)`。
- **Orbital trails and pulse:** primary orbital trail 約 12s、secondary 約 9s 反向運動，分別使用 cyan/pink、amber/violet 邊緣；中心 energy pulse 約 4.8s。不再有 radial scan 或背景掃描亮帶。
- **Masked edge energy flow:** HUD shell 使用 1px masked conic edge，色序為 cyan → white → magenta → amber，透過 typed `--edge-angle` 約 9s 流動；mission plot/evidence rail 使用同樣 1px masked edge、typed `--panel-edge-angle` 約 12s 流動。mask 把能量限制在邊框，內容維持 z-index 1，絕不穿過內容；這些元素皆 `pointer-events: none`。
- **Geometry structure:** near layer 的 structure 約 inset `8% 3%`，含 12px 內框、彩譜水平 alignment line、四個 `52px` corner brackets，以及左右 `6%`、上下 `22%` 的 depth rails；它們只建立艦橋對齊與深度，不是資料線。
- **Pause contract:** `hud-shell.is-paused` 會暫停所有 animation；頁面 hidden 時由 JS 設定 paused 並降低 polling，避免背景特效與資料更新在不可見狀態持續消耗。

### Mission plot and territories

- **Shape:** 5px plot panel；內部 canvas 16px padding，territory 12px padding、4–5px 圓角。
- **Structure:** 依序呈現 `BRIEFING`（Intake）、`EXECUTION`（In Progress）、`HOLD`（Blocked）、`VERIFICATION`（Review）、`ARCHIVE`（Done）；主標下保留原 lifecycle 副標與每區數量。
- **Doctrine:** phase header 的輔助文案只說明 task order、file snapshot、read-only、command link 或 human intervention；它不是 sensor feed，也不補造座標、事件或任務真相。
- **Task helper:** semantic `li`，顯示 ID、title、textual state；最多 15 個，map placement 只是展示。主色使用依 lifecycle bounded 的 status family，只有 Blocked 維持 red，amber 只作 attention pulse/glow。
- **Task title / nameplate:** title 預設最多兩行 clamp；task helper 取得 keyboard focus 時顯示同一 task 的 nameplate（hover 也顯示），作為被截斷標題的補充資訊。
- **Bounded marquee:** 只有實際 DOM intrinsic width 超過可用寬度 2px 以上時，才由 JS 自動設定 `data-marquee="true"`，以 bounded ping-pong（`alternate`）在約 7–20s 間移動標題；不需 click 或 hover。未溢出時保持靜態；不得為了裝飾強迫所有標題跑馬。
- **Active binding:** 只有資料中的 `agent.active === true` 才能加上 `data-active="true"`；Done、idle/Idle task 即使有 active 欄位也不套用 active treatment。不要從 status、位置或 Runtime 推測 active。
- **Active card treatment:** active task 使用黑曜石 surface 上的 cyan/pink aura（`activeAuraBreathe` 約 3.2s）、唯一的卡內 operation scan（約 3.8s）、conic-gradient emissive edge（約 2.8s）；內容置於光效之上，nameplate 維持最高層。背景與面板不使用 operation scan。
- **Empty / unknown:** 使用 muted empty state；Unknown 不得被渲染成 Done。

### Task topology

- **Style:** SVG presentation layer，依真實 `dependencies` 產生 authored path 與 arrow marker；一般線為低對比 cyan。
- **State:** 沒有已驗證依賴時隱藏線並呈現 `NO VERIFIED DEPENDENCY EDGES` 的語意狀態；不捏造連線。
- **Responsive:** `620px` 以下隱藏拓撲，task DOM 仍保留。

### Attention capsule / controls

- **Style:** compact rectangular button（7px 10px padding、4px radius、shell surface），icon dot + label；attention=true 時邊框/文字改 amber。
- **Hover / focus:** hover 提升 cyan 對比；全域 `:focus-visible` 為 2px cyan-peak outline、3px offset。
- **Runtime drawer:** 預設收合；桌面展開為 right-side dock 並觸發主內容避讓，窄螢幕則是 overlay。點擊 capsule 展開、Close 或 Escape 關閉，並恢復原 focus。

### Telemetry ticker

- **Source:** ticker 只由目前 task snapshot 的 `status`、`progress`、`agents.length`、`blocked.length` 與 `freshness` 組成；不可填入 mock 值或 Runtime 推測。
- **Presentation:** `TELEMETRY` label、1px cyan border、ground background、mono uppercase text；track 以兩份相同訊息每 24s 做 CSS transform loop，gap 約 48px。
- **Accessibility:** viewport 裝飾內容 `aria-hidden`；`telemetryAnnouncement` 保留一份去重後的 polite live status，讓動態 ticker 不造成重複朗讀。

### Desktop telemetry rails

- **Layout:** `.telemetry-rail` 位於 plot heading 下方，桌面以約 `1.2fr / .8fr` 分成 Task Signal 與 Runtime Signal，最小高度約 42px、上下 7px、左右 18px；strip 使用 1px cyan border、3px radius、corner brackets 與 repeating linear grid。
- **Broadcast orientation:** 頂部 broadcast 為 LTR（約 34s）；footer telemetry ticker 為 RTL（約 24s，`<=620px` 約 36s）；左右 vertical waterfalls 各自維持相反方向（約 30s）。它們是 `aria-hidden` 的節奏層，`<=760px` 隱藏 secondary flows。
- **Task Signal:** `ACTIVE` IDs 只取 `state.agents` 中 `agent.active === true`（最多 15）；lifecycle count 只依五個 zone 計算；freshness/progress 直接取 task snapshot。
- **Runtime Signal:** source、visible/total IDs、working、blocked、attention 只依 runtime snapshot；visible agent 上限 15，總數與隱藏數保持 truthful。Runtime polling 為可見且有 active agent 約 30 秒、一般靜置約 60 秒、hidden 約 120 秒；Task polling 為可見約 60 秒、hidden 約 120 秒。
- **No phantom telemetry:** rail 不顯示 Runtime map 座標、猜測的依賴、mock 值或第二套狀態；視覺上的 bracket/grid 只是 decoration。

### Evidence rail

- **Style:** `rail` surface、18px padding；標題、說明與 DOM list 保持窄而安靜。
- **Items:** 每項以 1px top divider、10px vertical padding；只顯示可由目前 task snapshot 追溯的 blocked/freshness evidence。
- **States:** attention evidence 用 amber；沒有證據時顯示 muted empty state；不可用/過期時明示 `UNAVAILABLE` / `STALE`。

### Runtime constellation

- **Style:** 可選的 fixed drawer（桌面寬度 `min(420px, 30vw)`、最大不超過 520px，18px padding，5px radius）與獨立 generation list；最多顯示 15 agents，超量必須揭露 visible/total/hidden。
- **Map layer:** Runtime 節點是獨立 SVG/DOM overlay，依 lifecycle anchor 綁定到五個 territory：Intake `10`、In Progress `30`、Blocked `50`、Review `70`、Done `90`；同區節點以索引在 anchor 周圍分散。Unknown 沒有 anchor 時不繪製節點。cyan 表示一般節點，amber 僅表示 `requiresAttention`，不改寫 task layer。
- **Attention separation:** task plot 的 `taskAttentionSummary` 與 Runtime drawer 的 `runtimeAttentionSummary` 是兩個獨立訊號；Runtime attention 不得冒充 Task blocked，反之亦然。
- **Sources / fallback:** connected、replay、file、fallback、static 等來源要如實標示；disconnected、idle、stale 不得暗示完成。

### State and motion

- **Truthful state:** task 載入失敗時保留最後有效 snapshot 並標示 STALE；從未成功載入時顯示 UNAVAILABLE fallback。Runtime 失敗時維持 Task HUD 可用。
- **Motion:** agent hover/focus 約 180ms；Runtime map 節點位置約 280ms；背景 pointer parallax 約 700ms；far/mid/near 三層分別使用 bounded transform（Rainbow `-3px`、starfield `-6px`、mid `+12/+8px`、near `-7/-5px`），singularity effects 僅使用 reverse orbit、orbital trail、border edge flow 與 energy pulse。桌面 broadcast LTR 約 34s、footer ticker RTL 約 24s、vertical waterfalls 約 30s。active card 才使用 operation scan/edge/aura 三組獨立節奏；實際溢出的 task title 自動 bounded ping-pong marquee，無需互動觸發。
- **Reduced motion:** `prefers-reduced-motion: reduce` 時 transition/animation 壓至約 0.001ms，HUD shell 與 mission plot/evidence rail 的 edge flow 固定靜止，singularity-effects opacity 降到 `.38`；ticker 停止在靜態訊息、active card 僅保留靜態 aura/edge、operation scan 與 overflow title 停止，scroll behavior 回到 auto。
- **Responsive simplification:** `760px` 以下改為單欄、隱藏 desktop 雙層 telemetry rail 與次要高密度資訊，保留 plot、task state、evidence 與可操作 Runtime；`620px` 以下再隱藏拓撲/Runtime map 並執行既有 singularity load-shed。不要把隱藏的 rail 內容改成虛構的 mobile summary。
- **Mobile load-shed:** `620px` 以下 effects opacity 降到 `.44`，只保留 primary ring；secondary/tertiary ring、orbital trail 隱藏，geometry structure 降到 opacity `.28`，mid/near parallax 幅度縮至約 `+5/+3` 與 `-3/-2px`，Runtime map/topology 隱藏；ticker 改為滿寬、loop 36s，保留 task DOM 與 Runtime drawer。
- **Hidden load-shed:** 頁面 hidden 時由 JS 設定 `is-paused`，暫停所有 CSS animation、停止 pointer parallax 更新，並把 task/Runtime polling 降至約 120 秒；重新可見後立即 refresh 並恢復可見 cadence。
- **Polling:** 可見且有 active Runtime 約 30 秒，無 active Runtime 約 60 秒；Task 約 60 秒；hidden 時兩者約 120 秒。WebSocket event 仍即時，LOCAL/UTC clock 僅在頁面可見時更新。這是資料新鮮度與效能行為，不是裝飾語意。

### Accessibility

- 使用 semantic `header`、`main`、`section`、`article`、`aside`、`ul/li`、button 與 progressbar；task helper 有 keyboard tabindex、role 與包含 ID/title/state 的 aria-label。
- Runtime drawer 是可聚焦的 `role="region"`（`tabindex="-1"`），透過 `aria-labelledby` / `aria-describedby` 關聯標題、summary、attention 與 notice；展開時 Tab/Shift+Tab 被 containment 在 drawer 內，沒有可聚焦項目時 focus 回到 region。
- `state-notice`、`runtime-attention` 與 `runtime-notice` 使用 polite live region；關閉 drawer 支援 Close、Escape、focus restoration。
- 狀態不可只靠顏色：Blocked/attention/stale/unavailable 必須同時有文字；focus ring 不可移除。
- 維護時保留 `aria-hidden` 的裝飾背景、任務拓撲的可見性語意與 reduced-motion 規則。

### Generated material provenance

- Approved comp：`.impeccable/mocks/orbital-bridge-c.png`。它是方向參考，不是 runtime task truth；mock 裡的 ID、日期、數字、座標與依賴不可硬編碼。
- Fleet bridge primary：`skills/mission-center/assets/visual-hub/mission-fleet-bridge-background.webp`，對應 `mission-fleet-bridge-background.webp.json`；approved、`generated-background-plate`、generator `image_gen built-in`，generated `2026-08-24`。畫面構圖是多艘星艦向 upper-center 遠方目的地航行、行星位於 lower center，下方是 polished obsidian panoramic flagship window frame；無 UI、文字、logo、人像、水印、複製艦體或 product state。
- Fleet provenance：JSON 記錄 WebP SHA-256 `321FC5A4F79317CED834E0DD9096A39614A27928B4F7C50348D224A5D4CF3D61`、usage `Mission Center Rainbow Singularity fleet-and-bridge background`，並標示 `containsProductState: false`。這是目前 primary background 的唯一素材真相。
- Rainbow reference：`skills/mission-center/assets/visual-hub/cosmic-spectrum-rainbow.jpg`，對應 `cosmic-spectrum-rainbow.jpg.json`；approved 的 reference-derived-background，來源為 Chat Observatory repository `Gale0418/Chat-Observatory` 的 `assets/themes/cosmic-spectrum-rainbow.jpg`、ref `agent/chat-observatory-rename`。它現在只提供色彩/風格方向，HTML 不把它當 primary background。
- Rainbow provenance：JSON 記錄 source blob SHA `c37fbabf08c952d5e05b1ca502c7c6c28ea4c94a`、asset SHA-256 `783CCFD32E9417BE77CFE9770259DFF00741F5E9FEB725A6007FB42D36045106`，並明確標示 `containsProductState: false`。
- Bridge plate：`skills/mission-center/assets/visual-hub/mission-bridge-background.webp` 與 `mission-bridge-background.webp.json`；仍是 approved 的裝飾 depth support，現行 opacity `.06`。
- Starfield plate：`skills/mission-center/assets/visual-hub/mission-starfield.webp` 與 `mission-starfield.webp.json`；仍是 approved 的裝飾 depth support，現行 opacity `.1`。四種 raster 都不得承擔 task/runtime state；只有 fleet WebP 是目前主背景，Rainbow JPG 是色彩/風格參考。

## Do's and Don'ts

### Do:

- **Do** 讓任務 lifecycle、證據與 freshness 保持可追溯；即使視覺特效主導畫面，也使用 semantic DOM 作唯一內容真相。
- **Do** 以 `#000d17` 起始，使用 ink/slate 鏡面深色階與 1px 線承載彩譜光場。
- **Do** 以 cosmic spectrum 建立奇點能量，以 cyan 表示 telemetry、以 amber 表示真實 intervention；所有狀態都附文字。
- **Do** 只以真實 `agent.active === true` 啟動 active card 的 scan、emissive edge 與 aura，並讓 active treatment 與 Task/Runtime attention 維持不同語意。
- **Do** 讓 telemetry ticker 只播送真實 status/progress/tasks/blocked/freshness，並保留一份可讀 live announcement。
- **Do** 讓桌面 Task/Runtime telemetry rails 只讀真實 snapshot、zone count、visible/total 與 polling constants；以資訊密度服務操作掃描，而非製造第二套真相。
- **Do** 維持 Fleet Command Deck A 的透明階層：主 panel `.50/.58`、canvas 無不透明實色底、territory `.36`、一般 card `.66`、active card `.72`，讓 fleet backdrop 可見。
- **Do** 以 `BRIEFING / EXECUTION / HOLD / VERIFICATION / ARCHIVE` 作軍事 phase label，並保留 Intake / In Progress / Blocked / Review / Done 的 lifecycle 副標。
- **Do** 顯示 truthful LOCAL/UTC、Task/Runtime snapshot 與 polling；broadcast/doctrine 只標示 `FILE SNAPSHOT`、`READ ONLY`、`NO SENSOR FEED`。
- **Do** 在桌面保留 top LTR broadcast、bottom RTL telemetry 與雙側 vertical waterfalls；`<=760px` 隱藏 secondary flows。
- **Do** 只在標題真的溢出時啟動自動 bounded ping-pong marquee；reduced-motion 時保持靜止。
- **Do** 將 `skills/mission-center/assets/visual-hub/mission-fleet-bridge-background.webp` 視為 primary background：保留多艘遠航星艦、lower-center 行星與底部旗艦窗框的構圖意圖；其相鄰 `.webp.json` 是素材 provenance 的唯一 metadata 真相。
- **Do** 保留 4–6px corners、compact controls、mono metadata 與 responsive regrouping。
- **Do** 讓 Runtime 維持獨立、唯讀、預設收合，並保留 visible/total/hidden、stale/unavailable 的誠實揭露。
- **Do** 維持 Chat Observatory Rainbow JPG、bridge/starfield 與相鄰 provenance JSON 的來源鏈；修改素材前先更新對應 metadata。
- **Do** 在 hidden、reduced-motion 與 mobile 條件下執行既定降載，確保 overdrive 不犧牲可操作性。

### Don't:

- **Don't** 把 approved mock 的示例資料、座標、依賴、日期或計數當成產品資料。
- **Don't** 把 raster 背景、星點、glow、grid、ring、trail 或角色圖像用來傳達狀態或互動；operation scan 只屬於真實 active card。
- **Don't** 把 rainbow spectrum 當成 status legend；只有有文字的 semantic state 與 amber intervention 才能表達操作語意。
- **Don't** 以 status、Runtime agent、卡片位置或視覺亮度猜測 `agent.active`；active 必須來自 task snapshot。
- **Don't** 把 ticker 的重複副本、geometry rails、alignment brackets 或 parallax depth 當成額外任務、依賴或 telemetry source。
- **Don't** 複製 EVE trade dress、iconography、產品畫面或艦橋 UI；只借鑑高資訊密度的閱讀節奏。
- **Don't** 使用受保護的 EVA/EVE 名稱、logo、iconography 或 trade dress；EVA-inspired 只可作為高張力、資訊密度的閱讀節奏參考。
- **Don't** 把 doctrine、broadcast、waterfall、fleet backdrop 或幾何裝飾解讀成 sensor feed；不得造假座標、資料、時鐘、計數或 polling 狀態。
- **Don't** 為了填滿 rail 造假座標、任務數字、Runtime IDs、polling 狀態或 marquee；`<=760px` 隱藏次要資訊即可。
- **Don't** 把 `cosmic-spectrum-rainbow.jpg` 誤當目前 primary background，或把 fleet/planet/window-frame 圖像解讀成 product state。
- **Don't** 改成 generic SaaS 卡片牆、oversized pills、粗重陰影或純裝飾 dashboard。
- **Don't** 讓 Runtime 改寫 Task lifecycle，或把 idle、unknown、stale、disconnected 顯示成完成。
- **Don't** 移除鍵盤 focus、Escape/focus restoration、live region 或 reduced-motion 支援。
- **Don't** 展示 prompt、reasoning、完整 command、tool arguments、環境變數、token 或 secrets。
