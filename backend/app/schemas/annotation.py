from __future__ import annotations

from pydantic import BaseModel, Field


class SubGoalDefinitionInput(BaseModel):
    sequenceNo: int
    code: str
    nameEn: str
    nameZh: str = ''
    description: str = ''
    actionVerb: str = ''
    isRequired: bool = False
    isConditional: bool = False
    maxOccurrences: int | None = None
    objectRoleHints: dict = Field(default_factory=dict)


class SubGoalSchemaCreateRequest(BaseModel):
    taskTypeId: str
    definitions: list[SubGoalDefinitionInput] = Field(default_factory=list)


class AnnotationTaskEnsureRequest(BaseModel):
    episodeIds: list[str] = Field(default_factory=list)
    taskTypeId: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class AnnotationGenerationEnqueueRequest(BaseModel):
    taskIds: list[str] = Field(default_factory=list)
    taskTypeId: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    priority: int = Field(default=50, ge=1, le=1000)


class AnnotationAssignmentRequest(BaseModel):
    reviewerId: str
    note: str = ''


class AnnotationPublicClaimRequest(BaseModel):
    enabled: bool


class AnnotationDraftRequest(BaseModel):
    rowVersion: int = Field(ge=1)
    canonicalInstructionEn: str = ''
    canonicalInstructionZh: str | None = None
    instructionVariantsEn: list[str] = Field(default_factory=list)
    episodeSummary: str | None = None
    objects: list = Field(default_factory=list)
    taskOutcome: str | None = None
    failureSubGoalInstanceId: int | None = None
    lastSuccessfulSubGoalInstanceId: int | None = None
    failureReason: str | None = None
    annotationNotes: str | None = None
    occurrences: list[dict] = Field(default_factory=list)


class AnnotationLockResponse(BaseModel):
    taskId: str
    lockOwner: str | None
    lockExpiresAt: str | None
    rowVersion: int


class AnnotationTaskListResponse(BaseModel):
    items: list[dict]
    page: int
    pageSize: int
    total: int


class AnnotationSchemaResponse(BaseModel):
    id: str
    taskTypeId: str
    versionNo: int
    status: str
    contentHash: str
    definitions: list[dict]
    createdAt: str
    publishedAt: str | None
