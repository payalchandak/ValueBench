"""Data models for human decision imports and participant tracking.

This module defines the schemas for:
- ParticipantInfo: Individual participant metadata
- ParticipantRegistry: Collection of participants with load/save utilities
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, Field, field_validator

# Simple email regex pattern
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class ParticipantInfo(BaseModel):
    """Metadata about a survey participant.
    
    Stores identifying information and timestamps for when the participant
    was first and last seen in survey imports.
    
    Attributes:
        participant_id: Anonymous ID in format participant_{hash[:8]}
        name: Full name from survey
        email: Validated email address (stored lowercase)
        expertise: Professional expertise/specialty (optional)
        first_seen: Timestamp of first response imported
        last_seen: Timestamp of most recent response imported
    """
    
    participant_id: str = Field(..., description="Anonymous ID (format: participant_{hash[:8]})")
    name: str = Field(..., description="Full name from survey")
    email: str = Field(..., description="Validated email address from survey")
    expertise: str = Field(default="", description="Professional expertise/specialty")
    first_seen: datetime = Field(..., description="Timestamp of first response")
    last_seen: datetime = Field(..., description="Timestamp of most recent response")
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format and normalize to lowercase."""
        if not EMAIL_PATTERN.match(v):
            raise ValueError(f"Invalid email format: {v}")
        return v.lower()
    
    @field_validator("participant_id")
    @classmethod
    def validate_participant_id(cls, v: str) -> str:
        """Validate participant ID format."""
        if not v.startswith("participant_") or len(v) != 20:  # "participant_" + 8 hex chars
            raise ValueError(f"Invalid participant ID format: {v}. Expected: participant_{{hash[:8]}}")
        return v


class ParticipantRegistry(BaseModel):
    """Registry of all known survey participants.
    
    Maintains a mapping of participant IDs to their metadata, supporting
    incremental imports where new participants are added and existing
    participants have their timestamps updated.
    
    The registry is stored as JSON at data/human_decisions/participant_registry.json
    
    Example:
        >>> registry = ParticipantRegistry()
        >>> registry.add_or_update(participant_info)
        >>> registry.save()
        >>> 
        >>> # Later...
        >>> registry = ParticipantRegistry.load()
        >>> info = registry.get("participant_a3f8c2d1")
    """
    
    participants: dict[str, ParticipantInfo] = Field(
        default_factory=dict,
        description="Mapping of participant_id -> ParticipantInfo"
    )
    
    def __len__(self) -> int:
        """Return the number of participants in the registry."""
        return len(self.participants)
    
    def __contains__(self, participant_id: str) -> bool:
        """Check if a participant ID exists in the registry."""
        return participant_id in self.participants
    
    def __iter__(self) -> Iterator[str]:
        """Iterate over participant IDs."""
        return iter(self.participants)
    
    def get(self, participant_id: str) -> ParticipantInfo | None:
        """Get participant info by ID, or None if not found."""
        return self.participants.get(participant_id)
    
    def add_or_update(self, info: ParticipantInfo) -> None:
        """Add a new participant or update an existing one.
        
        If the participant already exists, updates first_seen and last_seen
        timestamps to expand the range if the new info extends it.
        
        Args:
            info: ParticipantInfo to add or merge
        """
        if info.participant_id in self.participants:
            existing = self.participants[info.participant_id]
            # Expand timestamp range
            if info.first_seen < existing.first_seen:
                existing.first_seen = info.first_seen
            if info.last_seen > existing.last_seen:
                existing.last_seen = info.last_seen
            # Update expertise if new one is provided and old one is empty
            if info.expertise and not existing.expertise:
                existing.expertise = info.expertise
        else:
            self.participants[info.participant_id] = info
    
    def save(self, path: str | Path | None = None) -> Path:
        """Save the registry to a JSON file.
        
        Args:
            path: Path to save to. Defaults to data/human_decisions/participant_registry.json
            
        Returns:
            Path where the registry was saved
        """
        if path is None:
            path = self._default_path()
        else:
            path = Path(path)
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to JSON-serializable format
        data = {
            pid: {
                "name": info.name,
                "email": info.email,
                "expertise": info.expertise,
                "first_seen": info.first_seen.isoformat(),
                "last_seen": info.last_seen.isoformat(),
            }
            for pid, info in self.participants.items()
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return path
    
    @classmethod
    def load(cls, path: str | Path | None = None) -> "ParticipantRegistry":
        """Load the registry from a JSON file.
        
        Args:
            path: Path to load from. Defaults to data/human_decisions/participant_registry.json
            
        Returns:
            Loaded ParticipantRegistry, or empty registry if file doesn't exist
        """
        if path is None:
            path = cls._default_path()
        else:
            path = Path(path)
        
        if not path.exists():
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        participants = {}
        for pid, info_dict in data.items():
            participants[pid] = ParticipantInfo(
                participant_id=pid,
                name=info_dict["name"],
                email=info_dict["email"],
                expertise=info_dict.get("expertise", ""),
                first_seen=datetime.fromisoformat(info_dict["first_seen"]),
                last_seen=datetime.fromisoformat(info_dict["last_seen"]),
            )
        
        return cls(participants=participants)
    
    @staticmethod
    def _default_path() -> Path:
        """Get the default path for the participant registry."""
        return Path(__file__).parent.parent.parent / "data" / "human_decisions" / "participant_registry.json"
