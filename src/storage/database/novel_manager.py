"""
NovelOS 数据库管理器
用于读写NovelState、记录StateEvents
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from storage.database.shared.model import Base
from storage.database.novel_models import NovelStateSnapshot, StateEvent


class NovelStateCreate(BaseModel):
    """创建NovelState快照的输入模型"""
    project_id: str = Field(..., description="项目唯一标识")
    snapshot: Dict[str, Any] = Field(..., description="NovelState完整快照")
    version: int = Field(default=1, description="版本号")


class NovelStateUpdate(BaseModel):
    """更新NovelState快照的输入模型"""
    project_id: str = Field(..., description="项目唯一标识")
    snapshot: Dict[str, Any] = Field(..., description="NovelState完整快照")
    version: int = Field(..., description="版本号")


class StateEventCreate(BaseModel):
    """创建状态事件的输入模型"""
    project_id: str = Field(..., description="项目唯一标识")
    event_type: str = Field(..., description="事件类型：draft/revise/proposal_merge/rollback等")
    version_before: int = Field(default=1, description="变更前版本号")
    version_after: int = Field(..., description="变更后版本号")
    state_delta: Dict[str, Any] = Field(..., description="状态变更内容（StateDelta）")
    chapter_ref: Optional[str] = Field(default=None, description="关联章节号")
    scene_ref: Optional[str] = Field(default=None, description="关联场景ID")
    description: str = Field(default="", description="事件描述")


class NovelStateManager:
    """NovelState 管理器"""
    
    def get_snapshot(self, db: Session, project_id: str) -> Optional[NovelStateSnapshot]:
        """获取项目的最新快照"""
        return db.query(NovelStateSnapshot).filter(
            NovelStateSnapshot.project_id == project_id
        ).first()
    
    def create_snapshot(self, db: Session, snapshot_in: NovelStateCreate) -> NovelStateSnapshot:
        """创建新的快照"""
        db_snapshot = NovelStateSnapshot(
            project_id=snapshot_in.project_id,
            snapshot=snapshot_in.snapshot,
            version=snapshot_in.version,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(db_snapshot)
        try:
            db.commit()
            db.refresh(db_snapshot)
            return db_snapshot
        except Exception:
            db.rollback()
            raise
    
    def update_snapshot(self, db: Session, snapshot_in: NovelStateUpdate) -> Optional[NovelStateSnapshot]:
        """更新快照"""
        db_snapshot = self.get_snapshot(db, snapshot_in.project_id)
        if not db_snapshot:
            return None
        
        db_snapshot.snapshot = snapshot_in.snapshot
        db_snapshot.version = snapshot_in.version
        db_snapshot.updated_at = datetime.now()
        
        db.add(db_snapshot)
        try:
            db.commit()
            db.refresh(db_snapshot)
            return db_snapshot
        except Exception:
            db.rollback()
            raise
    
    def create_event(self, db: Session, event_in: StateEventCreate) -> StateEvent:
        """创建状态事件"""
        db_event = StateEvent(
            project_id=event_in.project_id,
            event_type=event_in.event_type,
            version_before=event_in.version_before,
            version_after=event_in.version_after,
            state_delta=event_in.state_delta,
            chapter_ref=event_in.chapter_ref,
            scene_ref=event_in.scene_ref,
            description=event_in.description,
            created_at=datetime.now()
        )
        db.add(db_event)
        try:
            db.commit()
            db.refresh(db_event)
            return db_event
        except Exception:
            db.rollback()
            raise
    
    def get_events(self, db: Session, project_id: str, limit: int = 100) -> List[StateEvent]:
        """获取项目的事件列表"""
        return db.query(StateEvent).filter(
            StateEvent.project_id == project_id
        ).order_by(StateEvent.created_at.desc()).limit(limit).all()
    
    def get_events_by_version(self, db: Session, project_id: str, version_after: int) -> List[StateEvent]:
        """获取指定版本之后的所有事件"""
        return db.query(StateEvent).filter(
            StateEvent.project_id == project_id,
            StateEvent.version_after == version_after
        ).order_by(StateEvent.created_at.desc()).all()
