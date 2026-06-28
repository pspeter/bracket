from pydantic import BaseModel, Field


class TournamentIssueEntry(BaseModel):
    type: str
    count: int = Field(ge=1)
