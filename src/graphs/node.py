"""
NovelOS 节点函数实现
包含所有工作流节点的实现
"""
import os
import json
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient
from langchain_core.messages import HumanMessage, SystemMessage
from jinja2 import Template

logger = logging.getLogger(__name__)

from graphs.state import (
    # 输入输出定义
    IntentRouterInput, IntentRouterOutput,
    CollectProjectInfoInput, CollectProjectInfoOutput,
    GenerateStyleBibleInput, GenerateStyleBibleOutput,
    InitNovelStateInput, InitNovelStateOutput,
    GenerateOutlineInput, GenerateOutlineOutput,
    InitSceneQueueInput, InitSceneQueueOutput,
    PickSceneInput, PickSceneOutput,
    BuildContextPackInput, BuildContextPackOutput, ContextPack,
    DraftSceneInput, DraftSceneOutput, SceneSummary, StateDelta,
    CommitStateInput, CommitStateOutput,
    ConsistencyCheckInput, ConsistencyCheckOutput, IssueItem, PatchPlanItem,
    SelectReviseModeInput, SelectReviseModeOutput,
    GenerateRevisePlanInput, GenerateRevisePlanOutput, RevisePlanItem,
    ApplyRevisionInput, ApplyRevisionOutput,
    SaveVersionInput, SaveVersionOutput,
    ListProposalsInput, ListProposalsOutput,
    MergeProposalsInput, MergeProposalsOutput,
    QuerySettingInput, QuerySettingOutput,
    ExportInput, ExportOutput,
    
    # 数据模型
    ProjectInfo, StyleBible, NovelState, SceneCard, OutlineBeat, 
    Entity, CanonRule, ChapterInfo, TimelineEvent, Proposal, ChangeLog, WorldSetting,
    
    # 全局状态
    GlobalState
)

from storage.database.db import get_session
from storage.database.novel_manager import NovelStateManager, NovelStateCreate, NovelStateUpdate, StateEventCreate


# ==================== 意图识别节点 ====================

