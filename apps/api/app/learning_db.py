from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utc_now


class ChannelLearningSnapshotORM(Base):
    __tablename__ = 'channel_learning_snapshots'
    __table_args__ = (UniqueConstraint('project_id', 'idempotency_key_hash', name='uq_learning_project_key'),
        Index('ix_learning_workspace_created', 'workspace_id', 'created_at'))
    learning_snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'))
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'))
    publication_id: Mapped[str] = mapped_column(String(64), ForeignKey('publications.publication_id', ondelete='RESTRICT'))
    anchor_snapshot_id: Mapped[str] = mapped_column(String(64), ForeignKey('analytics_metric_snapshots.snapshot_id', ondelete='RESTRICT'))
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
