# Optimization Routing

Route with `mission_optimizer.py profile` and `route`. Record the reason, missing evidence, risk, and budget before selecting a method.

| Condition | Strategy |
| --- | --- |
| Few discrete alternatives | Trade study and scenario stress test |
| Many factors, early screening | Screening DOE |
| High noise | Robust DOE or Taguchi design |
| Few expensive black-box numeric parameters | Bayesian Optimization |
| Mixed or categorical parameters | TPE |
| Multiple objectives | Pareto analysis; NSGA-II only when sample budget supports it |
| Continuous and differentiable | Gradient method |
| No repeatable metric | `research_spike`; do not assign a numerical optimizer |

Hard constraints outrank scores. Prefer `decision` for reversible low-risk choices, `hybrid` when judgment and measurements both matter, and `experimental` only when measurements, budgets, and stopping rules are explicit. Retrieval may use only cases recorded in the current repository.
