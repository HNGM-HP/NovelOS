"""
NovelOS 主图编排
实现Router + 7个分支的DAG结构
"""
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from graphs.state import (
    GlobalState,
    GraphInput,
    GraphOutput
)
from graphs.node import (
    # 意图识别节点
    intent_router_node,
    
    # 一致性检查入口节点
    consistency_check_entry_node,

    # 新书创建流程节点
    collect_project_info_node,
    generate_style_bible_node,
    init_novel_state_node,
    generate_outline_node,
    init_scene_queue_node,

    # 场景写作流程节点
    pick_scene_node,
    build_context_pack_node,
    draft_scene_node,
    commit_state_node,
    consistency_check_draft_node,

    # 改稿流程节点
    select_revise_mode_node,
    generate_revise_plan_node,
    apply_revision_node,
    save_version_node,
    consistency_check_revise_node,

    # 提案审批流程节点
    list_proposals_node,
    merge_proposals_node,

    # 查询设定流程节点
    query_setting_node,

    # 导出流程节点
    export_node
)


# ==================== 条件判断函数 ====================

def route_intent(state: GlobalState) -> str:
    """
    title: 意图路由
    desc: 根据意图识别结果路由到不同的分支
    """
    intent = state.intent
    
    if intent == "new_project":
        return "新书创建"
    elif intent == "write_next":
        return "场景写作"
    elif intent == "revise":
        return "改稿"
    elif intent == "check_consistency":
        return "一致性检查"
    elif intent == "query_setting":
        return "查询设定"
    elif intent == "approve_proposals":
        return "提案审批"
    elif intent == "export":
        return "导出"
    else:
        return "默认响应"


# 创建状态图
builder = StateGraph(GlobalState, input_schema=GraphInput, output_schema=GraphOutput)

# ===== 添加意图识别节点 =====
builder.add_node("intent_router", intent_router_node, 
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})

# ===== 一致性检查入口节点 =====
builder.add_node("consistency_check_entry", consistency_check_entry_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})

# ===== 新书创建流程 =====
builder.add_node("collect_project_info", collect_project_info_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("generate_style_bible", generate_style_bible_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("init_novel_state", init_novel_state_node)
builder.add_node("generate_outline", generate_outline_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("init_scene_queue", init_scene_queue_node)

# ===== 场景写作流程 =====
builder.add_node("pick_scene", pick_scene_node)
builder.add_node("build_context_pack", build_context_pack_node)
builder.add_node("draft_scene", draft_scene_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("commit_state", commit_state_node)
builder.add_node("consistency_check_draft", consistency_check_draft_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})

# ===== 改稿流程 =====
builder.add_node("select_revise_mode", select_revise_mode_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("generate_revise_plan", generate_revise_plan_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("apply_revision", apply_revision_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})
builder.add_node("save_version", save_version_node)
builder.add_node("consistency_check_revise", consistency_check_revise_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})

# ===== 提案审批流程 =====
builder.add_node("list_proposals", list_proposals_node)
builder.add_node("merge_proposals", merge_proposals_node)

# ===== 查询设定流程 =====
builder.add_node("query_setting", query_setting_node,
                 metadata={"type": "agent", "llm_cfg": "config/intent_router_llm_cfg.json"})

# ===== 导出流程 =====
builder.add_node("export", export_node)

# ===== 设置入口点 =====
builder.set_entry_point("intent_router")

# ===== 添加条件分支 =====
builder.add_conditional_edges(
    source="intent_router",
    path=route_intent,
    path_map={
        "新书创建": "collect_project_info",
        "场景写作": "pick_scene",
        "改稿": "select_revise_mode",
        "一致性检查": "consistency_check_entry",
        "查询设定": "query_setting",
        "提案审批": "list_proposals",
        "导出": "export",
        "默认响应": END
    }
)

# ===== 新书创建流程的边 =====
builder.add_edge("collect_project_info", "generate_style_bible")
builder.add_edge("generate_style_bible", "init_novel_state")
builder.add_edge("init_novel_state", "generate_outline")
builder.add_edge("generate_outline", "init_scene_queue")
builder.add_edge("init_scene_queue", END)

# ===== 场景写作流程的边 =====
builder.add_edge("pick_scene", "build_context_pack")
builder.add_edge("build_context_pack", "draft_scene")
builder.add_edge("draft_scene", "commit_state")
builder.add_edge("commit_state", "consistency_check_draft")
builder.add_edge("consistency_check_draft", END)

# ===== 改稿流程的边 =====
builder.add_edge("select_revise_mode", "generate_revise_plan")
builder.add_edge("generate_revise_plan", "apply_revision")
builder.add_edge("apply_revision", "save_version")
builder.add_edge("save_version", "consistency_check_revise")
builder.add_edge("consistency_check_revise", END)

# ===== 提案审批流程的边 =====
builder.add_edge("list_proposals", "merge_proposals")
builder.add_edge("merge_proposals", END)

# ===== 查询设定流程的边 =====
builder.add_edge("query_setting", END)

# ===== 导出流程的边 =====
builder.add_edge("export", END)

# ===== 一致性检查入口的边 =====
builder.add_edge("consistency_check_entry", END)

# 编译图
main_graph = builder.compile()
