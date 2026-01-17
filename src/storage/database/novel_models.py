"""
NovelOS 数据库表定义
包含：
- novel_state_snapshot: 存储NovelState最新快照
- state_events: 记录所有StateDelta、提案合并、回滚事件
"""
from sqlalchemy import BigInteger, DateTime, String, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional

from .shared.model import Base


class NovelStateSnapshot(Base):
    """NovelState 最新快照表"""
    __tablename__ = "novel_state_snapshot"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="项目唯一标识")
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, comment="NovelState完整快照")
    version: Mapped[int] = mapped_column(BigInteger, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    __table_args__ = (
        Index("idx_project_id", "project_id"),
    )


class StateEvent(Base):
    """状态变更事件表"""
    __tablename__ = "state_events"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="项目唯一标识")
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, comment="事件类型：draft/revise/proposal_merge/rollback等")
    version_before: Mapped[int] = mapped_column(BigInteger, comment="变更前版本号")
    version_after: Mapped[int] = mapped_column(BigInteger, comment="变更后版本号")
    state_delta: Mapped[dict] = mapped_column(JSON, comment="状态变更内容（StateDelta）")
    chapter_ref: Mapped[Optional[str]] = mapped_column(String(100), comment="关联章节号")
    scene_ref: Mapped[Optional[str]] = mapped_column(String(100), comment="关联场景ID")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="事件描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    
    __table_args__ = (
        Index("idx_project_id", "project_id"),
        Index("idx_version_after", "version_after"),
    )