def intent_router_node(state: IntentRouterInput, config: RunnableConfig, runtime: Runtime[Context]) -> IntentRouterOutput:
    """
    title: 意图识别
    desc: 分析用户输入，识别用户想要执行的操作类型（新建项目/写作/改稿/检查/查询/审批/导出）
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 读取配置文件
    cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), config['metadata']['llm_cfg'])
    with open(cfg_file, 'r', encoding='utf-8') as fd:
        llm_cfg = json.load(fd)
    
    model_config = llm_cfg.get("config", {})
    sp = llm_cfg.get("sp", "")
    up_template = llm_cfg.get("up", "")
    
    # 渲染用户提示词
    up_tpl = Template(up_template)
    user_prompt = up_tpl.render({"user_input": state.user_input})
    
    # 调用大模型
    client = LLMClient(ctx=ctx)
    messages = [
        SystemMessage(content=sp),
        HumanMessage(content=user_prompt)
    ]
    
    response = client.invoke(
        messages=messages,
        model=model_config.get("model", "doubao-seed-1-8-251228"),
        temperature=model_config.get("temperature", 0.3),
        max_completion_tokens=model_config.get("max_completion_tokens", 1000)
    )
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    # 尝试提取JSON
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            result = json.loads(json_str)
            intent = result.get("intent", "unknown")
            confidence = result.get("confidence", 0.0)
            parameters = result.get("parameters", {})
        except json.JSONDecodeError:
            intent = "unknown"
            confidence = 0.0
            parameters = {}
    else:
        intent = "unknown"
        confidence = 0.0
        parameters = {}
    
    # 检查项目是否存在，并加载NovelState
    project_exists = False
    loaded_novel_state = None
    if state.project_id:
        try:
            db = get_session()
            try:
                mgr = NovelStateManager()
                snapshot = mgr.get_snapshot(db, state.project_id)
                if snapshot:
                    project_exists = True
                    # 从快照加载NovelState
                    loaded_novel_state = NovelState(**snapshot.snapshot)
            finally:
                db.close()
        except Exception as e:
            # 数据库连接失败时，假设项目不存在
            logger.warning(f"Failed to check/load project existence: {e}")
            project_exists = False

    return IntentRouterOutput(
        intent=intent,
        confidence=confidence,
        parameters=parameters,
        project_exists=project_exists,
        novel_state=loaded_novel_state
    )


# ==================== 新书创建流程节点 ====================

def collect_project_info_node(state: CollectProjectInfoInput, config: RunnableConfig, runtime: Runtime[Context]) -> CollectProjectInfoOutput:
    """
    title: 收集项目信息
    desc: 从用户输入中提取小说项目的基本信息（标题、题材、受众、视角、长度等）
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    input_data = state  # 直接使用state作为输入对象
    
    # 使用LLM提取项目信息
    client = LLMClient(ctx=ctx)
    
    prompt = f"""请从以下用户输入中提取小说项目的基本信息，返回JSON格式：

用户输入：{state.user_input}

请提取以下信息（如果用户没有明确说明，请根据上下文合理推断）：
- title: 小说标题
- genre: 题材（玄幻/科幻/言情/悬疑/历史/都市等）
- target_audience: 目标受众
- target_length: 目标字数（默认200000）
- narrative_perspective: 叙事视角（第一人称/第三人称，默认第三人称）
- tenses: 时态（过去时/现在时，默认过去时）

返回JSON格式：
{{
    "title": "...",
    "genre": "...",
    "target_audience": "...",
    "target_length": 200000,
    "narrative_perspective": "第三人称",
    "tenses": "过去时"
}}
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # 默认值
            data = {
                "title": "未命名作品",
                "genre": "未知",
                "target_audience": "大众",
                "target_length": 200000,
                "narrative_perspective": "第三人称",
                "tenses": "过去时"
            }
    else:
        data = {
            "title": "未命名作品",
            "genre": "未知",
            "target_audience": "大众",
            "target_length": 200000,
            "narrative_perspective": "第三人称",
            "tenses": "过去时"
        }
    
    project_info = ProjectInfo(**data)
    return CollectProjectInfoOutput(project_info=project_info)


def generate_style_bible_node(state: GenerateStyleBibleInput, config: RunnableConfig, runtime: Runtime[Context]) -> GenerateStyleBibleOutput:
    """
    title: 生成写作宪法
    desc: 根据项目信息生成文风约束（语气、基调、节奏、禁忌等）
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    client = LLMClient(ctx=ctx)
    
    prompt = f"""基于以下小说项目信息，生成写作宪法（Style Bible），返回JSON格式：

项目信息：
- 标题：{state.project_info.title}
- 题材：{state.project_info.genre}
- 目标受众：{state.project_info.target_audience}
- 叙事视角：{state.project_info.narrative_perspective}
- 时态：{state.project_info.tenses}

请生成以下内容：
- voice: 语气风格（如：幽默/严肃/抒情/冷峻等）
- tone: 基调（如：温馨/悲壮/轻松/紧张等）
- pacing: 节奏控制（如：快节奏/慢铺垫/张弛有度等）
- taboos: 禁忌内容列表（至少3条）
- dialogue_style: 对话风格
- description_style: 描写风格

返回JSON格式：
{{
    "voice": "...",
    "tone": "...",
    "pacing": "...",
    "taboos": ["...", "...", "..."],
    "dialogue_style": "...",
    "description_style": "..."
}}
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.7)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            data = {
                "voice": "自然流畅",
                "tone": "平和",
                "pacing": "适中",
                "taboos": ["避免过度暴力", "避免低俗内容", "保持内容健康"],
                "dialogue_style": "贴近生活",
                "description_style": "生动形象"
            }
    else:
        data = {
            "voice": "自然流畅",
            "tone": "平和",
            "pacing": "适中",
            "taboos": ["避免过度暴力", "避免低俗内容", "保持内容健康"],
            "dialogue_style": "贴近生活",
            "description_style": "生动形象"
        }
    
    style_bible = StyleBible(**data)
    return GenerateStyleBibleOutput(style_bible=style_bible)


def init_novel_state_node(state: InitNovelStateInput, config: RunnableConfig, runtime: Runtime[Context]) -> InitNovelStateOutput:
    """
    title: 初始化NovelState
    desc: 根据项目信息和写作宪法创建初始的NovelState
    integrations: 数据库
    """
    # 创建默认的project_info和style_bible
    project_info = ProjectInfo(
        title="未命名作品",
        genre="未知",
        target_audience="大众",
        target_length=200000,
        narrative_perspective="第三人称",
        tenses="过去时"
    )
    
    style_bible = StyleBible(
        voice="自然流畅",
        tone="平和",
        pacing="适中",
        taboos=["避免过度暴力", "避免低俗内容", "保持内容健康"],
        dialogue_style="贴近生活",
        description_style="生动形象"
    )
    
    input_data = InitNovelStateInput(project_info=project_info, style_bible=style_bible)
    # 生成项目ID
    project_id = f"novel_{uuid.uuid4().hex[:8]}"
    
    # 创建NovelState
    novel_state = NovelState(
        project_id=project_id,
        project=state.project_info,
        style=state.style_bible,
        outline=[],
        chapters={},
        scene_queue=[],
        world=WorldSetting(),
        timeline=[],
        proposals=[],
        change_log=[],
        current_version=1,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # 保存到数据库
    try:
        db = get_session()
        try:
            mgr = NovelStateManager()
            snapshot_in = NovelStateCreate(
                project_id=project_id,
                snapshot=novel_state.model_dump(),
                version=1
            )
            mgr.create_snapshot(db, snapshot_in)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to save novel state to database: {e}")
    
    return InitNovelStateOutput(novel_state=novel_state)


def generate_outline_node(state: GenerateOutlineInput, config: RunnableConfig, runtime: Runtime[Context]) -> GenerateOutlineOutput:
    """
    title: 生成大纲
    desc: 根据项目信息生成小说大纲和初始场景卡
    integrations: 大语言模型
    """
    ctx = runtime.context

    # 检查novel_state是否存在
    if not state.novel_state or not state.novel_state.project:
        # 返回默认大纲和场景
        outline = [
            OutlineBeat(
                beat_id="beat_001",
                title="开场",
                description="故事开场，介绍主角和世界观",
                act="第一幕",
                sequence=1,
                estimated_chapters=2
            ),
            OutlineBeat(
                beat_id="beat_002",
                title="激励事件",
                description="主角遭遇关键事件，踏上旅程",
                act="第一幕",
                sequence=2,
                estimated_chapters=3
            ),
            OutlineBeat(
                beat_id="beat_003",
                title="情节上升",
                description="主角面临各种挑战和考验",
                act="第二幕",
                sequence=3,
                estimated_chapters=5
            ),
            OutlineBeat(
                beat_id="beat_004",
                title="中点",
                description="故事转折点，主角做出重大决策",
                act="第二幕",
                sequence=4,
                estimated_chapters=3
            ),
            OutlineBeat(
                beat_id="beat_005",
                title="高潮前奏",
                description="危机加深，最终决战前的准备",
                act="第三幕",
                sequence=5,
                estimated_chapters=3
            ),
            OutlineBeat(
                beat_id="beat_006",
                title="高潮与结局",
                description="最终决战和结局",
                act="第三幕",
                sequence=6,
                estimated_chapters=2
            )
        ]
        initial_scenes = [
            SceneCard(
                scene_id="scene_001",
                chapter_ref="1",
                sequence_in_chapter=1,
                objective="介绍主角的日常生活",
                conflict="日常生活被打破",
                turning_point="意外事件发生",
                result="主角踏上旅程",
                characters=[],
                location="家中",
                time_point="早晨",
                foreshadowing=[],
                style_markers={},
                priority=10
            )
        ]
        return GenerateOutlineOutput(outline=outline, initial_scenes=initial_scenes)

    client = LLMClient(ctx=ctx)

    prompt = f"""基于以下信息生成小说大纲和初始场景卡，返回JSON格式：

项目信息：
- 标题：{state.novel_state.project.title}
- 题材：{state.novel_state.project.genre}
- 目标长度：{state.novel_state.project.target_length}字
- 叙事视角：{state.novel_state.project.narrative_perspective}

请生成：
1. 大纲节点（OutlineBeat）：至少6个节点，涵盖第一幕、第二幕、第三幕
2. 初始场景卡（SceneCard）：至少3张，用于第一幕

大纲节点格式：
{{
    "outline": [
        {{
            "beat_id": "beat_001",
            "title": "标题",
            "description": "描述",
            "act": "第一幕",
            "sequence": 1,
            "estimated_chapters": 2
        }}
    ]
}}

场景卡格式：
{{
    "initial_scenes": [
        {{
            "scene_id": "scene_001",
            "chapter_ref": "1",
            "sequence_in_chapter": 1,
            "objective": "场景目标",
            "conflict": "冲突",
            "turning_point": "转折",
            "result": "结果",
            "characters": [],
            "location": "地点",
            "time_point": "时间点",
            "foreshadowing": [],
            "style_markers": {{}},
            "priority": 10
        }}
    ]
}}

