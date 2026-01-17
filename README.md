# NovelOS 小说创作系统交付总结

## 一、系统概述

NovelOS 是一个基于 LangGraph 框架的专业小说创作辅助系统，通过 LLM 和工作流引擎实现从项目初始化到导出发布的全流程管理。

### 技术栈
- **工作流引擎**: LangGraph (Python 1.0)
- **数据库**: PostgreSQL + SQLAlchemy
- **数据验证**: Pydantic
- **大模型**: 豆包大模型 (doubao-seed-1-8-251228)

### 核心特性
- ✅ **意图路由系统**: 自动识别用户意图（新建/写作/改稿/检查/查询/审批/导出）
- ✅ **提案审批机制**: 新设定必须用户审批才能进入 Canon
- ✅ **一致性检查**: 生成 IssueList 和 PatchPlan，支持定位问题
- ✅ **版本化管理**: Snapshot + Events 双表结构，支持审计和回滚
- ✅ **上下文感知**: ContextPack 机制为每个场景提供相关人物、地点、规则

---

## 二、架构设计

### 2.1 数据库架构

采用 **Snapshot + Events 双表结构**：

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `novel_state_snapshot` | 存储 NovelState 最新完整快照 | `project_id`, `snapshot` (JSON), `version` |
| `state_events` | 记录所有状态变更事件 | `project_id`, `event_type`, `state_delta`, `chapter_ref`, `scene_ref` |

**关键约定**：
- 每个 `state_events` 记录包含 `linked_asset_version`，通过 `chapter_ref` + `version_after` 关联正文版本
- **回滚粒度**：回滚到特定版本时，需同时：
  1. 回滚 DB state 到对应事件的 `version_before`
  2. 将正文版本指针指向 `version_before` 对应的正文文件

### 2.2 资产目录结构

**实际实现**：采用 **章级文件存储**

```
assets/
└── {project_id}/
    └── chapter_{chapter_no}/
        ├── v1.md          # 第1版
        ├── v2.md          # 第2版
        └── ...
```

**说明**：
- 每个章节一个独立文件，按版本号存储（`v{version}.md`）
- `ChapterInfo` 维护 `scenes` 列表（场景ID顺序），但正文是章级合并存储
- **场景追踪**：通过 `StateEvent.scene_ref` + `StateDelta.scene_updates` 记录场景级变更

**导出策略**：
- 按章节号排序后，直接拼接各章的正文文件
- 插入标题层级：`# {书名}` 作为主标题，`## {章节标题}` 作为二级标题
- **文件规范**：UTF-8（无 BOM）+ LF 换行符

### 2.3 工作流架构

采用 **Router + 7个分支的 DAG 结构**：

```
用户输入
    ↓
意图识别节点 (intent_router)
    ↓
    ├─→ 新书创建: collect_project_info → generate_style_bible → init_novel_state → generate_outline → init_scene_queue → END
    ├─→ 场景写作: pick_scene → build_context_pack → draft_scene → commit_state → consistency_check → END
    ├─→ 改稿: select_revise_mode → generate_revise_plan → apply_revision → save_version → consistency_check → END
    ├─→ 一致性检查: consistency_check → END
    ├─→ 查询设定: query_setting → END
    ├─→ 提案审批: list_proposals → merge_proposals → END
    └─→ 导出: export → END
```

**关键约定 - 多轮修补机制**：
- 主图为 **无环图（DAG）**，单次执行只做 **一次一致性检查**
- **多轮修补** 通过 **外层 Orchestrator 重入图** 实现：
  1. 用户触发「一致性检查」→ 输出 IssueList + PatchPlan
  2. 用户触发「改稿」→ 应用修补计划 → 保存新版本
  3. 用户再次触发「一致性检查」→ 验证修补效果
- **不支持自动闭环修补**（避免无限循环），由用户主导多轮迭代

---

## 三、核心功能实现

### 3.1 意图路由 (Intent Router)

**实现位置**: `src/graphs/node.py:intent_router_node`

**功能**：分析用户输入，识别操作类型

| 意图类型 | 触发条件示例 | 路由分支 |
|---------|-------------|---------|
| new_project | "我要写一本玄幻小说" | 新书创建 |
| write_next | "写下一个场景" | 场景写作 |
| revise | "润色第3章" | 改稿 |
| check_consistency | "检查一致性" | 一致性检查 |
| query_setting | "查询主角信息" | 查询设定 |
| approve_proposals | "批准提案123" | 提案审批 |
| export | "导出全文" | 导出 |

