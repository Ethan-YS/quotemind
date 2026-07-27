# QuoteMind — AI RFQ→Quotation Agent

> IndustrialMind.ai Solution Design Challenge · Option B 原型
> 场景：PrecisionMotion GmbH（虚拟客户）· 完整方案设计见 [docs/solution-design.md](docs/solution-design.md)
> 📝 中文工作稿 —— 定稿后整体替换为英文版

一条端到端的 AI 报价流水线：**客户 RFQ + 工程图纸 → 零件特征卡 → 相似件检索 → BOM 草稿 → 工艺路线草稿 → 成本分解 + 报价书草稿**。每个阶段都是一个人工审核门（human-in-the-loop）：工程师确认或修改后，下一阶段才会基于**修改后**的结果继续。

## 快速开始

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --port 8000
# 打开 http://localhost:8000
```

**零配置即可运行**：没有 API key 时自动进入 **demo mode**，回放内置样例（GS-4032 齿轮轴 RFQ）的预生成流水线输出，评审者无需任何配置就能走完全流程。

**Live mode**：`export GEMINI_API_KEY=...` 后重启即切换为真实 Gemini 调用（默认 `gemini-2.5-pro`，可用 `QUOTEMIND_MODEL` 覆盖）。

## 架构决策（为什么这么设计）

1. **每个阶段一个独立端点，而不是一次性跑完整条链。** 前端把"人审后（可能被修改过）"的阶段 N 输出传给阶段 N+1——HITL 不靠 UI 自觉，而是被 API 形状强制。这是制造业客户能信任 AI 的前提：判断权始终在工程师手里。
2. **相似件检索故意不用 LLM。** 工程相似性是"约束满足 + 邻近度"，结构化特征匹配是混合检索中最该先做对的通道：确定性、可解释（每个匹配都带理由）、离线可跑。生产版在此之上叠加 dense/sparse 语义通道（见方案 §3.3）。
3. **"几何双胞胎"排除名单。** 检索会显式列出几何近似但材料等级不同的零件（如钛合金试制轴）：几何可参考、成本不可迁移——这是报价估算最经典的坑，系统把它变成显式输出而不是默默排错或默默排对。
4. **每条 AI 产出都带依据（basis）与置信度。** BOM 行引用了哪个历史零件、工时按哪条产线校准、哪些字段必须人工确认——可追溯性优先于流畅性。
5. **模型无关抽象层。** 流水线不知道自己在 live 还是 demo mode；换 Gemini/Claude/本地开源模型只动 `llm.py` 一个文件。对德国客户，"可切换到 EU region / on-prem 部署"是签单前提，抽象层是架构的一等公民。
6. **Demo 缓存 = 真实模型输出的快照**，与内置零件库的历史成本互相校准（报价 €88.50 能从 BOM + 工时 + 费率逐行对出来），不是演示用的假数字。

## 样例输入 / 输出

- 输入：[samples/rfq_email.txt](samples/rfq_email.txt)（Nordwind 询价邮件，250 + 500 件/年）+ [samples/GS-4032_RevB.svg](samples/GS-4032_RevB.svg)(工程图纸，42CrMo4 花键齿轮轴)
- 中间输出：特征卡（含 3 个 review flag）→ Top-5 相似件（含钛合金排除项）→ 4 行 BOM → 8 工序 routing（含产线推荐：首批德国、量产评估波兰）
- 最终输出：双数量场景成本分解 + 报价书草稿（€88.50 / €79.90，7 周交付，零工装费——因为花键滚刀在库）

## 目录结构

```
backend/
  app.py                  # FastAPI —— 5 个阶段端点 + 静态文件
  pipeline/
    llm.py                # 模型抽象层（live Gemini / demo 缓存）
    drawing_agent.py      # ① 图纸理解 → 特征卡
    retrieval.py          # ② 相似件检索（结构化特征匹配，无 LLM）
    bom_agent.py          # ③ BOM 草稿
    process_agent.py      # ④ 工艺路线草稿
    quote_agent.py        # ⑤ 成本汇总 + 报价书
  data/
    parts_db.json         # 13 个历史零件（含成本/工艺实绩）
    demo_cache/           # demo mode 回放的流水线输出
frontend/                 # 审核工作台（英文 UI）
samples/                  # 样例 RFQ + 工程图纸
docs/solution-design.md   # Part 1-5 完整方案设计
```

## 已知边界（原型的诚实清单）

- 图纸理解只处理单张单视图图纸；多页 PDF / 装配图 / 手绘扫描件是生产版工程
- 零件库 13 条为手工构造的演示数据；生产版从 PLM/ERP 同步并做混合检索
- 成本费率与假设硬编码在 prompt 中；生产版从 ERP 主数据读取
- 无鉴权、无并发控制——这是一个 challenge 原型，不是产品
