"""
NovelOS 数据结构定义
包含工作流的全局状态、输入输出定义，以及所有节点的输入输出数据模型
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ==================== 核心数据模型 ====================

class ProjectInfo(BaseModel):
    """项目基本信息"""
    title: str = Field(..., description="小说标题")
    genre: str = Field(..., description="题材（如：玄幻/科幻/言情/悬疑等）")
    target_audience: str = Field(default="大众", description="目标受众")
    target_length: int = Field(default=200000, description="目标字数")
    narrative_perspective: str = Field(default="第三人称", description="叙事视角（第一人称/第三人称）")
    tenses: str = Field(default="过去时", description="时态（过去时/现在时）")


class StyleBible(BaseModel):
    """写作宪法（文风约束）"""
    voice: str = Field(default="", description="语气风格")
    tone: str = Field(default="", description="基调")
    pacing: str = Field(default="", description="节奏控制")
    taboos: List[str] = Field(default=[], description="禁忌内容列表")
    dialogue_style: str = Field(default="", description="对话风格")
    description_style: str = Field(default="", description="描写风格")


class Entity(BaseModel):
    """实体基类（人物/地点/物品/势力）"""
    entity_id: str = Field(..., description="实体唯一ID")
    name: str = Field(..., description="名称")
    type: Literal["character", "location", "item", "faction"] = Field(..., description="实体类型")
    description: str = Field(default="", description="描述")
    attributes: Dict[str, Any] = Field(default={}, description="属性字典（年龄、外貌、性格等）")
    status: Dict[str, Any] = Field(default={}, description="当前状态（受伤、位置、持有物品等）")
    relationships: Dict[str, str] = Field(default={}, description="关系字典（key: 实体ID, value: 关系描述）")


class CanonRule(BaseModel):
    """硬设定规则"""
    rule_id: str = Field(..., description="规则ID")
    rule_type: Literal["setting", "logic", "power", "other"] = Field(..., description="规则类型")
    content: str = Field(..., description="规则内容")
    constraints: List[str] = Field(default=[], description="约束条件列表")


class OutlineBeat(BaseModel):
    """大纲节点/幕结构"""
    beat_id: str = Field(..., description="节点ID")
    title: str = Field(..., description="节点标题")
    description: str = Field(..., description="节点描述")
    act: str = Field(default="", description="所属幕（第一幕/第二幕/第三幕等）")
    sequence: int = Field(..., description="序号")
    estimated_chapters: int = Field(default=1, description="预计章节数")


class SceneCard(BaseModel):
    """场景卡"""
    scene_id: str = Field(..., description="场景唯一ID")
    chapter_ref: str = Field(..., description="所属章节号")
    sequence_in_chapter: int = Field(..., description="章节内序号")
    objective: str = Field(..., description="场景目标（角色想要什么）")
    conflict: str = Field(..., description="冲突（阻碍是什么）")
    turning_point: str = Field(default="", description="转折（信息/行动变化点）")
    result: str = Field(default="", description="结果（场景结束时状态）")
    characters: List[str] = Field(default=[], description="出场人物ID列表")
    location: str = Field(..., description="地点ID或名称")
    time_point: str = Field(..., description="时间点")
    foreshadowing: List[str] = Field(default=[], description="伏笔列表")
    style_markers: Dict[str, Any] = Field(default={}, description="风格标记（节奏、对话密度等）")
    priority: int = Field(default=0, description="优先级（数字越大越优先）")
    status: Literal["pending", "drafted", "completed"] = Field(default="pending", description="状态")


class ChapterInfo(BaseModel):
    """章节信息"""
    chapter_no: str = Field(..., description="章节号")
    title: str = Field(..., description="章节标题")
    summary: str = Field(default="", description="章节摘要")
    completion_rate: float = Field(default=0.0, description="完成度（0.0-1.0）")
    current_version: int = Field(default=0, description="当前版本号")
    scenes: List[str] = Field(default=[], description="包含的场景ID列表")
    file_path: Optional[str] = Field(default=None, description="正文文件路径（相对assets路径）")


class TimelineEvent(BaseModel):
    """时间线事件"""
    event_id: str = Field(..., description="事件ID")
    time_point: str = Field(..., description="时间点")
    description: str = Field(..., description="事件描述")
    involved_entities: List[str] = Field(default=[], description="涉及实体ID列表")
    chapter_ref: Optional[str] = Field(default=None, description="关联章节")
    scene_ref: Optional[str] = Field(default=None, description="关联场景")


class Proposal(BaseModel):
    """新设定提案"""
    proposal_id: str = Field(..., description="提案ID")
    proposal_type: Literal["new_entity", "new_rule", "new_location", "new_item", "other"] = Field(..., description="提案类型")
    content: str = Field(..., description="提案内容")
    rationale: str = Field(..., description="理由（对剧情的好处）")
    risks: List[str] = Field(default=[], description="风险点")
    impact_analysis: str = Field(default="", description="影响分析")
    affected_entities: List[str] = Field(default=[], description="影响哪些实体/规则")
    status: Literal["pending", "approved", "rejected"] = Field(default="pending", description="状态")
    risk_level: Literal["low", "medium", "high"] = Field(default="medium", description="风险等级")
    created_at: str = Field(default="", description="创建时间")


class StateDelta(BaseModel):
    """状态增量（单次提交的变更）"""
    entities_updated: Dict[str, Dict[str, Any]] = Field(default={}, description="实体状态变更")
    new_events: List[TimelineEvent] = Field(default=[], description="新增时间线事件")
    new_proposals: List[Proposal] = Field(default=[], description="新增提案")
    chapter_updates: Dict[str, Dict[str, Any]] = Field(default={}, description="章节信息更新")
    scene_updates: List[str] = Field(default=[], description="场景状态更新（scene_id列表）")


class ChangeLog(BaseModel):
    """变更日志"""
    log_id: str = Field(..., description="日志ID")
    version: int = Field(..., description="版本号")
    timestamp: str = Field(..., description="时间戳")
    event_type: str = Field(..., description="事件类型")
    delta: StateDelta = Field(..., description="状态增量")
    chapter_ref: Optional[str] = Field(default=None, description="关联章节")
    scene_ref: Optional[str] = Field(default=None, description="关联场景")
    description: str = Field(..., description="描述")


class WorldSetting(BaseModel):
    """世界观设定"""
    entities: Dict[str, Entity] = Field(default={}, description="人物/地点/物品/势力集合")
    canon_rules: Dict[str, CanonRule] = Field(default={}, description="硬设定规则")


# ==================== NovelState 核心状态 ====================

class NovelState(BaseModel):
    """NovelOS 全局状态"""
    project_id: str = Field(..., description="项目唯一标识")
    project: ProjectInfo = Field(..., description="项目基本信息")
    style: StyleBible = Field(default_factory=StyleBible, description="写作宪法")
    outline: List[OutlineBeat] = Field(default=[], description="大纲节点/幕结构")
    chapters: Dict[str, ChapterInfo] = Field(default={}, description="章节信息字典（key: chapter_no）")
    scene_queue: List[SceneCard] = Field(default=[], description="待写场景卡队列")
    world: WorldSetting = Field(default_factory=WorldSetting, description="世界观设定")
    timeline: List[TimelineEvent] = Field(default=[], description="时间线事件")
    proposals: List[Proposal] = Field(default=[], description="新设定提案池")
    change_log: List[ChangeLog] = Field(default=[], description="变更日志")
    current_version: int = Field(default=1, description="当前版本号")
    created_at: str = Field(default="", description="创建时间")
    updated_at: str = Field(default="", description="更新时间")


# ==================== 工作流输入输出 ====================

class GraphInput(BaseModel):
    """工作流输入"""
    user_input: str = Field(..., description="用户输入文本")
    project_id: Optional[str] = Field(default=None, description="项目ID（可选，已有项目时提供）")

# GraphOutput 将在 GlobalState 之后定义，因为它引用了 IssueItem


# ==================== 节点输入输出定义 ====================

# === 意图识别节点 ===
class IntentRouterInput(BaseModel):
    """意图识别节点输入"""
    user_input: str = Field(..., description="用户输入文本")
    project_id: Optional[str] = Field(default=None, description="项目ID")


class IntentRouterOutput(BaseModel):
    """意图识别节点输出"""
    intent: str = Field(..., description="识别到的意图类型")
    confidence: float = Field(default=0.0, description="置信度")
    parameters: Dict[str, Any] = Field(default={}, description="提取的参数")
    project_exists: bool = Field(default=False, description="项目是否存在")
    novel_state: Optional[NovelState] = Field(default=None, description="加载的NovelState（如果项目存在）")


# === 新书创建流程节点 ===

class CollectProjectInfoInput(BaseModel):
    """收集项目信息节点输入"""
    user_input: str = Field(..., description="用户输入")


class CollectProjectInfoOutput(BaseModel):
    """收集项目信息节点输出"""
    project_info: ProjectInfo = Field(..., description="项目基本信息")


class GenerateStyleBibleInput(BaseModel):
    """生成写作宪法节点输入"""
    project_info: ProjectInfo = Field(..., description="项目基本信息")


class GenerateStyleBibleOutput(BaseModel):
    """生成写作宪法节点输出"""
    style_bible: StyleBible = Field(..., description="写作宪法")


class InitNovelStateInput(BaseModel):
    """初始化NovelState节点输入"""
    project_info: ProjectInfo = Field(..., description="项目基本信息")
    style_bible: StyleBible = Field(..., description="写作宪法")


class InitNovelStateOutput(BaseModel):
    """初始化NovelState节点输出"""
    novel_state: Optional[NovelState] = Field(None, description="初始NovelState")


class GenerateOutlineInput(BaseModel):
    """生成大纲节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")


