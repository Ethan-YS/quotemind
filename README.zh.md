# QuoteMind — AI RFQ→Quotation Agent

> IndustrialMind.ai Solution Design Challenge · Option B 原型
> 场景：PrecisionMotion GmbH（虚拟客户）· 完整方案设计见 [docs/solution-design.zh.md](docs/solution-design.zh.md)
> English: [README.md](README.md)

一条端到端的 AI 报价流水线：**客户 RFQ + 工程图纸 → 零件特征卡 → 相似件检索 → BOM 草稿 → 工艺路线草稿 → 成本分解 + 报价书草稿**。每个阶段都是一个人工审核门（human-in-the-loop）：工程师确认或修改后，下一阶段才会基于**修改后**的结果继续。

## 快速开始

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --port 8000
# 打开 http://localhost:8000
```

**无需 API key 或模型配置**：安装依赖并启动服务后，未配置任何后端时自动进入 **demo mode**，回放内置样例（GS-4032 齿轮轴 RFQ）的预生成流水线输出，评审者无需任何配置就能走完全流程。

**Live 后端（二选一）**：

| 后端 | 启用方式 | 说明 |
|---|---|---|
| Gemini API | `export GEMINI_API_KEY=...` | 默认 `gemini-2.5-pro`，`QUOTEMIND_MODEL` 可覆盖 |
| Claude CLI | `QUOTEMIND_BACKEND=claude-cli` | shell 到本地已登录的 Claude Code（`claude -p` 无头模式），**代码库不接触任何 API key** |
| Codex CLI | `QUOTEMIND_BACKEND=codex-cli` | 同理走 `codex exec`（含 `-i` 图纸视觉输入），模型 `QUOTEMIND_CODEX_MODEL`（默认 gpt-5.5） |

重新生成 demo 缓存：`QUOTEMIND_BACKEND=codex-cli python scripts/regen_demo_cache.py`（四阶段输出先过 schema 校验再落盘，失败保留旧缓存）。

## 架构决策（为什么这么设计）

1. **每个阶段一个独立端点，而不是一次性跑完整条链。** 前端把"人审后（可能被修改过）"的阶段 N 输出传给阶段 N+1——HITL 不靠 UI 自觉，而是被 API 形状强制。这是制造业客户能信任 AI 的前提：判断权始终在工程师手里。
2. **相似件检索故意不用 LLM。** 工程相似性是"约束满足 + 邻近度"，结构化特征匹配是混合检索中最该先做对的通道：确定性、可解释（每个匹配都带理由）、离线可跑。生产版在此之上叠加 dense/sparse 语义通道（见方案 §3.3）。
3. **"几何双胞胎"排除名单。** 检索会显式列出几何近似但材料等级不同的零件（如钛合金试制轴）：几何可参考、成本不可迁移——这是报价估算最经典的坑，系统把它变成显式输出而不是默默排错或默默排对。
4. **检索结果可被工程师否决（HITL 的最硬处）。** 算法只知道特征像不像，不知道"那批活当年热处理炉出过问题""那单是为拿客户亏本报的"——这些只在人脑子里。所以每条匹配都能被排除，且**必须写明理由**；被排除的参考件不进入 OP 40 的成本校准，理由随报价单归档（OP 50「工程师决策」面板）。这一步不是让人改数字，是让人**否决 AI 的证据基础**——检索恰恰是领域知识打败算法的地方。
5. **特征卡有规则校验，不是只让人肉眼看。** 材料牌号在特征卡内部必须自洽——改了主材料却漏改"关键要求"里那句，系统会指名道姓标出矛盾条目并**拦截签发**；但它不假装自己判得准：合法差异（配对件、镀层、供应商备注）可由工程师「确认无冲突」放行，该确认进入决策归档。架构图里的"规则校验"节点在代码里是有实现的。
6. **OP 40 让工程师改的是“方案”而不只是“数字”。** 可增删 BOM 行与工序（AI 多排的划掉、漏排的补上，被删的不进入核价），合计随编辑实时重算——修改的后果当场可见；**低置信工序必须逐条确认才能放行**（方案 §3.4 写的“低置信→强制人工介入”，这里是它的实现而不是承诺）。所有增删与确认都进入 OP 50 的「工程师决策」归档。
7. **OP 50 是商务决策，不是只读汇总。** 毛利与售价**双向联动**（改哪个另一个跟随，成本由 OP 40 结转、只读）——按成本加成报价和按目标价倒推毛利，工厂两种都要用；工装、交期、假设与风险均可编辑增补。**报价信与成本表不一致时强制拦截签发**并提供一键同步：报价信写 €98.69、成本表写 €90.56 的报价单，绝不能发出公司。
8. **每条 AI 产出都带依据（basis）与置信度。** BOM 行引用了哪个历史零件、工时按哪条产线校准、哪些字段必须人工确认——可追溯性优先于流畅性。工程师的每次修正都被记录并计数（审批栏实时显示"已修正 N 处"），修正值传入下一阶段——这就是生产版"人工修正回流为评测集"的雏形。
9. **模型无关抽象层。** 流水线不知道自己在 live 还是 demo mode；换 Gemini/Claude/本地开源模型只动 `llm.py` 一个文件。对德国客户，"可切换到 EU region / on-prem 部署"是签单前提，抽象层是架构的一等公民。
10. **Demo 缓存 = 真实模型输出的快照**：由 codex-cli 后端（gpt-5.5）通过 `scripts/regen_demo_cache.py` 真实跑一遍流水线生成，四阶段输出过 schema 校验后落盘。每条成本都锚定零件库参考件实绩（basis 字段可逐行核对），不是演示用的假数字。

## 样例输入 / 输出

- 输入：[samples/rfq_email.txt](samples/rfq_email.txt)（Nordwind 询价邮件，250 + 500 件/年）+ [samples/GS-4032_RevB.svg](samples/GS-4032_RevB.svg)(工程图纸，42CrMo4 花键齿轮轴)
- 中间输出：特征卡（13 项特征 + review flags）→ Top-5 相似件（top 命中 PM-SH-1998，99.4 分；钛合金几何双胞胎显式排除）→ 9 行作业级 BOM → 12 工序 routing（模型自行补入"淬火后校直"工序并标注低置信——正是 HITL 要人看的地方）
- 最终输出：双数量场景成本分解 + 报价书草稿（€98.69 / €97.38，8 周交付，零工装费——因为 W30×1.5 花键滚刀在库）

## 真实与回放的边界（What's real vs replayed）

| 环节 | demo mode | live mode（任一后端） |
|---|---|---|
| 相似件检索 + 几何双胞胎排除 | ✅ 真实运行（确定性代码，永不回放） | ✅ 真实运行 |
| 四个 LLM 阶段（图纸/BOM/工艺/报价） | 回放缓存（缓存本身是 live 真跑的快照） | ✅ 真实调用 |
| HITL 数据流（人审后的 JSON 传入下一阶段） | ✅ 真实传递，但回放输出不会基于修改重算 | ✅ 修改真实影响下游结果 |
| 生产环境模型与系统 | — | 见方案文档 §3.2（模型可切换，EU region / on-prem） |

## 目录结构

```
backend/
  app.py                  # FastAPI —— 5 个阶段端点 + 静态文件
  pipeline/
    llm.py                # 模型抽象层（gemini / claude-cli / codex-cli / demo 缓存）
    drawing_agent.py      # ① 图纸理解 → 特征卡
    retrieval.py          # ② 相似件检索（结构化特征匹配，无 LLM）
    bom_agent.py          # ③ BOM 草稿
    process_agent.py      # ④ 工艺路线草稿
    quote_agent.py        # ⑤ 成本汇总 + 报价书
  data/
    parts_db.json         # 13 个历史零件（含成本/工艺实绩）
    demo_cache/           # demo mode 回放的流水线输出
  scripts/regen_demo_cache.py  # 用 live 后端真跑一遍并校验后写缓存
frontend/                 # 审核工作台（英文 UI，可切中文）
samples/                  # 样例 RFQ + 工程图纸
docs/solution-design.md   # Part 1-5 完整方案设计（英文版为正式交付）
```

## 已知边界（原型的诚实清单）

- 图纸理解只处理单张单视图图纸；多页 PDF / 装配图 / 手绘扫描件是生产版工程
- demo mode 下编辑蓝色值会真实传入下一阶段请求，但 LLM 阶段回放的答案不重算——**界面在这三个阶段会明确声明这一点**（检索是确定性代码，永远真算，修正立刻反映在评分与成本可迁移性上）
- OP 10 支持上传自有图纸（PNG/JPG）+ 直接编辑 RFQ 文本，仅 live 后端可用；demo mode 锁定内置样例并明示原因
- 撤销栈 / 修改历史面板 / 字段级 schema 校验是生产版工程，原型只做了数字字段的非法输入回退
- 零件库 13 条为手工构造的演示数据；生产版从 PLM/ERP 同步并做混合检索
- 成本费率与假设硬编码在 prompt 中；生产版从 ERP 主数据读取
- 无鉴权、无并发控制——这是一个 challenge 原型，不是产品
