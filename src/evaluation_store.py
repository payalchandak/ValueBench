"""
Evaluation Store Module

Manages user evaluation sessions with lightweight tracking.
The CaseRecord is the source of truth for evaluation data.
This store only tracks which cases each user has reviewed.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import re

from src.response_models.case import BenchmarkCandidate
from src.response_models.human_evaluation import CaseEvaluation, UserSession


class EvaluationStore:
    """
    Manages lightweight tracking of user evaluation sessions.
    
    CaseRecord is the source of truth for evaluation data.
    This store only tracks which cases each user has reviewed.
    
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
    
    def _sanitize_username(self, username: str) -> str:
        """Sanitize username for safe filename (should already be valid)."""
        # Username should already be lowercase letters only, but ensure it's safe
        return username.lower()
    
    def _get_session_file_path(self, username: str) -> Path:
        """Get the file path for a user's session."""
        safe_username = self._sanitize_username(username)
        return self.evaluations_dir / f"session_{safe_username}.json"
    
    def load_or_create_session(self, username: str) -> UserSession:
        """
        Load an existing session or create a new one.
        
        Args:
            username: User's username (lowercase letters only)
            
        Returns:
            UserSession object
        """
        if not self._validate_username(username):
            raise ValueError(f"Invalid username format: {username}. Username must contain only lowercase letters.")
        
        session_file = self._get_session_file_path(username)
        
        if session_file.exists():
            session = self._load_session_from_file(session_file)
            session.last_updated = datetime.now().isoformat()
            print(f"✓ Loaded existing session for {username}")
            print(f"  - {len(session.reviewed_case_ids)} cases previously reviewed")
        else:
            session = self._create_new_session(username)
            print(f"✓ Created new session for {username}")
        
        self.current_session = session
        return session
    
    def _validate_username(self, username: str) -> bool:
        """Validate username contains only lowercase letters."""
        pattern = r'^[a-z]+$'
        return re.match(pattern, username) is not None
    
    def _create_new_session(self, username: str) -> UserSession:
        """Create a new user session."""
        now = datetime.now().isoformat()
        session_id = f"{self._sanitize_username(username)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return UserSession(
            username=username,
            session_id=session_id,
            started_at=now,
            last_updated=now,
            reviewed_case_ids=set()
        )
    
    def _load_session_from_file(self, file_path: Path) -> UserSession:
        """Load a session from JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return UserSession(
            username=data['username'],
            session_id=data['session_id'],
            started_at=data['started_at'],
            last_updated=data['last_updated'],
            reviewed_case_ids=set(data.get('reviewed_case_ids', []))
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
        session_file = self._get_session_file_path(session.username)
        
        # Convert to dict for JSON serialization
        session_dict = {
            'username': session.username,
            'session_id': session.session_id,
            'started_at': session.started_at,
            'last_updated': session.last_updated,
            'reviewed_case_ids': list(session.reviewed_case_ids)
        }
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_dict, f, indent=2, ensure_ascii=False)
    
    def record_evaluation(
        self,
        case_id: str,
        decision: str,
        case_loader,  # CaseLoader instance
        updated_case: Optional[BenchmarkCandidate] = None,
        notes: Optional[str] = None
    ) -> None:
        """
        Record a case evaluation by updating the CaseRecord and tracking in session.
        
        Args:
            case_id: ID of the case being evaluated
            decision: "approve" or "reject"
            case_loader: CaseLoader instance to load/save case records
            updated_case: Optional edited BenchmarkCandidate
            notes: Optional evaluation notes
            
        Raises:
            ValueError: If no active session or invalid decision
            RuntimeError: If case cannot be loaded or saved
        """
        if self.current_session is None:
            raise ValueError("No active session. Call load_or_create_session first.")
        
        if decision not in ["approve", "reject"]:
            raise ValueError(f"Invalid decision: {decision}. Must be 'approve' or 'reject'")
        
        # Load the case record (source of truth)
        case_record = case_loader.get_case_by_id(case_id)
        if not case_record:
            raise RuntimeError(f"Case {case_id} not found")
        
        try:
            # Add evaluation to the case record
            case_record.add_human_evaluation(
                decision=decision,
                evaluator=self.current_session.username,
                updated_case=updated_case,
                notes=notes
            )
            
            # Save the updated case record
            case_loader.save_case(case_record)
            
            # Track in session (lightweight)
            self.current_session.reviewed_case_ids.add(case_id)
            self.save_session()
            
        except Exception as e:
            # If anything fails, don't track in session
            raise RuntimeError(f"Failed to record evaluation: {e}")
    
    def has_reviewed(self, case_id: str) -> bool:
        """Check if a case has been reviewed in the current session."""
        if self.current_session is None:
            return False
        return case_id in self.current_session.reviewed_case_ids
    
    def get_evaluation(self, case_id: str, case_loader) -> Optional[CaseEvaluation]:
        """
        Get the evaluation for a specific case by loading from CaseRecord.
        
        Args:
            case_id: The case ID
            case_loader: CaseLoader instance
            
        Returns:
            CaseEvaluation view object or None if not evaluated
        """
        case_record = case_loader.get_case_by_id(case_id)
        if not case_record:
            return None
        
        eval_data = case_record.get_latest_evaluation()
        if not eval_data:
            return None
        
        # Reconstruct evaluation from case record
        # Find the original (pre-evaluation) case by looking for the last non-evaluation iteration
        eval_iteration = eval_data['iteration']
        original_case = None
        
        # Look backwards from the evaluation iteration to find the last non-evaluation case
        for i in range(eval_iteration - 1, -1, -1):
            if i < len(case_record.refinement_history):
                iteration_record = case_record.refinement_history[i]
                if iteration_record.step_description != "human_evaluation":
                    original_case = iteration_record.data
                    break
        
        # If no pre-evaluation case found, use the first iteration
        if original_case is None and len(case_record.refinement_history) > 0:
            original_case = case_record.refinement_history[0].data
        
        # Current case (possibly edited) from the evaluation iteration
        current_case = case_record.refinement_history[eval_iteration].data if eval_iteration < len(case_record.refinement_history) else case_record.final_case
        
        # Determine if edited
        updated_case = None
        if eval_data.get('has_edits'):
            updated_case = current_case
        
        return CaseEvaluation(
            case_id=case_id,
            evaluated_at=eval_data['evaluated_at'],
            decision=eval_data['decision'],
            evaluator=eval_data['evaluator'],
            original_case=original_case if isinstance(original_case, BenchmarkCandidate) else current_case,
            updated_case=updated_case,
            notes=eval_data.get('notes')
        )
    
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
        
        return [cid for cid in all_case_ids if cid not in self.current_session.reviewed_case_ids]
    
    def get_statistics(self, case_loader) -> Dict[str, Any]:
        """
        Get evaluation statistics for the current session.
        
        Args:
            case_loader: CaseLoader instance to load case records
            
        Returns:
            Dictionary with statistics
        """
        if self.current_session is None:
            return {
                "total_reviewed": 0,
                "approved": 0,
                "rejected": 0,
                "with_edits": 0
            }
        
        approved = 0
        rejected = 0
        with_edits = 0
        
        for case_id in self.current_session.reviewed_case_ids:
            case_record = case_loader.get_case_by_id(case_id)
            if case_record:
                eval_data = case_record.get_latest_evaluation()
                if eval_data:
                    if eval_data['decision'] == 'approve':
                        approved += 1
                    elif eval_data['decision'] == 'reject':
                        rejected += 1
                    if eval_data.get('has_edits'):
                        with_edits += 1
        
        return {
            "total_reviewed": len(self.current_session.reviewed_case_ids),
            "approved": approved,
            "rejected": rejected,
            "with_edits": with_edits
        }
    
    def list_all_sessions(self) -> List[Dict[str, str]]:
        """List all available user sessions."""
        sessions = []
        
        for session_file in self.evaluations_dir.glob("session_*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    sessions.append({
                        'username': data.get('username', 'unknown'),
                        'session_id': data.get('session_id', 'unknown'),
                        'started_at': data.get('started_at', 'unknown'),
                        'last_updated': data.get('last_updated', 'unknown'),
                        'num_evaluations': len(data.get('reviewed_case_ids', []))
                    })
            except Exception as e:
                print(f"Warning: Could not load {session_file.name}: {e}")
        
        return sorted(sessions, key=lambda x: x['last_updated'], reverse=True)


def main():
    """CLI utility for testing the EvaluationStore."""
    import sys
    from src.case_loader import CaseLoader
    
    store = EvaluationStore()
    
    # Test username prompt
    print("\nEvaluation Store Test")
    print("-" * 80)
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("Enter your username (lowercase letters only): ").strip()
    
    try:
        session = store.load_or_create_session(username)
        
        print(f"\nSession Info:")
        print(f"  Username: {session.username}")
        print(f"  Session ID: {session.session_id}")
        print(f"  Started: {session.started_at}")
        
        # Load case loader for statistics
        try:
            case_loader = CaseLoader()
            stats = store.get_statistics(case_loader)
            print(f"\nStatistics:")
            print(f"  Total reviewed: {stats['total_reviewed']}")
            print(f"  Approved: {stats['approved']}")
            print(f"  Rejected: {stats['rejected']}")
            print(f"  With edits: {stats['with_edits']}")
        except Exception as e:
            print(f"\nNote: Could not load statistics: {e}")
        
        print("\n" + "-" * 80)
        print("\nAll Sessions:")
        for s in store.list_all_sessions():
            print(f"  - {s['username']}: {s['num_evaluations']} evaluations (updated: {s['last_updated'][:19]})")
        
    except ValueError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