**配置文件**: `config/intent_router_llm_cfg.json`

### 3.2 新书创建流程

**节点链**：
1. `collect_project_info`: 提取项目基本信息（标题、题材、受众等）
2. `generate_style_bible`: 生成写作宪法（文风约束）
3. `init_novel_state`: 创建初始 NovelState 并保存到 DB
4. `generate_outline`: 生成大纲节点（OutlineBeat）和初始场景卡（SceneCard）
5. `init_scene_queue`: 将场景卡加入队列，更新 NovelState

**关键数据结构**：
- `ProjectInfo`: 项目基本信息
- `StyleBible`: 写作宪法（voice、tone、pacing、taboos等）
- `OutlineBeat`: 大纲节点/幕结构
- `SceneCard`: 场景卡（objective、conflict、turning_point等）

### 3.3 场景写作流程

**节点链**：
1. `pick_scene`: 从场景队列中选择优先级最高的场景
2. `build_context_pack`: 构建上下文包（相关人物、地点、规则、时间线）
3. `draft_scene`: 生成场景正文内容（800-1500字）
4. `commit_state`: 提交状态增量，保存正文文件，记录事件
5. `consistency_check`: 检查一致性，生成 IssueList + PatchPlan

**ContextPack 机制**：
```python
class ContextPack(BaseModel):
    scene_card: SceneCard              # 场景卡
    relevant_characters: Dict[str, Entity]  # 相关人物
    location_info: Entity              # 地点信息
    timeline_context: List[TimelineEvent]  # 时间线上下文
    relevant_rules: Dict[str, CanonRule]  # 相关规则
    style_bible: StyleBible            # 写作宪法
    chapter_summary: str               # 章节摘要
```

**ConsistencyGate（一致性检查）**：
- 检查项：视角一致性、时间线矛盾、人物属性一致性、硬设定规则违规
- 输出：`IssueItem[]` + `PatchPlanItem[]`
- **段落定位策略**：
  - 当前版本使用 `where` 字段提供 **自然语言位置描述**（如"第3段开头"）
  - **建议增强**：为每个段落生成 `para_id`（UUID/哈希），实现精确到段落的稳定锚点
  - **Diff 对比**：使用前后文窗口 + 引用片段进行定位（类似代码 diff）

### 3.4 改稿流程

**节点链**：
1. `select_revise_mode`: 识别改稿模式
2. `generate_revise_plan`: 生成改稿计划
3. `apply_revision`: 应用改稿，生成新版本正文
4. `save_version`: 保存新版本，更新 NovelState
5. `consistency_check`: 验证修补效果

**改稿模式**：
- `polish`: 语句润色（不改剧情、不新增设定）
- `restructure`: 结构重写（允许重排段落、加强冲突，但不改关键事件）
- `plot_revision`: 剧情修订（允许改事件，需走提案流程）

**版本管理**：
- 每次改稿生成新版本文件：`v{new_version}.md`
- NovelState 中的 `current_version` 自动递增
- StateEvent 记录事件类型（`revise`）和前后版本号

### 3.5 提案审批流程

**节点链**：
1. `list_proposals`: 列出所有提案（待审批/已批准/已拒绝）
2. `merge_proposals`: 将批准的提案合并到 Canon，更新 NovelState

**ProposalPool 机制**：
```python
class Proposal(BaseModel):
    proposal_id: str
    proposal_type: Literal["new_entity", "new_rule", "new_location", "new_item", "other"]
    content: str                      # 提案内容
    rationale: str                    # 理由
    risks: List[str]                  # 风险点
    impact_analysis: str              # 影响分析
    affected_entities: List[str]      # 影响的实体
    status: Literal["pending", "approved", "rejected"]
    risk_level: Literal["low", "medium", "high"]
```

**CanonGate（设定拦截机制）**：
- **当前状态**：提案审批流程已实现，但正文生成后 **暂未自动检测新增设定**
- **建议增强**：实现 `CanonGate` 节点
  1. 正文生成后，自动检测是否有未批准的新增实体/设定引用
  2. 如果发现，自动抽取为 Proposal 并标记为 `pending`
  3. 阻断提交或要求重写
  4. 在 ContextPack 构建时，**仅包含已批准的设定**，并在 System Prompt 中明确"不得引用未批准设定"