请返回完整的JSON，包含outline和initial_scenes两个字段。
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.7, max_completion_tokens=4000)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            outline_data = data.get("outline", [])
            scenes_data = data.get("initial_scenes", [])
            
            outline = [OutlineBeat(**item) for item in outline_data]
            initial_scenes = [SceneCard(**item) for item in scenes_data]
        except (json.JSONDecodeError, TypeError) as e:
            # 默认大纲
            outline = [
                OutlineBeat(
                    beat_id="beat_001",
                    title="开场",
                    description="故事开场，介绍主角和世界观",
                    act="第一幕",
                    sequence=1,
                    estimated_chapters=2
                ),
                OutlineBeat(
                    beat_id="beat_002",
                    title="激励事件",
                    description="主角遭遇关键事件，踏上旅程",
                    act="第一幕",
                    sequence=2,
                    estimated_chapters=3
                ),
                OutlineBeat(
                    beat_id="beat_003",
                    title="情节上升",
                    description="主角面临各种挑战和考验",
                    act="第二幕",
                    sequence=3,
                    estimated_chapters=5
                ),
                OutlineBeat(
                    beat_id="beat_004",
                    title="中点",
                    description="故事转折点，主角做出重大决策",
                    act="第二幕",
                    sequence=4,
                    estimated_chapters=3
                ),
                OutlineBeat(
                    beat_id="beat_005",
                    title="高潮前奏",
                    description="危机加深，最终决战前的准备",
                    act="第三幕",
                    sequence=5,
                    estimated_chapters=3
                ),
                OutlineBeat(
                    beat_id="beat_006",
                    title="高潮与结局",
                    description="最终决战和结局",
                    act="第三幕",
                    sequence=6,
                    estimated_chapters=2
                )
            ]
            initial_scenes = [
                SceneCard(
                    scene_id="scene_001",
                    chapter_ref="1",
                    sequence_in_chapter=1,
                    objective="介绍主角的日常生活",
                    conflict="日常生活被打破",
                    turning_point="意外事件发生",
                    result="主角踏上旅程",
                    characters=[],
                    location="家中",
                    time_point="早晨",
                    foreshadowing=[],
                    style_markers={},
                    priority=10
                )
            ]
    else:
        # 默认大纲
        outline = [
            OutlineBeat(
                beat_id="beat_001",
                title="开场",
                description="故事开场，介绍主角和世界观",
                act="第一幕",
                sequence=1,
                estimated_chapters=2
            ),
            OutlineBeat(
                beat_id="beat_002",
                title="激励事件",
                description="主角遭遇关键事件，踏上旅程",
                act="第一幕",
                sequence=2,
                estimated_chapters=3
            ),
            OutlineBeat(
                beat_id="beat_003",
                title="情节上升",
                description="主角面临各种挑战和考验",
                act="第二幕",
                sequence=3,
                estimated_chapters=5
            ),
            OutlineBeat(
                beat_id="beat_004",
                title="中点",
                description="故事转折点，主角做出重大决策",
                act="第二幕",
                sequence=4,
                estimated_chapters=3
            ),
            OutlineBeat(
                beat_id="beat_005",
                title="高潮前奏",
                description="危机加深，最终决战前的准备",
                act="第三幕",
                sequence=5,
                estimated_chapters=3
            ),
            OutlineBeat(
                beat_id="beat_006",
                title="高潮与结局",
                description="最终决战和结局",
                act="第三幕",
                sequence=6,
                estimated_chapters=2
            )
        ]
        initial_scenes = [
            SceneCard(
                scene_id="scene_001",
                chapter_ref="1",
                sequence_in_chapter=1,
                objective="介绍主角的日常生活",
                conflict="日常生活被打破",
                turning_point="意外事件发生",
                result="主角踏上旅程",
                characters=[],
                location="家中",
                time_point="早晨",
                foreshadowing=[],
                style_markers={},
                priority=10
            )
        ]
    
    return GenerateOutlineOutput(outline=outline, initial_scenes=initial_scenes)


