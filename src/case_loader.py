"""
Case Loader Module

Responsible for scanning and loading case JSON files from the dataset directory.
Handles file discovery, JSON parsing, and basic validation.
"""

import json
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from src.response_models.record import CaseRecord


@dataclass
class CaseMetadata:
    """Lightweight metadata for quick preview (useful for UI lists)."""
    case_id: str
    file_path: Path
    created_at: str
    version: str
    status: str
    vignette_preview: Optional[str] = None


class CaseLoader:
    """
    Loads and manages case files from the dataset directory.
    
    Attributes:
        cases_dir: Path to the directory containing case JSON files
    """
    
    def __init__(self, cases_dir: str = "data/cases"):
        """
        Initialize the CaseLoader.
        
        Args:
            cases_dir: Path to the cases directory (relative or absolute)
        """
        self.cases_dir = Path(cases_dir)
        
        if not self.cases_dir.exists():
            raise RuntimeError(f"Cases directory not found: {self.cases_dir}")
        
        if not self.cases_dir.is_dir():
            raise RuntimeError(f"Cases path is not a directory: {self.cases_dir}")
    
    def scan_cases(self) -> List[Path]:
        """
        Scan the cases directory for JSON files.
        
        Returns:
            List of Path objects for case JSON files
        """
        json_files = list(self.cases_dir.glob("case_*.json"))
        return sorted(json_files, key=lambda p: p.stat().st_mtime, reverse=True)
    
    def load_case(self, file_path: Path) -> CaseRecord:
        """
        Load a case file and parse it into a CaseRecord.
        
        Args:
            file_path: Path to the case JSON file
            
        Returns:
            CaseRecord object with full case data
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return CaseRecord(**data)
        
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in {file_path.name}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error loading {file_path.name}: {e}")
    
    def load_case_metadata(self, file_path: Path) -> Optional[CaseMetadata]:
        """
        Load minimal metadata for quick preview without full parsing.
        
        Args:
            file_path: Path to the case JSON file
            
        Returns:
            CaseMetadata object or None if loading fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Get vignette preview from final iteration
            vignette_preview = None
            if data.get('refinement_history'):
                last_iteration = data['refinement_history'][-1]
                vignette = last_iteration.get('data', {}).get('vignette', '')
                if vignette:
                    vignette_preview = vignette[:100] + "..." if len(vignette) > 100 else vignette
            
            return CaseMetadata(
                case_id=data.get('case_id', 'unknown'),
                file_path=file_path,
                created_at=data.get('created_at', 'unknown'),
                version=data.get('version', '1.0'),
                status=data.get('status', 'unknown'),
                vignette_preview=vignette_preview
            )
        
        except Exception as e:
            print(f"[Warning] Error loading metadata from {file_path.name}: {e}")
            return None
    
    def get_all_cases(self) -> List[CaseRecord]:
        """
        Load all cases as full CaseRecord objects.
        
        Returns:
            List of CaseRecord objects
        """
        case_files = self.scan_cases()
        cases = []
        
        for file_path in case_files:
            try:
                case = self.load_case(file_path)
                cases.append(case)
            except RuntimeError as e:
                print(f"[Warning] {e}")
        
        return cases
    
    def get_all_metadata(self) -> List[CaseMetadata]:
        """
        Get lightweight metadata for all cases (faster for UI lists).
        
        Returns:
            List of CaseMetadata objects
        """
        case_files = self.scan_cases()
        metadata = []
        
        for file_path in case_files:
            meta = self.load_case_metadata(file_path)
            if meta:
                metadata.append(meta)
        
        return metadata
    
    def get_case_by_id(self, case_id: str) -> Optional[CaseRecord]:
        """
        Load a specific case by its ID.
        
        Args:
            case_id: The case_id to search for
            
        Returns:
            CaseRecord object or None if not found
        """
        for file_path in self.scan_cases():
            try:
                case = self.load_case(file_path)
                if case.case_id == case_id:
                    return case
            except RuntimeError:
                continue
        
        return None
    
    def get_active_cases(self) -> List[CaseRecord]:
        """
        Load all cases with status='active'.
        
        Returns:
            List of active CaseRecord objects
        """
        all_cases = self.get_all_cases()
        return [c for c in all_cases if c.status == "active"]
    
    def get_cases_by_status(self, status: str) -> List[CaseRecord]:
        """
        Load all cases with a specific status.
        
        Args:
            status: Status to filter by ('active', 'deprecated', 'deleted', etc.)
            
        Returns:
            List of CaseRecord objects with that status
        """
        all_cases = self.get_all_cases()
        return [c for c in all_cases if c.status == status]
    
    def save_case(self, case_record: CaseRecord, overwrite_existing: bool = True) -> Path:
        """
        Save a case record using content-addressable filename: case_{uuid}_{hash}.json
        
        Args:
            case_record: The CaseRecord to save
            overwrite_existing: If True, overwrites/renames existing file with same case_id
            
        Returns:
            Path to the saved file
            
        Raises:
            RuntimeError: If file exists and overwrite_existing is False
        """
        # Compute content hash for filename
        try:
            content_hash = case_record.compute_content_hash()
        except ValueError:
            # Fallback for cases without final_case (drafts)
            content_hash = "draft"
        
        # Find existing file with this case_id
        existing_file = None
        for file_path in self.scan_cases():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('case_id') == case_record.case_id:
                        existing_file = file_path
                        break
            except Exception:
                continue
        
        # Generate new filename with content hash
        filename = f"case_{case_record.case_id}_{content_hash}.json"
        new_file_path = self.cases_dir / filename
        
        # Handle existing file
        if existing_file:
            if not overwrite_existing:
                raise RuntimeError(
                    f"Case {case_record.case_id} already exists at {existing_file}. "
                    f"Set overwrite_existing=True to update it."
                )
        
        # Save with proper JSON encoding (write first, then delete old file)
        try:
            with open(new_file_path, 'w', encoding='utf-8') as f:
                json.dump(case_record.model_dump(), f, indent=2, ensure_ascii=False, default=str)
            
            # Only delete old file after successful write
            if existing_file and existing_file != new_file_path:
                existing_file.unlink()
            
            return new_file_path
        except Exception as e:
            raise RuntimeError(f"Error saving case to {new_file_path}: {e}")


def main():
    """CLI utility for testing the CaseLoader."""
    import sys
    
    # Default to data/cases or accept command line argument
    cases_dir = sys.argv[1] if len(sys.argv) > 1 else "data/cases"
    
    try:
        loader = CaseLoader(cases_dir)
        cases = loader.get_all_cases()
        
        print(f"\n✓ Found {len(cases)} cases in {loader.cases_dir}")
        print("\nCases:")
        print("-" * 80)
        
        for i, case in enumerate(cases, 1):
            print(f"\n{i}. Case ID: {case.case_id}")
            print(f"   Created: {case.created_at}")
            print(f"   Status: {case.status}")
            print(f"   Model: {case.model_name}")
            print(f"   Iterations: {len(case.refinement_history)}")
            
            # Show final case if available
            final = case.final_case
            if final:
                preview = final.vignette[:100] + "..." if len(final.vignette) > 100 else final.vignette
                print(f"   Vignette: {preview}")
        
        print("\n" + "-" * 80)
        
    except RuntimeError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