### 3.6 查询设定流程

**节点**：`query_setting`

**功能**：从 NovelState 中查询人物、地点、规则、时间线等信息

**支持查询类型**：
- 人物详情（含属性、状态、关系）
- 地点信息
- 硬设定规则
- 时间线事件

### 3.7 导出流程

**节点**：`export`

**导出格式**：Markdown / TXT

**导出策略**：
1. 按章节号排序（`ChapterInfo.scenes` 中的场景ID顺序）
2. 读取每个章节的最新版本文件
3. 拼接为完整内容，插入标题层级
4. 保存为 `export.md` 或 `export.txt`

**文件规范**：
- 编码：UTF-8（无 BOM）
- 换行符：LF（Unix风格）
- 标题层级：`# {书名}`（主标题）+ `## {章节标题}`（二级标题）

---

## 四、数据流设计

### 4.1 NovelState 核心状态

```python
class NovelState(BaseModel):
    project_id: str                   # 项目唯一标识
    project: ProjectInfo              # 项目基本信息
    style: StyleBible                 # 写作宪法
    outline: List[OutlineBeat]        # 大纲节点
    chapters: Dict[str, ChapterInfo]  # 章节信息字典
    scene_queue: List[SceneCard]      # 待写场景队列
    world: WorldSetting               # 世界观设定（实体+规则）
    timeline: List[TimelineEvent]     # 时间线
    proposals: List[Proposal]         # 提案池
    change_log: List[ChangeLog]       # 变更日志
    current_version: int              # 当前版本号
    created_at: str                   # 创建时间
    updated_at: str                   # 更新时间
```

### 4.2 节点输入输出隔离

**规范**：每个节点定义独立的 `NodeInput` 和 `NodeOutput`

**示例**：
```python
class DraftSceneInput(BaseModel):
    context_pack: ContextPack
    style_bible: StyleBible

class DraftSceneOutput(BaseModel):
    content: str
    summary: SceneSummary
    state_delta: StateDelta
```

**数据流转**：
- 节点函数入参：`GlobalState`（LangGraph 自动合并所有节点输出）
- 节点内部：创建 `NodeInput` 对象，从 `GlobalState` 提取所需字段
- 节点输出：`NodeOutput` 对象，LangGraph 自动合并到 `GlobalState`

---

## 五、工程规范遵循

### 5.1 目录结构

```
├── config/                           # 配置目录
│   └── intent_router_llm_cfg.json    # 意图识别模型配置
├── src/
│   ├── agents/                       # Agent代码（初始为空）
│   ├── storage/
│   │   └── database/
│   │       ├── shared/               # 共享模型
│   │       ├── novel_models.py       # NovelState 数据库表定义
│   │       └── novel_manager.py      # NovelState 管理器
│   ├── graphs/
│   │   ├── state.py                  # 状态定义（GlobalState、NodeInput/Output）
│   │   ├── node.py                   # 节点函数实现
│   │   └── graph.py                  # 主图编排
│   ├── utils/                        # 业务封装（预先内置）
│   └── main.py                       # 运行入口（预先内置）
├── assets/                           # 资产目录
│   └── {project_id}/
│       └── chapter_{chapter_no}/
│           ├── v1.md
│           └── ...
└── requirements.txt                  # 依赖包
```

### 5.2 Import 规范

- ✅ 无 `src.` 前缀：`from graphs.state import ...`
- ✅ 环境变量 `COZE_WORKSPACE_PATH` 已加入 PYTHONPATH
- ✅ LangGraph 和 LangChain 使用 1.0 版本

### 5.3 节点函数规范

- ✅ 标准三参数签名：`(state: GlobalState, config: RunnableConfig, runtime: Runtime[Context])`
- ✅ 标准返回类型：`NodeOutput`
- ✅ 标准 Docstring：`title`、`desc`、`integrations`
- ✅ Agent 节点使用 Metadata 注入配置文件

### 5.4 状态定义规范

- ✅ 继承 `pydantic.BaseModel`
- ✅ 所有字段都有类型注解和 `Field(description="...")`
- ✅ 为每个节点定义独立的 `NodeInput` 和 `NodeOutput`
- ✅ 复杂类型使用嵌套 `BaseModel`
- ✅ 文件类型使用 `File` 类（当前未使用，因为采用本地文件路径）