def init_scene_queue_node(state: InitSceneQueueInput, config: RunnableConfig, runtime: Runtime[Context]) -> InitSceneQueueOutput:
    """
    title: 初始化场景队列
    desc: 将初始场景卡加入队列，更新NovelState
    integrations: 数据库
    """
    # 创建默认数据
    novel_state = NovelState(
        project_id="temp",
        project=ProjectInfo(
            title="未命名作品",
            genre="未知",
            target_audience="大众",
            target_length=200000,
            narrative_perspective="第三人称",
            tenses="过去时"
        ),
        style=StyleBible(),
        outline=[],
        chapters={},
        scene_queue=[],
        world=WorldSetting(),
        timeline=[],
        proposals=[],
        change_log=[],
        current_version=1,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    initial_scenes = [
        SceneCard(
            scene_id="scene_001",
            chapter_ref="1",
            sequence_in_chapter=1,
            objective="介绍主角的日常生活",
            conflict="日常生活被打破",
            turning_point="意外事件发生",
            result="主角踏上旅程",
            characters=[],
            location="家中",
            time_point="早晨",
            foreshadowing=[],
            style_markers={},
            priority=10
        )
    ]
    
    input_data = InitSceneQueueInput(novel_state=novel_state, initial_scenes=initial_scenes)
    # 更新NovelState
    updated_state = state.novel_state.model_copy(deep=True)
    # outline已经在generate_outline_node中设置了
    updated_state.scene_queue = state.initial_scenes if state.initial_scenes else []
    
    # 保存到数据库
    try:
        db = get_session()
        try:
            mgr = NovelStateManager()
            snapshot_in = NovelStateUpdate(
                project_id=updated_state.project_id,
                snapshot=updated_state.model_dump(),
                version=updated_state.current_version
            )
            mgr.update_snapshot(db, snapshot_in)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to save novel state to database: {e}")
    
    return InitSceneQueueOutput(
        scene_queue=updated_state.scene_queue,
        novel_state=updated_state
    )


# ==================== 场景写作流程节点 ====================

def pick_scene_node(state: PickSceneInput, config: RunnableConfig, runtime: Runtime[Context]) -> PickSceneOutput:
    """
    title: 选择场景
    desc: 从场景队列中选择下一个要写的场景（默认选择优先级最高的）
    integrations: 
    """
    # 创建默认novel_state
    novel_state = state.novel_state
    if novel_state is None:
        novel_state = NovelState(
            project_id="temp",
            project=ProjectInfo(title="未命名", genre="未知", target_length=200000),
            style=StyleBible(),
            outline=[],
            chapters={},
            scene_queue=[],
            world=WorldSetting(),
            timeline=[],
            proposals=[],
            change_log=[],
            current_version=1
        )
    
    input_data = PickSceneInput(novel_state=novel_state, user_override=None)
    if state.user_override:
        # 用户指定了特定场景
        scene_id = state.user_override.get("scene_id")
        for scene in novel_state.scene_queue:
            if scene.scene_id == scene_id:
                return PickSceneOutput(scene_card=scene)
    
    # 默认：选择优先级最高的场景
    if novel_state.scene_queue:
        sorted_scenes = sorted(novel_state.scene_queue, key=lambda x: x.priority, reverse=True)
        return PickSceneOutput(scene_card=sorted_scenes[0])
    
    # 如果队列空了，返回空场景卡
    return PickSceneOutput(scene_card=SceneCard(
        scene_id="",
        chapter_ref="",
        sequence_in_chapter=0,
        objective="",
        conflict="",
        location="",
        time_point="",
        priority=0
    ))


def build_context_pack_node(state: BuildContextPackInput, config: RunnableConfig, runtime: Runtime[Context]) -> BuildContextPackOutput:
    """
    title: 构建Context Pack
    desc: 从NovelState中提取与本场景相关的上下文信息（人物、地点、规则、时间线等）
    integrations:
    """
    # 检查novel_state是否存在
    novel_state = state.novel_state
    if novel_state is None:
        # 返回一个最小化的ContextPack，只包含场景卡信息
        context_pack = ContextPack(
            scene_card=state.scene_card,
            relevant_characters={},
            location_info=None,
            timeline_context=[],
            relevant_rules={},
            style_bible=StyleBible(
                voice="幽默风趣",
                tone="轻松明快",
                pacing="张弛有度",
                taboos=[],
                dialogue_style="贴近都市生活口语",
                description_style="简洁轻快的笔触"
            ),
            chapter_summary=""
        )
        return BuildContextPackOutput(context_pack=context_pack)

    # 提取相关人物
    relevant_characters = {}
    if novel_state.world and novel_state.world.entities:
        for char_id in state.scene_card.characters:
            if char_id in novel_state.world.entities:
                relevant_characters[char_id] = novel_state.world.entities[char_id]

    # 提取地点信息
    location_info = None
    if novel_state.world and novel_state.world.entities and state.scene_card.location:
        if state.scene_card.location in novel_state.world.entities:
            location_info = novel_state.world.entities[state.scene_card.location]

    # 提取时间线上下文
    timeline_context = []
    if novel_state.timeline:
        for event in novel_state.timeline:
            if state.scene_card.chapter_ref in (event.chapter_ref or ""):
                timeline_context.append(event)

    # 提取相关规则
    relevant_rules = {}
    if novel_state.world and novel_state.world.canon_rules:
        for rule_id, rule in novel_state.world.canon_rules.items():
            relevant_rules[rule_id] = rule

    # 获取章节摘要
    chapter_summary = ""
    if novel_state.chapters and state.scene_card.chapter_ref:
        if state.scene_card.chapter_ref in novel_state.chapters:
            chapter_summary = novel_state.chapters[state.scene_card.chapter_ref].summary

    # 获取风格指南，如果不存在则使用默认值
    style_bible = novel_state.style
    if style_bible is None:
        style_bible = StyleBible(
            voice="幽默风趣",
            tone="轻松明快",
            pacing="张弛有度",
            taboos=[],
            dialogue_style="贴近都市生活口语",
            description_style="简洁轻快的笔触"
        )

    context_pack = ContextPack(
        scene_card=state.scene_card,
        relevant_characters=relevant_characters,
        location_info=location_info,
        timeline_context=timeline_context,
        relevant_rules=relevant_rules,
        style_bible=style_bible,
        chapter_summary=chapter_summary
    )

    return BuildContextPackOutput(context_pack=context_pack)


def draft_scene_node(state: DraftSceneInput, config: RunnableConfig, runtime: Runtime[Context]) -> DraftSceneOutput:
    """
    title: 起草场景
    desc: 根据Context Pack生成场景正文内容，同时生成摘要和状态增量
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    client = LLMClient(ctx=ctx)
    
    # 构建提示词
    context_info = f"""
场景目标：{state.context_pack.scene_card.objective}
冲突：{state.context_pack.scene_card.conflict}
转折：{state.context_pack.scene_card.turning_point}
结果：{state.context_pack.scene_card.result}
地点：{state.context_pack.scene_card.location}
时间：{state.context_pack.scene_card.time_point}
"""
    
    style_info = f"""
语气风格：{state.context_pack.style_bible.voice}
基调：{state.context_pack.style_bible.tone}
节奏：{state.context_pack.style_bible.pacing}
对话风格：{state.context_pack.style_bible.dialogue_style}
"""
    
    if state.context_pack.chapter_summary:
        context_info += f"\n章节摘要：{state.context_pack.chapter_summary}"
    
    prompt = f"""请根据以下信息写一个场景：

{context_info}

{style_info}

要求：
1. 字数800-1500字
2. 紧扣场景目标和冲突
3. 体现转折点
4. 遵循指定的文风

请直接返回场景正文内容，不要有任何前言或后言。
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.8, max_completion_tokens=4000)
    
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    # 生成摘要
    summary_prompt = f"""请为以下场景内容写一个100-200字的摘要：

{content[:1000]}...
"""
    summary_response = client.invoke(messages=[HumanMessage(content=summary_prompt)], temperature=0.3)
    summary_text = summary_response.content
    if isinstance(summary_text, str):
        summary_text = summary_text.strip()
    else:
        summary_text = str(summary_text)
    
    # 生成状态增量
    state_delta = StateDelta(
        entities_updated={},
        new_events=[],
        new_proposals=[],
        chapter_updates={},
        scene_updates=[state.context_pack.scene_card.scene_id]
    )
    
    scene_summary = SceneSummary(
        content=summary_text,
        key_points=[state.context_pack.scene_card.objective, state.context_pack.scene_card.conflict]
    )
    
    return DraftSceneOutput(
        content=content,
        summary=scene_summary,
        state_delta=state_delta,
        scene_id=state.context_pack.scene_card.scene_id,
        chapter_no=state.context_pack.scene_card.chapter_ref
    )


