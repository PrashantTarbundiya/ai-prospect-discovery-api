from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Phrase = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Aliases = Annotated[list[Phrase], Field(min_length=1, max_length=10)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Query(StrictModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"query": "Guido van Rossum", "mode": "person"}, {"query": "new Gemini model"}]})
    mode: Literal["discovery", "person"] = "discovery"
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]

    @field_validator("query")
    @classmethod
    def audience_text(cls, value: str) -> str:
        if not any(ch.isalpha() for ch in value):
            raise ValueError("Enter a topic or audience containing at least one letter.")
        return value


class Geography(StrictModel):
    city: Phrase | None
    state: Phrase | None
    country: Phrase | None
    aliases: list[Phrase] = Field(max_length=10, description="Equivalent names for the most specific requested place only.")


class Intent(StrictModel):
    audience: Phrase
    interest: Phrase
    target_type: Literal["individual", "business", "either"]
    location: Geography
    requirements: list[Aliases] = Field(min_length=1, max_length=5, description="All concepts required. Within each group any one phrase is sufficient.")


class Link(StrictModel):
    platform: Literal["Google", "LinkedIn", "X", "YouTube", "Instagram", "Facebook", "Threads", "Email", "Phone", "WhatsApp"]
    link: str


class Prospect(StrictModel):
    name: str
    location: str | None
    social_link: list[Link]
    description: str | None = None


class Discovery(StrictModel):
    success: Literal[True] = True
    query: str
    total_prospects: int
    prospects: list[Prospect]