### 5.5 图编排规范

- ✅ 主图为 DAG（无环图）
- ✅ 指定 `input_schema` 和 `output_schema`
- ✅ 使用 `add_node` 添加节点函数（无 lambda 包装）
- ✅ 使用 `add_conditional_edges` 添加条件分支
- ✅ 条件判断函数返回中文分支名
- ✅ 并行分支使用列表形式：`add_edge(["node1", "node2"], "merge_node")`

---

## 六、已解决的关键问题

### 6.1 节点函数类型不匹配

**问题**：节点函数期望独立的 `NodeInput`，但 LangGraph 传递 `GlobalState`

**解决**：
1. 修改所有节点函数签名为 `(state: GlobalState, ...)`
2. 在函数内部创建 `NodeInput` 对象，从 `GlobalState` 提取字段
3. 确保数据覆盖规则：下游节点的所有必填字段都能从上游或 GlobalState 中获取

### 6.2 GlobalState 导入错误

**问题**：节点函数使用 `GlobalState` 但未导入

**解决**：在 `node.py` 中导入 `GlobalState`

### 6.3 文件路径不一致

**问题**：文档中描述场景级目录，但代码实现为章级目录

**解决**：统一为章级目录结构：
```
assets/{project_id}/chapter_{chapter_no}/v{version}.md
```

---

## 七、待优化项

### 7.1 段落级定位锚点

**当前状态**：一致性检查使用自然语言位置描述

**建议增强**：
- 为每个段落生成 `para_id`（UUID 或内容哈希）
- 在正文存储时，记录段落索引（para_id, line_range, snippet）
- IssueItem 中使用 `para_id` 替代 `where` 字段，实现稳定定位

### 7.2 CanonGate 实现完整性

**当前状态**：提案审批流程已实现，但正文生成后未自动检测新增设定

**建议增强**：
- 在 `draft_scene_node` 后增加 `canon_gate_node`
- 检测新增实体/设定引用，自动生成 Proposal
- 在 `build_context_pack_node` 中过滤未批准设定
- 在 System Prompt 中明确禁止引用未批准设定

### 7.3 回滚功能实现

**当前状态**：数据库支持记录事件，但未实现回滚操作

**建议增强**：
- 实现 `rollback_node`，接受 `target_version` 参数
- 从 `state_events` 查找目标版本的事件
- 回滚 DB state 到 `version_before`
- 更新正文版本指针到对应的文件版本

### 7.4 场景级版本追踪

**当前状态**：采用章级文件存储，场景通过 StateEvent.scene_ref 追踪

**建议增强**：
- 考虑迁移到场景级目录结构：
  ```
  assets/{project_id}/chapter_{chapter_no}/scene_{scene_id}/v{version}.md
  ```
- 在导出时，根据 `ChapterInfo.scenes` 顺序拼接场景文件
- 更精确的场景级版本管理和问题定位

### 7.5 多语言支持

**当前状态**：所有提示词和输出均为中文

**建议增强**：
- 在 `StyleBible` 中增加 `language` 字段
- 支持多语言生成和导出

---

## 八、测试与验证

### 8.1 测试流程

1. **准备测试数据**：
   - 创建测试项目 ID
   - 生成测试用的用户输入

2. **执行测试**：
   ```bash
   python -m pytest src/tests/ -v
   ```

3. **验证数据流**：
   - 检查数据库快照是否正确保存
   - 检查正文文件是否正确生成
   - 检查事件日志是否正确记录

### 8.2 已知问题

- ✅ 已修复：节点函数类型不匹配
- ✅ 已修复：GlobalState 导入错误
- ⚠️ 待优化：段落级定位锚点
- ⚠️ 待优化：CanonGate 完整性
- ⚠️ 待优化：回滚功能实现

---

## 九、使用指南

### 9.1 创建新书

**用户输入**：
```
我要写一本玄幻小说，标题是《星辰变》，主角是一个少年，
背景是修仙世界，目标长度50万字。
```

**系统流程**：
1. 意图识别 → `new_project`
2. 收集项目信息 → 提取标题、题材等
3. 生成写作宪法 → 文风约束
4. 初始化 NovelState → 保存到数据库
5. 生成大纲 → OutlineBeat + SceneCard
6. 初始化场景队列 → SceneCard 加入队列