def commit_state_node(state: CommitStateInput, config: RunnableConfig, runtime: Runtime[Context]) -> CommitStateOutput:
    """
    title: 提交状态
    desc: 将StateDelta提交到NovelState，记录事件，保存正文文件
    integrations: 数据库
    """
    # 检查novel_state是否存在
    if not state.novel_state:
        logger.warning("novel_state is None, skipping commit_state operation")
        # 创建一个临时的NovelState用于返回
        temp_state = NovelState(
            project_id="temp",
            project=ProjectInfo(
                title="未命名作品",
                genre="未知",
                target_audience="大众",
                target_length=200000,
                narrative_perspective="第三人称",
                tenses="过去时"
            ),
            style=StyleBible(),
            outline=[],
            chapters={},
            scene_queue=[],
            world=WorldSetting(),
            timeline=[],
            proposals=[],
            change_log=[],
            current_version=1,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        return CommitStateOutput(
            novel_state=temp_state,
            event_id="temp_event",
            file_path=""
        )

    # 更新NovelState
    updated_state = state.novel_state.model_copy(deep=True)
    
    # 生成文件路径
    project_dir = f"assets/{updated_state.project_id}"
    chapter_dir = f"{project_dir}/chapter_{state.chapter_no}"
    file_path = f"{chapter_dir}/v{updated_state.current_version}.md"
    
    # 创建目录
    import os
    os.makedirs(chapter_dir, exist_ok=True)
    
    # 保存正文文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(state.content)
    
    # 更新章节信息
    if state.chapter_no not in updated_state.chapters:
        updated_state.chapters[state.chapter_no] = ChapterInfo(
            chapter_no=state.chapter_no,
            title=f"第{state.chapter_no}章",
            summary="",
            completion_rate=0.0,
            current_version=updated_state.current_version,
            scenes=[],
            file_path=file_path
        )
    
    updated_state.chapters[state.chapter_no].file_path = file_path
    updated_state.chapters[state.chapter_no].current_version = updated_state.current_version
    updated_state.chapters[state.chapter_no].completion_rate = min(1.0, updated_state.chapters[state.chapter_no].completion_rate + 0.2)
    
    # 从队列中移除已完成的场景
    updated_state.scene_queue = [s for s in updated_state.scene_queue if s.scene_id != state.scene_id]
    
    # 增加版本号
    updated_state.current_version += 1
    
    # 记录事件
    event_id = f"event_{uuid.uuid4().hex[:8]}"
    change_log = ChangeLog(
        log_id=event_id,
        version=updated_state.current_version - 1,
        timestamp=datetime.now().isoformat(),
        event_type="draft",
        delta=state.state_delta,
        chapter_ref=state.chapter_no,
        scene_ref=state.scene_id,
        description=f"完成场景 {state.scene_id}"
    )
    updated_state.change_log.append(change_log)
    
    # 保存到数据库
    try:
        db = get_session()
        try:
            mgr = NovelStateManager()
            
            # 更新快照
            snapshot_in = NovelStateUpdate(
                project_id=updated_state.project_id,
                snapshot=updated_state.model_dump(),
                version=updated_state.current_version
            )
            mgr.update_snapshot(db, snapshot_in)
            
            # 记录事件
            event_in = StateEventCreate(
                project_id=updated_state.project_id,
                event_type="draft",
                version_before=updated_state.current_version - 1,
                version_after=updated_state.current_version,
                state_delta=state.state_delta.model_dump(),
                chapter_ref=state.chapter_no,
                scene_ref=state.scene_id,
                description=f"完成场景 {state.scene_id}"
            )
            mgr.create_event(db, event_in)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to save novel state to database: {e}")
    
    return CommitStateOutput(
        novel_state=updated_state,
        event_id=event_id,
        file_path=file_path
    )


def consistency_check_entry_node(state: QuerySettingInput, config: RunnableConfig, runtime: Runtime[Context]) -> ConsistencyCheckOutput:
    """
    title: 一致性检查入口
    desc: 用户手动触发一致性检查的入口节点，用于检查指定章节/场景的内容一致性
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 检查novel_state是否存在
    if not state.novel_state:
        return ConsistencyCheckOutput(
            issues=[],
            patch_plan=[],
            passed=True
        )
    
    client = LLMClient(ctx=ctx)
    
    # 构建规则上下文
    rules_text = "\n".join([f"- {rule.content}" for rule in state.novel_state.world.canon_rules.values()])
    
    # 构建人物上下文
    characters_text = "\n".join([f"- {char.name}: {char.description}" for char in state.novel_state.world.entities.values() if char.type == "character"])
    
    prompt = f"""用户请求检查设定的一致性。根据查询内容确定检查范围，返回JSON格式：

用户查询：{state.query}

硬设定规则：
{rules_text if rules_text else '暂无规则'}

人物信息：
{characters_text if characters_text else '暂无人物信息'}

如果查询涉及特定章节或场景，请：
1. 提取章节号/场景ID
2. 检查相关内容的一致性

如果查询是全局检查，请：
1. 检查整体设定的一致性
2. 列出所有潜在冲突

返回JSON格式：
{{
    "issues": [
        {{
            "severity": "blocker|warn|info",
            "where": "位置描述",
            "why": "违反的规则",
            "fix_suggestion": "修复建议",
            "rule_ref": "规则ID"
        }}
    ],
    "patch_plan": [
        {{
            "target": "目标位置",
            "action": "replace|delete|insert",
            "content": "内容",
            "rationale": "理由"
        }}
    ]
}}

如果没有问题，返回空的issues数组。
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            issues_data = data.get("issues", [])
            patch_data = data.get("patch_plan", [])
            
            issues = [IssueItem(**item) for item in issues_data]
            patch_plan = [PatchPlanItem(**item) for item in patch_data]
        except (json.JSONDecodeError, TypeError):
            issues = []
            patch_plan = []
    else:
        issues = []
        patch_plan = []
    
    passed = len([i for i in issues if i.severity == "blocker"]) == 0
    
    return ConsistencyCheckOutput(
        issues=issues,
        patch_plan=patch_plan,
        passed=passed
    )


# ==================== 一致性检查节点 ====================

def consistency_check_node(state: ConsistencyCheckInput, config: RunnableConfig, runtime: Runtime[Context]) -> ConsistencyCheckOutput:
    """
    title: 一致性检查
    desc: 检查内容是否符合设定规则，生成问题列表和修补计划
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 检查novel_state是否存在
    if not state.novel_state:
        return ConsistencyCheckOutput(
            issues=[],
            patch_plan=[],
            passed=True
        )
    
    client = LLMClient(ctx=ctx)
    
    # 构建规则上下文
    rules_text = "\n".join([f"- {rule.content}" for rule in state.novel_state.world.canon_rules.values()])
    
    # 构建人物上下文
    characters_text = "\n".join([f"- {char.name}: {char.description}" for char in state.novel_state.world.entities.values() if char.type == "character"])
    
    prompt = f"""请检查以下内容的一致性，返回JSON格式：

章节号：{state.chapter_no}
场景ID：{state.scene_id or '无'}

硬设定规则：
{rules_text if rules_text else '暂无规则'}

人物信息：
{characters_text if characters_text else '暂无人物信息'}

待检查内容：
{state.content[:2000]}...

请检查：
1. 视角是否一致
2. 时间线是否有矛盾
3. 人物属性是否一致
4. 是否违反硬设定规则

返回JSON格式：
{{
    "issues": [
        {{
            "severity": "blocker|warn|info",
            "where": "位置描述",
            "why": "违反的规则",
            "fix_suggestion": "修复建议",
            "rule_ref": "规则ID"
        }}
    ],
    "patch_plan": [
        {{
            "target": "目标位置",
            "action": "replace|delete|insert",
            "content": "内容",
            "rationale": "理由"
        }}
    ]
}}

如果没有问题，返回空的issues数组。
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            issues_data = data.get("issues", [])
            patch_data = data.get("patch_plan", [])
            
            issues = [IssueItem(**item) for item in issues_data]
            patch_plan = [PatchPlanItem(**item) for item in patch_data]
        except (json.JSONDecodeError, TypeError):
            issues = []
            patch_plan = []
    else:
        issues = []
        patch_plan = []
    
    passed = len([i for i in issues if i.severity == "blocker"]) == 0
    
    return ConsistencyCheckOutput(
        issues=issues,
        patch_plan=patch_plan,
        passed=passed
    )


def consistency_check_draft_node(state: ConsistencyCheckInput, config: RunnableConfig, runtime: Runtime[Context]) -> ConsistencyCheckOutput:
    """
    title: 起草后一致性检查
    desc: 检查起草内容是否符合设定规则，生成问题列表和修补计划
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 检查novel_state是否存在
    if not state.novel_state:
        return ConsistencyCheckOutput(
            issues=[],
            patch_plan=[],
            passed=True
        )
    
    client = LLMClient(ctx=ctx)
    
    # 构建规则上下文
    rules_text = "\n".join([f"- {rule.content}" for rule in state.novel_state.world.canon_rules.values()])
    
    # 构建人物上下文
    characters_text = "\n".join([f"- {char.name}: {char.description}" for char in state.novel_state.world.entities.values() if char.type == "character"])
    
    prompt = f"""请检查以下内容的一致性，返回JSON格式：

章节号：{state.chapter_no}
场景ID：{state.scene_id or '无'}

硬设定规则：
{rules_text if rules_text else '暂无规则'}

人物信息：
{characters_text if characters_text else '暂无人物信息'}

待检查内容：
{state.content[:2000]}...

请检查：
1. 视角是否一致
2. 时间线是否有矛盾
3. 人物属性是否一致
4. 是否违反硬设定规则

返回JSON格式：
{{
    "issues": [
        {{
            "severity": "blocker|warn|info",
            "where": "位置描述",
            "why": "违反的规则",
            "fix_suggestion": "修复建议",
            "rule_ref": "规则ID"
        }}
    ],
    "patch_plan": [
        {{
            "target": "目标位置",
            "action": "replace|delete|insert",
            "content": "内容",
            "rationale": "理由"
        }}
    ]
}}

如果没有问题，返回空的issues数组。
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            issues_data = data.get("issues", [])
            patch_data = data.get("patch_plan", [])
            
            issues = [IssueItem(**item) for item in issues_data]
            patch_plan = [PatchPlanItem(**item) for item in patch_data]
        except (json.JSONDecodeError, TypeError):
            issues = []
            patch_plan = []
    else:
        issues = []
        patch_plan = []
    
    passed = len([i for i in issues if i.severity == "blocker"]) == 0
    
    return ConsistencyCheckOutput(
        issues=issues,
        patch_plan=patch_plan,
        passed=passed
    )


def consistency_check_revise_node(state: ConsistencyCheckInput, config: RunnableConfig, runtime: Runtime[Context]) -> ConsistencyCheckOutput:
    """
    title: 改稿后一致性检查
    desc: 检查改稿内容是否符合设定规则，验证修补效果
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 检查novel_state是否存在
    if not state.novel_state:
        return ConsistencyCheckOutput(
            issues=[],
            patch_plan=[],
            passed=True
        )
    
    client = LLMClient(ctx=ctx)
    
    # 构建规则上下文
    rules_text = "\n".join([f"- {rule.content}" for rule in state.novel_state.world.canon_rules.values()])
    
    # 构建人物上下文
    characters_text = "\n".join([f"- {char.name}: {char.description}" for char in state.novel_state.world.entities.values() if char.type == "character"])
    
    prompt = f"""请检查改稿后内容的一致性，验证修补效果，返回JSON格式：

章节号：{state.chapter_no}
场景ID：{state.scene_id or '无'}

硬设定规则：
{rules_text if rules_text else '暂无规则'}

人物信息：
{characters_text if characters_text else '暂无人物信息'}

待检查内容：
{state.content[:2000]}...

请检查：
1. 视角是否一致
2. 时间线是否有矛盾
3. 人物属性是否一致
4. 是否违反硬设定规则
5. 是否成功修复了之前的问题

返回JSON格式：
{{
    "issues": [
        {{
            "severity": "blocker|warn|info",
            "where": "位置描述",
            "why": "违反的规则",
            "fix_suggestion": "修复建议",
            "rule_ref": "规则ID"
        }}
    ],
    "patch_plan": [
        {{
            "target": "目标位置",
            "action": "replace|delete|insert",
            "content": "内容",
            "rationale": "理由"
        }}
    ]
}}

如果没有问题，返回空的issues数组。
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            issues_data = data.get("issues", [])
            patch_data = data.get("patch_plan", [])
            
            issues = [IssueItem(**item) for item in issues_data]
            patch_plan = [PatchPlanItem(**item) for item in patch_data]
        except (json.JSONDecodeError, TypeError):
            issues = []
            patch_plan = []
    else:
        issues = []
        patch_plan = []
    
    passed = len([i for i in issues if i.severity == "blocker"]) == 0
    
    return ConsistencyCheckOutput(
        issues=issues,
        patch_plan=patch_plan,
        passed=passed
    )


# ==================== 改稿流程节点 ====================

def select_revise_mode_node(state: SelectReviseModeInput, config: RunnableConfig, runtime: Runtime[Context]) -> SelectReviseModeOutput:
    """
    title: 选择改稿模式
    desc: 从用户输入中识别改稿模式（润色/结构重写/剧情修订）
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    client = LLMClient(ctx=ctx)
    
    prompt = f"""请从用户输入中识别改稿模式，返回JSON格式：

用户输入：{state.user_input}

可用的改稿模式：
- polish: 语句润色（不改剧情、不新增设定）
- restructure: 结构重写（允许重排段落、加强冲突，但不改关键事件）
- plot_revision: 剧情修订（允许改事件，但需要走提案流程）

如果用户指定了章节或场景，也提取出来。

返回JSON格式：
{{
    "mode": "polish|restructure|plot_revision",
    "target_chapter": "章节号（可选）",
    "target_scene": "场景ID（可选）"
}}
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            mode = data.get("mode", "polish")
            target_chapter = data.get("target_chapter")
            target_scene = data.get("target_scene")
        except (json.JSONDecodeError, TypeError):
            mode = "polish"
            target_chapter = None
            target_scene = None
    else:
        mode = "polish"
        target_chapter = None
        target_scene = None
    
    return SelectReviseModeOutput(
        mode=mode,
        target_chapter=target_chapter,
        target_scene=target_scene
    )


def generate_revise_plan_node(state: GenerateRevisePlanInput, config: RunnableConfig, runtime: Runtime[Context]) -> GenerateRevisePlanOutput:
    """
    title: 生成改稿计划
    desc: 根据改稿模式和问题列表生成具体的改稿计划
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    client = LLMClient(ctx=ctx)
    
    issues_text = "\n".join([f"- [{i.severity}] {i.where}: {i.why} -> {i.fix_suggestion}" for i in state.issues])
    
    mode_desc = {
        "polish": "语句润色（不改剧情、不新增设定）",
        "restructure": "结构重写（允许重排段落、加强冲突，但不改关键事件）",
        "plot_revision": "剧情修订（允许改事件）"
    }
    
    prompt = f"""请生成改稿计划，返回JSON格式：

改稿模式：{mode_desc.get(state.mode, state.mode)}

问题列表：
{issues_text if issues_text else '无问题'}

待改稿内容：
{state.content[:1500]}...

请生成具体的改稿计划，每个计划项包含：
- location: 位置描述
- action: 操作描述
- rationale: 理由

返回JSON格式：
{{
    "plan": [
        {{
            "location": "位置",
            "action": "操作描述",
            "rationale": "理由"
        }}
    ]
}}
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.5)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            plan_data = data.get("plan", [])
            plan = [RevisePlanItem(**item) for item in plan_data]
        except (json.JSONDecodeError, TypeError):
            plan = []
    else:
        plan = []
    
    return GenerateRevisePlanOutput(plan=plan)