class GenerateOutlineOutput(BaseModel):
    """生成大纲节点输出"""
    outline: List[OutlineBeat] = Field(..., description="大纲节点列表")
    initial_scenes: List[SceneCard] = Field(default=[], description="初始场景卡")


class InitSceneQueueInput(BaseModel):
    """初始化场景队列节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    initial_scenes: List[SceneCard] = Field(default=[], description="初始场景卡")


class InitSceneQueueOutput(BaseModel):
    """初始化场景队列节点输出"""
    scene_queue: List[SceneCard] = Field(..., description="场景队列")
    novel_state: Optional[NovelState] = Field(None, description="更新后的NovelState")


# === 场景写作流程节点 ===

class PickSceneInput(BaseModel):
    """选择场景节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    user_override: Optional[Dict[str, Any]] = Field(default=None, description="用户覆盖参数")


class PickSceneOutput(BaseModel):
    """选择场景节点输出"""
    scene_card: SceneCard = Field(..., description="选中的场景卡")


class BuildContextPackInput(BaseModel):
    """构建Context Pack节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    scene_card: SceneCard = Field(..., description="场景卡")


class ContextPack(BaseModel):
    """上下文包"""
    scene_card: SceneCard = Field(..., description="场景卡")
    relevant_characters: Dict[str, Entity] = Field(default={}, description="相关人物")
    location_info: Optional[Entity] = Field(default=None, description="地点信息")
    timeline_context: List[TimelineEvent] = Field(default=[], description="时间线上下文")
    relevant_rules: Dict[str, CanonRule] = Field(default={}, description="相关规则")
    style_bible: StyleBible = Field(..., description="文风约束")
    chapter_summary: str = Field(default="", description="章节摘要")


class BuildContextPackOutput(BaseModel):
    """构建Context Pack节点输出"""
    context_pack: ContextPack = Field(..., description="上下文包")


class DraftSceneInput(BaseModel):
    """起草场景节点输入"""
    context_pack: ContextPack = Field(..., description="上下文包")


class SceneSummary(BaseModel):
    """场景摘要"""
    content: str = Field(..., description="摘要内容（100-200字）")
    key_points: List[str] = Field(default=[], description="关键点")


class DraftSceneOutput(BaseModel):
    """起草场景节点输出"""
    content: str = Field(..., description="场景正文内容")
    summary: SceneSummary = Field(..., description="场景摘要")
    state_delta: StateDelta = Field(..., description="状态增量")
    scene_id: str = Field(..., description="场景ID")
    chapter_no: str = Field(..., description="章节号")


class CommitStateInput(BaseModel):
    """提交状态节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="当前NovelState")
    state_delta: StateDelta = Field(..., description="状态增量")
    scene_id: str = Field(..., description="场景ID")
    chapter_no: str = Field(..., description="章节号")
    content: str = Field(..., description="正文内容")