**输出**：
- 项目 ID：`novel_xxx`
- 初始场景队列：SceneCard 列表

### 9.2 场景写作

**用户输入**：
```
写下一个场景
```

**系统流程**：
1. 意图识别 → `write_next`
2. 选择场景 → 优先级最高的 SceneCard
3. 构建 ContextPack → 提取相关上下文
4. 起草场景 → 生成正文（800-1500字）
5. 提交状态 → 保存文件 + 记录事件
6. 一致性检查 → IssueList + PatchPlan

**输出**：
- 场景正文：`chapter_1/v1.md`
- 一致性报告：IssueList（如有问题）

### 9.3 改稿

**用户输入**：
```
润色第1章
```

**系统流程**：
1. 意图识别 → `revise`
2. 选择改稿模式 → `polish`
3. 生成改稿计划 → RevisePlanItem[]
4. 应用改稿 → 生成新版本
5. 保存版本 → `chapter_1/v2.md`
6. 一致性检查 → 验证修补效果

**输出**：
- 改后内容：`chapter_1/v2.md`
- 新版本号：`2`

### 9.4 查询设定

**用户输入**：
```
查询主角信息
```

**系统流程**：
1. 意图识别 → `query_setting`
2. 从 NovelState 中查询人物信息

**输出**：
- 人物详情（Entity 对象）

### 9.5 提案审批

**用户输入**：
```
批准提案 123
```

**系统流程**：
1. 意图识别 → `approve_proposals`
2. 列出提案 → 显示所有 pending 提案
3. 合并提案 → 更新 NovelState

**输出**：
- 提案状态更新为 `approved`
- Canon 设定更新

### 9.6 导出

**用户输入**：
```
导出全文为 Markdown
```

**系统流程**：
1. 意图识别 → `export`
2. 按章节顺序读取文件
3. 拼接完整内容
4. 保存为 `export.md`

**输出**：
- 导出文件路径：`assets/{project_id}/export.md`

---

## 十、总结

### 已完成功能

- ✅ 意图路由系统（7种意图类型）
- ✅ 新书创建流程（项目信息 + 写作宪法 + 大纲 + 场景队列）
- ✅ 场景写作流程（ContextPack + 生成 + 一致性检查）
- ✅ 改稿流程（3种改稿模式 + 版本管理）
- ✅ 提案审批流程（ProposalPool + Canon 合并）
- ✅ 查询设定流程（人物/地点/规则/时间线）
- ✅ 导出流程（Markdown/TXT）
- ✅ 数据库架构（Snapshot + Events 双表）
- ✅ 版本管理（版本号 + 事件日志）
- ✅ 资产目录（章级文件存储）
- ✅ 文件编码规范（UTF-8 无 BOM + LF）

### 核心亮点

1. **提案审批机制**：新设定必须用户审批才能进入 Canon
2. **一致性检查**：生成 IssueList + PatchPlan，支持问题定位
3. **版本化管理**：Snapshot + Events 双表结构，支持审计和回滚
4. **ContextPack 机制**：为每个场景提供精准的上下文
5. **DAG 工作流**：Router + 7个分支的清晰结构

### 后续优化方向

1. **段落级定位锚点**：实现 `para_id` 机制，精确到段落级别的稳定定位
2. **CanonGate 完整性**：正文生成后自动检测新增设定，生成 Proposal
3. **回滚功能实现**：支持回滚到任意历史版本（DB state + 正文文件）
4. **场景级版本追踪**：考虑迁移到场景级目录结构，提升精细化管理能力
5. **多语言支持**：支持多语言生成和导出

---

## 附录：关键文件清单

| 文件路径 | 说明 |
|---------|------|
| `src/graphs/state.py` | 状态定义（GlobalState、NodeInput/Output、数据模型） |
| `src/graphs/node.py` | 所有节点函数实现 |
| `src/graphs/graph.py` | 主图编排（Router + 7个分支） |
| `src/storage/database/novel_models.py` | 数据库表定义 |
| `src/storage/database/novel_manager.py` | 数据库管理器 |
| `config/intent_router_llm_cfg.json` | 意图识别模型配置 |

---
本地运行
运行流程
bash scripts/local_run.sh -m flow

运行节点
bash scripts/local_run.sh -m node -n node_name

启动HTTP服务
bash scripts/http_run.sh -m http -p 5000

**交付日期**: 2026-01-17
**版本**: v1.0.0