def apply_revision_node(state: ApplyRevisionInput, config: RunnableConfig, runtime: Runtime[Context]) -> ApplyRevisionOutput:
    """
    title: 应用改稿
    desc: 根据改稿计划对原文进行修改
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    client = LLMClient(ctx=ctx)
    
    plan_text = "\n".join([f"{i+1}. 位置：{item.location}，操作：{item.action}，理由：{item.rationale}" for i, item in enumerate(state.plan)])
    
    mode_desc = {
        "polish": "语句润色（不改剧情、不新增设定）",
        "restructure": "结构重写（允许重排段落、加强冲突，但不改关键事件）",
        "plot_revision": "剧情修订（允许改事件）"
    }
    
    prompt = f"""请根据改稿计划对原文进行修改，返回改后的内容：

改稿模式：{mode_desc.get(state.mode, state.mode)}

改稿计划：
{plan_text if plan_text else '无具体计划，请根据模式进行通用修改'}

原文：
{state.original_content}

要求：
1. 直接返回改后的内容，不要有任何前言或后言
2. 严格按照改稿模式的要求进行修改
3. 保持原文的核心内容不丢失（除非是剧情修订模式）
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.7, max_completion_tokens=4000)
    
    revised_content = response.content
    if isinstance(revised_content, str):
        revised_content = revised_content.strip()
    else:
        revised_content = str(revised_content)
    
    diff_summary = f"改稿模式：{state.mode}，修改计划项数：{len(state.plan)}"
    
    return ApplyRevisionOutput(
        revised_content=revised_content,
        diff_summary=diff_summary
    )


