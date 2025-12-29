"""
Evaluation Store Module

Manages user evaluation sessions with lightweight tracking.
Stores evaluations separately from case files to avoid merge conflicts.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import re

from src.response_models.case import BenchmarkCandidate
from src.response_models.human_evaluation import UserSession
from src.response_models.standalone_evaluation import StandaloneEvaluation


class EvaluationStore:
    """
    Manages evaluation sessions with evaluations stored separately from cases.
    
    Directory structure:
        evaluations/
            sessions/
                session_username.json
            case_evaluations/
                username/
                    case_{uuid}.json
    
    Attributes:
        evaluations_dir: Path to the evaluations storage directory
        sessions_dir: Path to session tracking files
        case_evaluations_dir: Path to per-user evaluation directories
        current_session: Currently active user session
    """
    
    def __init__(self, evaluations_dir: str = "data/evaluations"):
        """
        Initialize the EvaluationStore.
        
        Args:
            evaluations_dir: Path to store evaluation sessions and case evaluations
        """
        self.evaluations_dir = Path(evaluations_dir)
        self.evaluations_dir.mkdir(exist_ok=True, parents=True)
        
        # Create subdirectories
        self.sessions_dir = self.evaluations_dir / "sessions"
        self.sessions_dir.mkdir(exist_ok=True, parents=True)
        
        self.case_evaluations_dir = self.evaluations_dir / "case_evaluations"
        self.case_evaluations_dir.mkdir(exist_ok=True, parents=True)
        
        self.current_session: Optional[UserSession] = None
    
    def _sanitize_username(self, username: str) -> str:
        """Sanitize username for safe filename (should already be valid)."""
        return username.lower()
    
    def _get_session_file_path(self, username: str) -> Path:
        """Get the file path for a user's session."""
        safe_username = self._sanitize_username(username)
        return self.sessions_dir / f"session_{safe_username}.json"
    
    def _get_user_evaluations_dir(self, username: str) -> Path:
        """Get the directory for a user's case evaluations."""
        safe_username = self._sanitize_username(username)
        user_dir = self.case_evaluations_dir / safe_username
        user_dir.mkdir(exist_ok=True, parents=True)
        return user_dir
    
    def _get_evaluation_file_path(self, username: str, case_id: str) -> Path:
        """Get the file path for a specific case evaluation by a user."""
        user_dir = self._get_user_evaluations_dir(username)
        return user_dir / f"case_{case_id}.json"
    
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
        problem_axes: Optional[List[str]] = None,
        comments: Optional[str] = None
    ) -> None:
        """
        Record a case evaluation in a separate file (no modification to case file).
        
        Each user can only evaluate each case once. Evaluations are stored in
        per-user directories to avoid merge conflicts.
        
        Args:
            case_id: ID of the case being evaluated
            decision: "approve" or "reject"
            case_loader: CaseLoader instance to load case data
            problem_axes: Optional list of problem categories (clinical, ethical, legal, stylistic, other)
            comments: Optional detailed feedback and recommended changes
            
        Raises:
            ValueError: If no active session, invalid decision, or already evaluated
            RuntimeError: If case cannot be loaded or saved
        """
        if self.current_session is None:
            raise ValueError("No active session. Call load_or_create_session first.")
        
        if decision not in ["approve", "reject"]:
            raise ValueError(f"Invalid decision: {decision}. Must be 'approve' or 'reject'")
        
        # Check if already evaluated by this user
        eval_file = self._get_evaluation_file_path(
            self.current_session.username,
            case_id
        )
        
        if eval_file.exists():
            raise ValueError(
                f"Case {case_id} has already been evaluated by {self.current_session.username}. "
                f"Re-evaluation is not allowed."
            )
        
        # Load the case record (read-only)
        case_record = case_loader.get_case_by_id(case_id)
        if not case_record:
            raise RuntimeError(f"Case {case_id} not found")
        
        if not case_record.final_case:
            raise RuntimeError(f"Case {case_id} has no final BenchmarkCandidate")
        
        # Get content hash of the case being evaluated
        try:
            content_hash = case_record.compute_content_hash()
        except Exception as e:
            raise RuntimeError(f"Failed to compute content hash: {e}")
        
        try:
            # Create standalone evaluation record
            evaluation = StandaloneEvaluation(
                case_id=case_id,
                case_content_hash=content_hash,
                evaluator=self.current_session.username,
                evaluated_at=datetime.now(),
                decision=decision,
                problem_axes=problem_axes,
                comments=comments
            )
            
            # Save to user's evaluation directory
            with open(eval_file, 'w', encoding='utf-8') as f:
                json.dump(
                    evaluation.model_dump(),
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str
                )
            
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
    
    def get_evaluation(
        self,
        case_id: str,
        evaluator: Optional[str] = None
    ) -> Optional[StandaloneEvaluation]:
        """
        Get the evaluation for a specific case by a specific evaluator.
        
        Args:
            case_id: The case ID
            evaluator: The evaluator's username (defaults to current session user)
            
        Returns:
            StandaloneEvaluation object or None if not found
        """
        if evaluator is None:
            if self.current_session is None:
                return None
            evaluator = self.current_session.username
        
        eval_file = self._get_evaluation_file_path(evaluator, case_id)
        
        if not eval_file.exists():
            return None
        
        try:
            with open(eval_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return StandaloneEvaluation(**data)
        except Exception as e:
            print(f"[Warning] Error loading evaluation from {eval_file.name}: {e}")
            return None
    
    def get_all_evaluations_for_case(self, case_id: str) -> List[StandaloneEvaluation]:
        """
        Get all evaluations for a case across all evaluators.
        
        Args:
            case_id: The case ID
            
        Returns:
            List of StandaloneEvaluation objects
        """
        evaluations = []
        
        # Scan all evaluator directories
        if not self.case_evaluations_dir.exists():
            return evaluations
        
        for evaluator_dir in self.case_evaluations_dir.iterdir():
            if not evaluator_dir.is_dir():
                continue
            
            eval_file = evaluator_dir / f"case_{case_id}.json"
            if eval_file.exists():
                try:
                    with open(eval_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    evaluations.append(StandaloneEvaluation(**data))
                except Exception as e:
                    print(f"[Warning] Error loading evaluation from {eval_file}: {e}")
        
        return evaluations
    
    def get_evaluation_with_case(
        self,
        case_id: str,
        case_loader,
        evaluator: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get evaluation with the case data loaded from case files (read-only).
        
        Args:
            case_id: The case ID
            case_loader: CaseLoader to load case data
            evaluator: The evaluator's username (defaults to current session user)
            
        Returns:
            Dict with 'evaluation' and 'case' keys, or None if not found
        """
        if evaluator is None:
            if self.current_session is None:
                return None
            evaluator = self.current_session.username
        
        # Load evaluation (just metadata)
        evaluation = self.get_evaluation(case_id, evaluator)
        if not evaluation:
            return None
        
        # Load case from source (read-only)
        case_record = case_loader.get_case_by_id(case_id)
        if not case_record:
            return None
        
        # Get the original case (no editing supported)
        case = case_record.final_case
        
        return {
            "evaluation": evaluation,
            "case": case
        }
    
    def get_unreviewed_cases(self, all_case_ids: List[str]) -> List[str]:
        """
        Get list of case IDs that haven't been reviewed yet by current user.
        
        Args:
            all_case_ids: Complete list of all case IDs in the dataset
            
        Returns:
            List of unreviewed case IDs
        """
        if self.current_session is None:
            return all_case_ids
        
        return [cid for cid in all_case_ids if cid not in self.current_session.reviewed_case_ids]
    
    def get_statistics(self, case_loader=None) -> Dict[str, Any]:
        """
        Get evaluation statistics for the current session.
        
        Args:
            case_loader: Not used anymore (kept for backward compatibility)
            
        Returns:
            Dictionary with statistics
        """
        if self.current_session is None:
            return {
                "total_reviewed": 0,
                "approved": 0,
                "rejected": 0,
                # Back-compat: older UIs called this "with_edits"
                "with_feedback": 0,
                "with_edits": 0,
                "problem_axes_summary": {}
            }
        
        approved = 0
        rejected = 0
        with_feedback = 0
        problem_axes_count = {}
        
        for case_id in self.current_session.reviewed_case_ids:
            evaluation = self.get_evaluation(case_id)
            if evaluation:
                if evaluation.decision == 'approve':
                    approved += 1
                elif evaluation.decision == 'reject':
                    rejected += 1
                
                # Count feedback
                if evaluation.comments or evaluation.problem_axes:
                    with_feedback += 1
                
                # Count problem axes
                if evaluation.problem_axes:
                    for axis in evaluation.problem_axes:
                        # Convert enum to string for display
                        axis_str = axis.value if hasattr(axis, 'value') else str(axis)
                        problem_axes_count[axis_str] = problem_axes_count.get(axis_str, 0) + 1
        
        return {
            "total_reviewed": len(self.current_session.reviewed_case_ids),
            "approved": approved,
            "rejected": rejected,
            # Back-compat: older UIs called this "with_edits"
            "with_feedback": with_feedback,
            "with_edits": with_feedback,
            "problem_axes_summary": problem_axes_count
        }
    
    def get_aggregated_statistics(self) -> Dict[str, Any]:
        """
        Get aggregated statistics across all evaluators.
        
        Returns:
            Dictionary with aggregated statistics including inter-rater data
        """
        all_evaluators = []
        total_evaluations = 0
        cases_evaluated = set()
        
        # Scan all evaluator directories
        if self.case_evaluations_dir.exists():
            for evaluator_dir in self.case_evaluations_dir.iterdir():
                if evaluator_dir.is_dir():
                    all_evaluators.append(evaluator_dir.name)
                    eval_files = list(evaluator_dir.glob("case_*.json"))
                    total_evaluations += len(eval_files)
                    for eval_file in eval_files:
                        # Extract case_id from filename
                        case_id = eval_file.stem.replace("case_", "")
                        cases_evaluated.add(case_id)
        
        # Calculate cases with multiple evaluations
        multi_eval_cases = []
        for case_id in cases_evaluated:
            evals = self.get_all_evaluations_for_case(case_id)
            if len(evals) > 1:
                multi_eval_cases.append({
                    'case_id': case_id,
                    'num_evaluations': len(evals),
                    'evaluators': [e.evaluator for e in evals],
                    'decisions': [e.decision for e in evals]
                })
        
        return {
            "num_evaluators": len(all_evaluators),
            "evaluators": all_evaluators,
            "total_evaluations": total_evaluations,
            "unique_cases_evaluated": len(cases_evaluated),
            "cases_with_multiple_evals": len(multi_eval_cases),
            "multi_eval_details": multi_eval_cases
        }
    
    def list_all_sessions(self) -> List[Dict[str, str]]:
        """List all available user sessions."""
        sessions = []
        
        for session_file in self.sessions_dir.glob("session_*.json"):
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
        
        # Get current user's statistics
        stats = store.get_statistics()
        print(f"\nYour Statistics:")
        print(f"  Total reviewed: {stats['total_reviewed']}")
        print(f"  Approved: {stats['approved']}")
        print(f"  Rejected: {stats['rejected']}")
        
        print("\n" + "-" * 80)
        print("\nAll Sessions:")
        for s in store.list_all_sessions():
            print(f"  - {s['username']}: {s['num_evaluations']} evaluations (updated: {s['last_updated'][:19]})")
        
        print("\n" + "-" * 80)
        print("\nAggregated Statistics:")
        agg_stats = store.get_aggregated_statistics()
        print(f"  Total evaluators: {agg_stats['num_evaluators']}")
        print(f"  Evaluators: {', '.join(agg_stats['evaluators'])}")
        print(f"  Total evaluations: {agg_stats['total_evaluations']}")
        print(f"  Unique cases evaluated: {agg_stats['unique_cases_evaluated']}")
        print(f"  Cases with multiple evaluations: {agg_stats['cases_with_multiple_evals']}")
        
        if agg_stats['multi_eval_details']:
            print("\n  Cases with multiple evaluations:")
            for detail in agg_stats['multi_eval_details'][:5]:  # Show first 5
                print(f"    - {detail['case_id'][:12]}... ({detail['num_evaluations']} evals)")
                for evaluator, decision in zip(detail['evaluators'], detail['decisions']):
                    print(f"      • {evaluator}: {decision}")
        
    except ValueError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
