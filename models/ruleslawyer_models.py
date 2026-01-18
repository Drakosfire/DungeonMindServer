from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


RulebookAvailability = Literal["available", "missing_data", "disabled"]
ProgressStage = Literal["embedding", "search", "rerank", "context", "generation", "complete"]


class RulesLawyerStatus(BaseModel):
    embeddingsLoaded: bool = Field(..., description="Whether embeddings are loaded in memory")
    activeRulebookId: Optional[str] = Field(None, description="Currently active rulebook id")


class Rulebook(BaseModel):
    id: str = Field(..., description="Stable rulebook identifier")
    title: str = Field(..., description="Rulebook title")
    availabilityStatus: RulebookAvailability = Field(..., description="Availability status")
    chunkCount: Optional[int] = Field(None, description="Number of chunks in rulebook")
    pageCount: Optional[int] = Field(None, description="Number of pages in rulebook")
    updatedAt: Optional[datetime] = Field(None, description="Last update time")


class RulebookList(BaseModel):
    rulebooks: List[Rulebook] = Field(default_factory=list, description="Available rulebooks")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Chat role")
    content: str = Field(..., description="Chat message content")


class RulesQueryRequest(BaseModel):
    message: str = Field(..., description="User query")
    rulebookId: str = Field(..., description="Active rulebook id")
    chatHistory: List[ChatTurn] = Field(default_factory=list, description="Chat history turns")


class RulebookRefreshRequest(BaseModel):
    rulebookIds: List[str] = Field(..., description="Rulebook ids to refresh")
    reason: Optional[str] = Field(None, description="Optional reason for refresh")


class RulebookRefreshResponse(BaseModel):
    status: Literal["accepted", "completed"] = Field(..., description="Refresh status")
    refreshedRulebooks: List[str] = Field(default_factory=list, description="Rulebooks refreshed")


class Citation(BaseModel):
    source: Optional[str] = Field(None, description="Rulebook source name")
    page: int = Field(..., ge=1, description="Page number")
    section: Optional[str] = Field(None, description="Section heading")
    link: Optional[str] = Field(None, description="Optional deep link")


class SavedRule(BaseModel):
    id: str = Field(..., description="Saved rule id")
    userId: Optional[str] = Field(None, description="User id if authenticated")
    rulebookId: str = Field(..., description="Rulebook id")
    queryText: str = Field(..., description="Original user query")
    responseText: str = Field(..., description="Markdown response text")
    citations: List[Citation] = Field(default_factory=list, description="Citations for the response")
    tags: List[str] = Field(default_factory=list, description="Optional user tags")
    createdAt: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updatedAt: datetime = Field(default_factory=datetime.utcnow, description="Last updated timestamp")


class SaveRuleRequest(BaseModel):
    rulebookId: str = Field(..., description="Rulebook id")
    queryText: str = Field(..., description="Original user query")
    responseText: str = Field(..., description="Markdown response text")
    citations: List[Citation] = Field(default_factory=list, description="Citations for the response")
    tags: List[str] = Field(default_factory=list, description="Optional user tags")


class SavedRuleList(BaseModel):
    rules: List[SavedRule] = Field(default_factory=list, description="Saved rules list")


class RetrievalProgressMetadata(BaseModel):
    chunksSearched: Optional[int] = Field(None, description="Chunks searched")
    matchesFound: Optional[int] = Field(None, description="Matches found")
    topSimilarity: Optional[float] = Field(None, description="Top similarity score")
    processingTimeMs: Optional[int] = Field(None, description="Processing time in ms")
    tokensUsed: Optional[int] = Field(None, description="Tokens used")


class SourceDistribution(BaseModel):
    book: str = Field(..., description="Rulebook name")
    count: int = Field(..., ge=0, description="Match count for rulebook")


class RetrievalProgress(BaseModel):
    stage: ProgressStage = Field(..., description="Pipeline stage")
    message: str = Field(..., description="Progress message")
    metadata: Optional[RetrievalProgressMetadata] = Field(None, description="Optional metadata")
    sources: List[SourceDistribution] = Field(default_factory=list, description="Source distribution")
    emittedAt: datetime = Field(default_factory=datetime.utcnow, description="Event time")