def save_version_node(state: SaveVersionInput, config: RunnableConfig, runtime: Runtime[Context]) -> SaveVersionOutput:
    """
    title: 保存版本
    desc: 保存新版本的正文，更新NovelState
    integrations: 数据库
    """
    # 更新NovelState
    updated_state = state.novel_state.model_copy(deep=True)
    
    # 生成文件路径
    project_dir = f"assets/{updated_state.project_id}"
    chapter_dir = f"{project_dir}/chapter_{state.chapter_no}"
    file_path = f"{chapter_dir}/v{updated_state.current_version}.md"
    
    # 创建目录
    import os
    os.makedirs(chapter_dir, exist_ok=True)
    
    # 保存正文文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(state.content)
    
    # 更新章节信息
    if state.chapter_no not in updated_state.chapters:
        updated_state.chapters[state.chapter_no] = ChapterInfo(
            chapter_no=state.chapter_no,
            title=f"第{state.chapter_no}章",
            summary="",
            completion_rate=0.0,
            current_version=updated_state.current_version,
            scenes=[],
            file_path=file_path
        )
    
    updated_state.chapters[state.chapter_no].file_path = file_path
    updated_state.chapters[state.chapter_no].current_version = updated_state.current_version
    
    # 增加版本号
    new_version = updated_state.current_version + 1
    updated_state.current_version = new_version
    
    # 记录事件
    event_id = f"event_{uuid.uuid4().hex[:8]}"
    change_log = ChangeLog(
        log_id=event_id,
        version=new_version - 1,
        timestamp=datetime.now().isoformat(),
        event_type=state.event_type,
        delta=StateDelta(),
        chapter_ref=state.chapter_no,
        scene_ref=None,
        description=f"保存版本 {new_version}"
    )
    updated_state.change_log.append(change_log)
    
    # 保存到数据库
    try:
        db = get_session()
        try:
            mgr = NovelStateManager()
            
            # 更新快照
            snapshot_in = NovelStateUpdate(
                project_id=updated_state.project_id,
                snapshot=updated_state.model_dump(),
                version=new_version
            )
            mgr.update_snapshot(db, snapshot_in)
            
            # 记录事件
            event_in = StateEventCreate(
                project_id=updated_state.project_id,
                event_type=state.event_type,
                version_before=new_version - 1,
                version_after=new_version,
                state_delta={},
                chapter_ref=state.chapter_no,
                scene_ref=None,
                description=f"保存版本 {new_version}"
            )
            mgr.create_event(db, event_in)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to save novel state to database: {e}")
    
    return SaveVersionOutput(
        novel_state=updated_state,
        file_path=file_path,
        new_version=new_version
    )