class CommitStateOutput(BaseModel):
    """提交状态节点输出"""
    novel_state: Optional[NovelState] = Field(None, description="更新后的NovelState")
    event_id: str = Field(..., description="事件ID")
    file_path: str = Field(..., description="保存的文件路径")


# === 一致性检查节点 ===

class ConsistencyCheckInput(BaseModel):
    """一致性检查节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    content: Optional[str] = Field(default=None, description="待检查内容")
    chapter_no: Optional[str] = Field(default=None, description="章节号")
    scene_id: Optional[str] = Field(default=None, description="场景ID")


class IssueItem(BaseModel):
    """问题项"""
    severity: Literal["blocker", "warn", "info"] = Field(..., description="严重程度")
    where: str = Field(..., description="位置（chapter/scene/段落索引或引用片段）")
    why: str = Field(..., description="违反的规则/设定")
    fix_suggestion: str = Field(..., description="修复建议")
    rule_ref: Optional[str] = Field(default=None, description="引用的规则ID")


class PatchPlanItem(BaseModel):
    """修补计划项"""
    target: str = Field(..., description="目标位置")
    action: Literal["replace", "delete", "insert"] = Field(..., description="操作类型")
    content: str = Field(..., description="内容")
    rationale: str = Field(..., description="理由")


class ConsistencyCheckOutput(BaseModel):
    """一致性检查节点输出"""
    issues: List[IssueItem] = Field(..., description="问题列表")
    patch_plan: List[PatchPlanItem] = Field(default=[], description="修补计划")
    passed: bool = Field(default=True, description="是否通过检查")


# === 改稿流程节点 ===

class SelectReviseModeInput(BaseModel):
    """选择改稿模式节点输入"""
    user_input: str = Field(..., description="用户输入")


class SelectReviseModeOutput(BaseModel):
    """选择改稿模式节点输出"""
    mode: Literal["polish", "restructure", "plot_revision"] = Field(..., description="改稿模式")
    target_chapter: Optional[str] = Field(default=None, description="目标章节号")
    target_scene: Optional[str] = Field(default=None, description="目标场景ID")


class GenerateRevisePlanInput(BaseModel):
    """生成改稿计划节点输入"""
    mode: Literal["polish", "restructure", "plot_revision"] = Field(..., description="改稿模式")
    content: str = Field(..., description="待改稿内容")
    issues: List[IssueItem] = Field(default=[], description="问题列表")


class RevisePlanItem(BaseModel):
    """改稿计划项"""
    location: str = Field(..., description="位置")
    action: str = Field(..., description="操作描述")
    rationale: str = Field(..., description="理由")


class GenerateRevisePlanOutput(BaseModel):
    """生成改稿计划节点输出"""
    plan: List[RevisePlanItem] = Field(..., description="改稿计划")


class ApplyRevisionInput(BaseModel):
    """应用改稿节点输入"""
    plan: List[RevisePlanItem] = Field(..., description="改稿计划")
    original_content: str = Field(..., description="原文内容")
    mode: Literal["polish", "restructure", "plot_revision"] = Field(..., description="改稿模式")


class ApplyRevisionOutput(BaseModel):
    """应用改稿节点输出"""
    revised_content: str = Field(..., description="改后内容")
    diff_summary: str = Field(..., description="差异摘要")


class SaveVersionInput(BaseModel):
    """保存版本节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    chapter_no: str = Field(..., description="章节号")
    content: str = Field(..., description="正文内容")
    event_type: str = Field(..., description="事件类型")


