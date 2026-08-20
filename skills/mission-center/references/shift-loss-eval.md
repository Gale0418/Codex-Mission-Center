# Shift-Loss Eval／Privacy-safe Self-Metrics

Shift-Loss evaluation只接受 bounded、structured summaries；它不接收 prompt、tool arguments、raw logs、commands 或 secrets，不會自行研究、不會修改 `tasks.md`／smoke evidence／memory，也不會把 synthetic fixture 當成實測。

每個 result 綁定 canonical `taskId` 與 versionable `variant`（例如 `baseline_v0_3`、`owo_v0_4`）。每個 case 必須明示 shouldRecall／shouldIgnore／shouldSupersede（至少一真）、actual 三種 action、firstCorrectActionMs、staleMemoryInjected、wrongBranch、tokensUsed、verifiedProgress、evidenceClaims／evidenceBackedClaims、falseDone、recoveryDistance、unverifiedDestructiveAction、activeGuardrailWithoutSource、multipleWritersSameBranch。

Aggregate metrics 定義如下：HRA＝所有 shouldRecall／shouldIgnore／shouldSupersede target 中相應 actual action 正確數／target 總數（同一 case 可有多個 target）；TFCA＝有值 `firstCorrectActionMs` 的平均；SMIR＝`staleMemoryInjected` count／case 總數；WBR＝`wrongBranch` count／case 總數；TVP＝`tokensUsed` 總和／`verifiedProgress: true` case 數；EvidenceCoverage＝evidenceBackedClaims／evidenceClaims；FalseDone＝`falseDone` count；RecoveryDistance＝有值案例的平均 recoveryDistance。任何分母為零都輸出 `null`，不偽造 0。

四項 hard constraints 優先於平均指標：FalseDone、unverified destructive action、active guardrail without source、multiple writers same branch 都必須是 0；任一違反即 `failed_hard_constraint`。Baseline／new paired comparison 只對相同 caseId 計算 current−baseline delta；缺 case 會標示 `incomplete_paired_cases`。delta 不是 improvement claim，且不同方向（例如時間／錯誤率越低越好、coverage 越高越好）不可混成單一分數。

```bash
python skills/mission-center/scripts/shift_loss_eval.py evaluate result.json --workspace .
python skills/mission-center/scripts/shift_loss_eval.py compare baseline.json owo.json --workspace .
```