# ==================== 提案审批流程节点 ====================

def list_proposals_node(state: ListProposalsInput, config: RunnableConfig, runtime: Runtime[Context]) -> ListProposalsOutput:
    """
    title: 列提案
    desc: 列出所有待审批、已批准、已拒绝的提案
    integrations:
    """
    # 检查novel_state是否存在
    if not state.novel_state:
        return ListProposalsOutput(
            pending_proposals=[],
            approved_proposals=[],
            rejected_proposals=[]
        )

    proposals = state.novel_state.proposals or []
    pending_proposals = [p for p in proposals if p.status == "pending"]
    approved_proposals = [p for p in proposals if p.status == "approved"]
    rejected_proposals = [p for p in proposals if p.status == "rejected"]

    return ListProposalsOutput(
        pending_proposals=pending_proposals,
        approved_proposals=approved_proposals,
        rejected_proposals=rejected_proposals
    )


def merge_proposals_node(state: MergeProposalsInput, config: RunnableConfig, runtime: Runtime[Context]) -> MergeProposalsOutput:
    """
    title: 合并提案
    desc: 将批准的提案合并到Canon中
    integrations: 数据库
    """
    # 更新NovelState
    updated_state = state.novel_state.model_copy(deep=True)
    
    merged_count = 0
    
    for proposal_id in state.proposal_ids:
        # 查找并更新提案状态
        for proposal in updated_state.proposals:
            if proposal.proposal_id == proposal_id and proposal.status == "pending":
                proposal.status = "approved"
                merged_count += 1
                
                # 根据提案类型更新世界观
                if proposal.proposal_type == "new_entity":
                    # 这里简化处理，实际应该解析proposal.content创建新实体
                    pass
                elif proposal.proposal_type == "new_rule":
                    # 创建新规则
                    pass
    
    # 保存到数据库
    try:
        db = get_session()
        try:
            mgr = NovelStateManager()
            snapshot_in = NovelStateUpdate(
                project_id=updated_state.project_id,
                snapshot=updated_state.model_dump(),
                version=updated_state.current_version
            )
            mgr.update_snapshot(db, snapshot_in)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to save novel state to database: {e}")
    
    return MergeProposalsOutput(
        novel_state=updated_state,
        merged_count=merged_count
    )


# ==================== 查询设定流程节点 ====================

def query_setting_node(state: QuerySettingInput, config: RunnableConfig, runtime: Runtime[Context]) -> QuerySettingOutput:
    """
    title: 查询设定
    desc: 根据查询内容从NovelState中查找相关信息
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 检查novel_state是否存在
    if not state.novel_state:
        return QuerySettingOutput(
            results=[{
                "type": "error",
                "name": "项目不存在",
                "content": "未找到项目数据，请先创建项目或提供正确的项目ID",
                "relevance": "N/A"
            }]
        )
    
    client = LLMClient(ctx=ctx)
    
    # 构建设定信息文本
    entities_text = "\n".join([f"- {char.name}（{char.type}）: {char.description}" for char in state.novel_state.world.entities.values()])
    rules_text = "\n".join([f"- {rule.content}" for rule in state.novel_state.world.canon_rules.values()])
    outline_text = "\n".join([f"{i+1}. {beat.title}: {beat.description}" for i, beat in enumerate(state.novel_state.outline)])
    
    prompt = f"""请根据查询内容从以下设定中查找相关信息，返回JSON格式：

查询内容：{state.query}

人物/地点/物品：
{entities_text if entities_text else '暂无设定'}

硬设定规则：
{rules_text if rules_text else '暂无规则'}

大纲：
{outline_text if outline_text else '暂无大纲'}

请返回相关的设定信息，格式如下：
{{
    "results": [
        {{
            "type": "character|location|rule|outline",
            "name": "名称",
            "content": "内容",
            "relevance": "相关性描述"
        }}
    ]
}}
"""
    
    messages = [HumanMessage(content=prompt)]
    response = client.invoke(messages=messages, temperature=0.3)
    
    # 解析结果
    content = response.content
    if isinstance(content, str):
        content = content.strip()
    else:
        content = str(content)
    
    json_start = content.find('{')
    json_end = content.rfind('}') + 1
    if json_start >= 0 and json_end > json_start:
        json_str = content[json_start:json_end]
        try:
            data = json.loads(json_str)
            results = data.get("results", [])
        except (json.JSONDecodeError, TypeError):
            results = []
    else:
        results = []
    
    return QuerySettingOutput(results=results)


# ==================== 导出流程节点 ====================

def export_node(state: ExportInput, config: RunnableConfig, runtime: Runtime[Context]) -> ExportOutput:
    """
    title: 导出
    desc: 将小说导出为指定格式（Markdown/TXT）
    integrations: 
    """
    # 检查novel_state是否存在
    if not state.novel_state:
        return ExportOutput(
            output_path="",
            success=False
        )
    
    project_dir = f"assets/{state.novel_state.project_id}"
    os.makedirs(project_dir, exist_ok=True)
    
    # 按章节顺序导出
    chapters = sorted(state.novel_state.chapters.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
    
    full_content = f"# {state.novel_state.project.title}\n\n"
    
    for chapter_no, chapter_info in chapters:
        # 读取章节内容
        if chapter_info.file_path:
            file_path = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), chapter_info.file_path)
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    chapter_content = f.read()
                
                full_content += f"## {chapter_info.title}\n\n{chapter_content}\n\n"
    
    # 保存文件
    if state.format == "markdown":
        output_path = f"{project_dir}/export.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
    elif state.format == "txt":
        output_path = f"{project_dir}/export.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
    else:
        output_path = f"{project_dir}/export.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
    
    return ExportOutput(
        output_path=output_path,
        success=True
    )
