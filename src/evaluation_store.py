"""
Evaluation Store Module

Manages user evaluation sessions with persistent storage.
Tracks which cases users have reviewed, their decisions (approve/reject),
and any edits they've made.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import re


@dataclass
class CaseEvaluation:
    """Record of a single case evaluation."""
    case_id: str
    evaluated_at: str
    decision: str  # "approve", "reject", or "pending"
    original_vignette: str
    edited_vignette: Optional[str] = None
    original_choice_1: Optional[str] = None
    edited_choice_1: Optional[str] = None
    original_choice_2: Optional[str] = None
    edited_choice_2: Optional[str] = None
    notes: Optional[str] = None
    
    def has_edits(self) -> bool:
        """Check if any edits were made."""
        return (
            self.edited_vignette is not None or
            self.edited_choice_1 is not None or
            self.edited_choice_2 is not None
        )


@dataclass
class UserSession:
    """User evaluation session data."""
    user_email: str
    session_id: str
    started_at: str
    last_updated: str
    evaluations: Dict[str, CaseEvaluation]  # case_id -> CaseEvaluation
    
    def get_reviewed_case_ids(self) -> List[str]:
        """Get list of all reviewed case IDs."""
        return list(self.evaluations.keys())
    
    def get_approved_cases(self) -> List[CaseEvaluation]:
        """Get all approved case evaluations."""
        return [e for e in self.evaluations.values() if e.decision == "approve"]
    
    def get_rejected_cases(self) -> List[CaseEvaluation]:
        """Get all rejected case evaluations."""
        return [e for e in self.evaluations.values() if e.decision == "reject"]
    
    def get_pending_cases(self) -> List[CaseEvaluation]:
        """Get all pending case evaluations."""
        return [e for e in self.evaluations.values() if e.decision == "pending"]
    
    def get_cases_with_edits(self) -> List[CaseEvaluation]:
        """Get all cases that have edits."""
        return [e for e in self.evaluations.values() if e.has_edits()]


class EvaluationStore:
    """
    Manages persistent storage of user evaluation sessions.
    
    Attributes:
        evaluations_dir: Path to the evaluations storage directory
        current_session: Currently active user session
    """
    
    def __init__(self, evaluations_dir: str = "data/evaluations"):
        """
        Initialize the EvaluationStore.
        
        Args:
            evaluations_dir: Path to store evaluation sessions
        """
        self.evaluations_dir = Path(evaluations_dir)
        self.evaluations_dir.mkdir(exist_ok=True, parents=True)
        self.current_session: Optional[UserSession] = None
    
    def _sanitize_email(self, email: str) -> str:
        """Convert email to a safe filename."""
        # Replace @ and . with underscores, remove other special chars
        safe_name = re.sub(r'[^\w\-.]', '_', email.lower())
        return safe_name
    
    def _get_session_file_path(self, email: str) -> Path:
        """Get the file path for a user's session."""
        safe_email = self._sanitize_email(email)
        return self.evaluations_dir / f"session_{safe_email}.json"
    
    def load_or_create_session(self, user_email: str) -> UserSession:
        """
        Load an existing session or create a new one.
        
        Args:
            user_email: User's email address
            
        Returns:
            UserSession object
        """
        if not self._validate_email(user_email):
            raise ValueError(f"Invalid email format: {user_email}")
        
        session_file = self._get_session_file_path(user_email)
        
        if session_file.exists():
            session = self._load_session_from_file(session_file)
            session.last_updated = datetime.now().isoformat()
            print(f"✓ Loaded existing session for {user_email}")
            print(f"  - {len(session.evaluations)} cases previously reviewed")
        else:
            session = self._create_new_session(user_email)
            print(f"✓ Created new session for {user_email}")
        
        self.current_session = session
        return session
    
    def _validate_email(self, email: str) -> bool:
        """Basic email validation."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def _create_new_session(self, user_email: str) -> UserSession:
        """Create a new user session."""
        now = datetime.now().isoformat()
        session_id = f"{self._sanitize_email(user_email)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return UserSession(
            user_email=user_email,
            session_id=session_id,
            started_at=now,
            last_updated=now,
            evaluations={}
        )
    
    def _load_session_from_file(self, file_path: Path) -> UserSession:
        """Load a session from JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert evaluation dicts back to CaseEvaluation objects
        evaluations = {}
        for case_id, eval_data in data.get('evaluations', {}).items():
            evaluations[case_id] = CaseEvaluation(**eval_data)
        
        return UserSession(
            user_email=data['user_email'],
            session_id=data['session_id'],
            started_at=data['started_at'],
            last_updated=data['last_updated'],
            evaluations=evaluations
        )
    
    def save_session(self, session: Optional[UserSession] = None) -> None:
        """
        Save the current or specified session to disk.
        
        Args:
            session: Session to save (defaults to current_session)
        """
        if session is None:
            session = self.current_session
        
        if session is None:
            raise ValueError("No session to save")
        
        session.last_updated = datetime.now().isoformat()
        session_file = self._get_session_file_path(session.user_email)
        
        # Convert to dict for JSON serialization
        session_dict = {
            'user_email': session.user_email,
            'session_id': session.session_id,
            'started_at': session.started_at,
            'last_updated': session.last_updated,
            'evaluations': {
                case_id: asdict(evaluation)
                for case_id, evaluation in session.evaluations.items()
            }
        }
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_dict, f, indent=2, ensure_ascii=False)
    
    def add_evaluation(
        self,
        case_id: str,
        decision: str,
        original_vignette: str,
        original_choice_1: Optional[str] = None,
        original_choice_2: Optional[str] = None,
        edited_vignette: Optional[str] = None,
        edited_choice_1: Optional[str] = None,
        edited_choice_2: Optional[str] = None,
        notes: Optional[str] = None
    ) -> None:
        """
        Add or update a case evaluation in the current session.
        
        Args:
            case_id: ID of the case being evaluated
            decision: "approve", "reject", or "pending"
            original_vignette: Original vignette text
            original_choice_1: Original choice 1 text
            original_choice_2: Original choice 2 text
            edited_vignette: Edited vignette (if changed)
            edited_choice_1: Edited choice 1 (if changed)
            edited_choice_2: Edited choice 2 (if changed)
            notes: Optional notes about the evaluation
        """
        if self.current_session is None:
            raise ValueError("No active session. Call load_or_create_session first.")
        
        if decision not in ["approve", "reject", "pending"]:
            raise ValueError(f"Invalid decision: {decision}. Must be 'approve', 'reject', or 'pending'")
        
        evaluation = CaseEvaluation(
            case_id=case_id,
            evaluated_at=datetime.now().isoformat(),
            decision=decision,
            original_vignette=original_vignette,
            edited_vignette=edited_vignette,
            original_choice_1=original_choice_1,
            edited_choice_1=edited_choice_1,
            original_choice_2=original_choice_2,
            edited_choice_2=edited_choice_2,
            notes=notes
        )
        
        self.current_session.evaluations[case_id] = evaluation
        self.save_session()
    
    def has_reviewed(self, case_id: str) -> bool:
        """Check if a case has been reviewed in the current session."""
        if self.current_session is None:
            return False
        return case_id in self.current_session.evaluations
    
    def get_evaluation(self, case_id: str) -> Optional[CaseEvaluation]:
        """Get the evaluation for a specific case."""
        if self.current_session is None:
            return None
        return self.current_session.evaluations.get(case_id)
    
    def get_unreviewed_cases(self, all_case_ids: List[str]) -> List[str]:
        """
        Get list of case IDs that haven't been reviewed yet.
        
        Args:
            all_case_ids: Complete list of all case IDs in the dataset
            
        Returns:
            List of unreviewed case IDs
        """
        if self.current_session is None:
            return all_case_ids
        
        reviewed = set(self.current_session.get_reviewed_case_ids())
        return [cid for cid in all_case_ids if cid not in reviewed]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get evaluation statistics for the current session."""
        if self.current_session is None:
            return {
                "total_reviewed": 0,
                "approved": 0,
                "rejected": 0,
                "pending": 0,
                "with_edits": 0
            }
        
        return {
            "total_reviewed": len(self.current_session.evaluations),
            "approved": len(self.current_session.get_approved_cases()),
            "rejected": len(self.current_session.get_rejected_cases()),
            "pending": len(self.current_session.get_pending_cases()),
            "with_edits": len(self.current_session.get_cases_with_edits())
        }
    
    def list_all_sessions(self) -> List[Dict[str, str]]:
        """List all available user sessions."""
        sessions = []
        
        for session_file in self.evaluations_dir.glob("session_*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    sessions.append({
                        'email': data.get('user_email', 'unknown'),
                        'session_id': data.get('session_id', 'unknown'),
                        'started_at': data.get('started_at', 'unknown'),
                        'last_updated': data.get('last_updated', 'unknown'),
                        'num_evaluations': len(data.get('evaluations', {}))
                    })
            except Exception as e:
                print(f"Warning: Could not load {session_file.name}: {e}")
        
        return sorted(sessions, key=lambda x: x['last_updated'], reverse=True)


def main():
    """CLI utility for testing the EvaluationStore."""
    import sys
    
    store = EvaluationStore()
    
    # Test email prompt
    print("\nEvaluation Store Test")
    print("-" * 80)
    
    if len(sys.argv) > 1:
        email = sys.argv[1]
    else:
        email = input("Enter your email: ").strip()
    
    try:
        session = store.load_or_create_session(email)
        
        print(f"\nSession Info:")
        print(f"  Email: {session.user_email}")
        print(f"  Session ID: {session.session_id}")
        print(f"  Started: {session.started_at}")
        
        stats = store.get_statistics()
        print(f"\nStatistics:")
        print(f"  Total reviewed: {stats['total_reviewed']}")
        print(f"  Approved: {stats['approved']}")
        print(f"  Rejected: {stats['rejected']}")
        print(f"  Pending: {stats['pending']}")
        print(f"  With edits: {stats['with_edits']}")
        
        print("\n" + "-" * 80)
        print("\nAll Sessions:")
        for s in store.list_all_sessions():
            print(f"  - {s['email']}: {s['num_evaluations']} evaluations (updated: {s['last_updated'][:19]})")
        
    except ValueError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