class SaveVersionOutput(BaseModel):
    """保存版本节点输出"""
    novel_state: Optional[NovelState] = Field(None, description="更新后的NovelState")
    file_path: str = Field(..., description="文件路径")
    new_version: int = Field(..., description="新版本号")


# === 提案审批流程节点 ===

class ListProposalsInput(BaseModel):
    """列提案节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")


class ListProposalsOutput(BaseModel):
    """列提案节点输出"""
    pending_proposals: List[Proposal] = Field(..., description="待审批提案列表")
    approved_proposals: List[Proposal] = Field(default=[], description="已批准提案列表")
    rejected_proposals: List[Proposal] = Field(default=[], description="已拒绝提案列表")


class MergeProposalsInput(BaseModel):
    """合并提案节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    proposal_ids: List[str] = Field(..., description="要合并的提案ID列表")


class MergeProposalsOutput(BaseModel):
    """合并提案节点输出"""
    novel_state: Optional[NovelState] = Field(None, description="更新后的NovelState")
    merged_count: int = Field(..., description="合并数量")


# === 查询设定流程节点 ===

class QuerySettingInput(BaseModel):
    """查询设定节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    query: Optional[str] = Field(default=None, description="查询内容")


class QuerySettingOutput(BaseModel):
    """查询设定节点输出"""
    results: List[Dict[str, Any]] = Field(..., description="查询结果列表")


# === 导出流程节点 ===

class ExportInput(BaseModel):
    """导出节点输入"""
    novel_state: Optional[NovelState] = Field(None, description="NovelState")
    format: Literal["markdown", "txt", "docx"] = Field(default="markdown", description="导出格式")


class ExportOutput(BaseModel):
    """导出节点输出"""
    output_path: str = Field(..., description="输出文件路径")
    success: bool = Field(default=True, description="是否成功")


# ==================== 全局状态 ====================

class GlobalState(BaseModel):
    """工作流全局状态"""
    # === 工作流输入输出 ===
    user_input: str = Field(..., description="用户输入")
    project_id: Optional[str] = Field(default=None, description="项目ID")
    novel_state: Optional[NovelState] = Field(default=None, description="NovelState")
    result: str = Field(default="", description="执行结果描述")
    issues: List[IssueItem] = Field(default=[], description="一致性问题列表")
    proposals: List[Proposal] = Field(default=[], description="待审批提案列表")
    output_files: List[str] = Field(default=[], description="输出文件路径列表")
    
    # === 意图识别 ===
    intent: str = Field(default="", description="识别到的意图")
    confidence: float = Field(default=0.0, description="意图置信度")
    parameters: Dict[str, Any] = Field(default={}, description="意图参数")
    project_exists: bool = Field(default=False, description="项目是否存在")
    
    # === 新书创建流程 ===
    project_info: Optional[ProjectInfo] = Field(default=None, description="项目基本信息")
    style_bible: Optional[StyleBible] = Field(default=None, description="写作宪法")
    outline: Optional[List[OutlineBeat]] = Field(default=None, description="大纲节点列表")
    initial_scenes: Optional[List[SceneCard]] = Field(default=None, description="初始场景卡")
    scene_queue: Optional[List[SceneCard]] = Field(default=None, description="场景队列")
    
    # === 场景写作流程 ===
    user_override: Optional[Dict[str, Any]] = Field(default=None, description="用户覆盖参数")
    scene_card: Optional[SceneCard] = Field(default=None, description="选中的场景卡")
    context_pack: Optional[ContextPack] = Field(default=None, description="上下文包")
    content: Optional[str] = Field(default=None, description="场景正文内容")
    chapter_no: Optional[str] = Field(default=None, description="章节号")
    scene_id: Optional[str] = Field(default=None, description="场景ID")
    state_delta: Optional[StateDelta] = Field(default=None, description="状态增量")
    event_id: Optional[str] = Field(default=None, description="事件ID")
    
    # === 一致性检查 ===
    patch_plan: Optional[List[PatchPlanItem]] = Field(default=None, description="修补计划")
    passed: Optional[bool] = Field(default=None, description="是否通过检查")
    
    # === 改稿流程 ===
    mode: Optional[str] = Field(default=None, description="改稿模式")
    plan: Optional[List[RevisePlanItem]] = Field(default=None, description="改稿计划")
    original_content: Optional[str] = Field(default=None, description="原始内容")
    revised_content: Optional[str] = Field(default=None, description="改后内容")
    diff_summary: Optional[str] = Field(default=None, description="差异摘要")
    event_type: Optional[str] = Field(default=None, description="事件类型")
    new_version: Optional[int] = Field(default=None, description="新版本号")
    
    # === 提案审批流程 ===
    proposal_ids: Optional[List[str]] = Field(default=None, description="提案ID列表")
    
    # === 查询设定流程 ===
    query: Optional[str] = Field(default=None, description="查询内容")
    
    # === 导出流程 ===
    format: Optional[str] = Field(default="markdown", description="导出格式")
    output_path: Optional[str] = Field(default=None, description="输出文件路径")
    success: Optional[bool] = Field(default=None, description="是否成功")


# ==================== 工作流输出定义 ====================

class GraphOutput(BaseModel):
    """工作流输出"""
    result: str = Field(..., description="执行结果描述")
    novel_state: Optional[NovelState] = Field(default=None, description="更新后的小说状态")
    issues: List[IssueItem] = Field(default=[], description="一致性问题列表")
    proposals: List[Proposal] = Field(default=[], description="待审批提案列表")
    output_files: List[str] = Field(default=[], description="输出文件路径列表")
