#!/usr/bin/env python3
"""
GUI Application for Case Evaluation

A Gradio-based interface for evaluating cases with editing capabilities.
Works both locally and can be deployed on HuggingFace Spaces.
"""

import os
import gradio as gr
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

from src.case_loader import CaseLoader
from src.evaluation_store import EvaluationStore
from src.response_models.case import BenchmarkCandidate, ChoiceWithValues


class CaseEvaluatorGUI:
    """Main GUI application for case evaluation."""
    
    def __init__(self, cases_dir: str = "data/cases", evaluations_dir: str = "data/evaluations"):
        """Initialize the GUI application."""
        self.loader = CaseLoader(cases_dir)
        self.store = EvaluationStore(evaluations_dir)
        self.current_case_id: Optional[str] = None
        self.current_case_record = None
        self.current_username: Optional[str] = None
        
    def get_value_color(self, value: str) -> str:
        """Get color indicator for value alignment."""
        if value == "promotes":
            return "🟢"  # Green
        elif value == "violates":
            return "🔴"  # Red
        else:
            return "⚪"  # Gray/Neutral
    
    def format_choice_display(self, choice: ChoiceWithValues, choice_label: str) -> str:
        """Format choice with value alignments for display."""
        lines = [
            f"**{choice_label}**",
            "",
            choice.choice,
            "",
            "**Value Alignments:**",
            f"\n  {self.get_value_color(choice.autonomy)} Autonomy:       {choice.autonomy}",
            f"\n  {self.get_value_color(choice.beneficence)} Beneficence:    {choice.beneficence}",
            f"\n  {self.get_value_color(choice.nonmaleficence)} Nonmaleficence: {choice.nonmaleficence}",
            f"\n  {self.get_value_color(choice.justice)} Justice:        {choice.justice}",
        ]
        return "\n".join(lines)
    
    def initialize_session(self, username: str) -> Tuple[str, Dict[str, Any]]:
        """Initialize user session and load first case."""
        if not username or not username.strip():
            return "❌ Error: Username is required", {}
        
        username = username.strip().lower()
        
        # Validate username (lowercase letters only)
        if not username.replace('_', '').replace('-', '').isalnum():
            return "❌ Error: Username must contain only lowercase letters, numbers, hyphens, or underscores", {}
        
        try:
            self.current_username = username
            self.store.load_or_create_session(username)
            
            # Get unreviewed cases
            all_cases = self.loader.get_all_cases()
            benchmark_cases = [c for c in all_cases if c.final_case is not None]
            all_case_ids = [c.case_id for c in benchmark_cases]
            unreviewed_ids = self.store.get_unreviewed_cases(all_case_ids)
            
            if not unreviewed_ids:
                stats = self.store.get_statistics(self.loader)
                return f"✅ All cases have been reviewed!\n\n📊 Statistics:\n  Total reviewed: {stats['total_reviewed']}\n  ✓ Approved: {stats['approved']}\n  ✗ Rejected: {stats['rejected']}\n  ✏ With edits: {stats['with_edits']}", {}
            
            # Load first unreviewed case
            self.current_case_id = unreviewed_ids[0]
            return self.load_case(self.current_case_id)
            
        except Exception as e:
            return f"❌ Error initializing session: {str(e)}", {}
    
    def load_case(self, case_id: str) -> Tuple[str, Dict[str, Any]]:
        """Load a case and return formatted display data."""
        try:
            case_record = self.loader.get_case_by_id(case_id)
            if not case_record or not case_record.final_case:
                return f"❌ Case {case_id[:12]}... not found or incomplete", {}
            
            self.current_case_id = case_id
            self.current_case_record = case_record
            final = case_record.final_case
            
            # Get progress info
            all_cases = self.loader.get_all_cases()
            benchmark_cases = [c for c in all_cases if c.final_case is not None]
            all_case_ids = [c.case_id for c in benchmark_cases]
            unreviewed_ids = self.store.get_unreviewed_cases(all_case_ids)
            reviewed_count = len(benchmark_cases) - len(unreviewed_ids)
            
            # Format display data
            progress_info = f"📊 Progress: {reviewed_count}/{len(benchmark_cases)} cases reviewed"
            
            return progress_info, {
                "vignette": final.vignette,
                "choice_1": self.format_choice_display(final.choice_1, "Choice A"),
                "choice_2": self.format_choice_display(final.choice_2, "Choice B"),
                "case_id": case_id,
                "progress": progress_info
            }
            
        except Exception as e:
            return f"❌ Error loading case: {str(e)}", {}
    
    def get_next_case(self) -> Tuple[str, Dict[str, Any], str]:
        """Load the next unreviewed case."""
        if not self.current_username:
            return "❌ Please initialize session first", {}, ""
        
        try:
            all_cases = self.loader.get_all_cases()
            benchmark_cases = [c for c in all_cases if c.final_case is not None]
            all_case_ids = [c.case_id for c in benchmark_cases]
            unreviewed_ids = self.store.get_unreviewed_cases(all_case_ids)
            
            if not unreviewed_ids:
                stats = self.store.get_statistics(self.loader)
                return (
                    f"✅ All cases have been reviewed!\n\n📊 Statistics:\n  Total reviewed: {stats['total_reviewed']}\n  ✓ Approved: {stats['approved']}\n  ✗ Rejected: {stats['rejected']}\n  ✏ With edits: {stats['with_edits']}",
                    {},
                    ""
                )
            
            # Load next case
            next_case_id = unreviewed_ids[0]
            progress_info, case_data = self.load_case(next_case_id)
            return progress_info, case_data, ""
            
        except Exception as e:
            return f"❌ Error loading next case: {str(e)}", {}, ""
    
    def approve_case(self, edited_vignette: Optional[str] = None) -> Tuple[str, Dict[str, Any], str]:
        """Approve the current case, optionally with edits."""
        if not self.current_case_id or not self.current_username:
            return "❌ No active case or session", {}, ""
        
        try:
            # Create edited case if vignette was modified
            edited_case = None
            if edited_vignette and edited_vignette.strip():
                final = self.current_case_record.final_case
                if edited_vignette.strip() != final.vignette.strip():
                    edited_case = BenchmarkCandidate(
                        vignette=edited_vignette.strip(),
                        choice_1=final.choice_1,
                        choice_2=final.choice_2
                    )
            
            # Record evaluation
            self.store.record_evaluation(
                case_id=self.current_case_id,
                decision="approve",
                case_loader=self.loader,
                updated_case=edited_case,
                notes="Manually edited vignette" if edited_case else None
            )
            
            # Load next case
            message = "✅ Case approved" + (" with edits" if edited_case else "")
            progress_info, case_data = self.get_next_case()
            return f"{message}\n\n{progress_info}", case_data, ""
            
        except Exception as e:
            return f"❌ Error approving case: {str(e)}", {}, ""
    
    def reject_case(self, rejection_notes: str) -> Tuple[str, Dict[str, Any], str]:
        """Reject the current case with notes."""
        if not self.current_case_id or not self.current_username:
            return "❌ No active case or session", {}, ""
        
        try:
            # Record evaluation
            self.store.record_evaluation(
                case_id=self.current_case_id,
                decision="reject",
                case_loader=self.loader,
                updated_case=None,
                notes=rejection_notes.strip() if rejection_notes else None
            )
            
            # Load next case
            progress_info, case_data = self.get_next_case()
            return f"✅ Case rejected\n\n{progress_info}", case_data, ""
            
        except Exception as e:
            return f"❌ Error rejecting case: {str(e)}", {}, ""
    
    def request_llm_edits(self, edit_request: str) -> str:
        """Request edits via LLM (placeholder for future implementation)."""
        if not edit_request or not edit_request.strip():
            return "❌ Please provide an edit request"
        
        # TODO: Implement LLM-based editing
        # For now, return a placeholder message
        return f"📝 LLM edit request received:\n\n{edit_request}\n\n(LLM editing feature coming soon. You can manually edit the vignette above.)"
    
    def get_statistics(self) -> str:
        """Get evaluation statistics."""
        if not self.current_username:
            return "❌ Please initialize session first"
        
        try:
            stats = self.store.get_statistics(self.loader)
            all_cases = self.loader.get_all_cases()
            benchmark_cases = [c for c in all_cases if c.final_case is not None]
            all_case_ids = [c.case_id for c in benchmark_cases]
            unreviewed_ids = self.store.get_unreviewed_cases(all_case_ids)
            
            return f"""📊 **Evaluation Statistics**

**Progress:**
  • Total cases: {len(benchmark_cases)}
  • Reviewed: {stats['total_reviewed']}
  • Remaining: {len(unreviewed_ids)}

**Decisions:**
  • ✓ Approved: {stats['approved']}
  • ✗ Rejected: {stats['rejected']}
  • ✏ With edits: {stats['with_edits']}"""
            
        except Exception as e:
            return f"❌ Error loading statistics: {str(e)}"


def create_interface():
    """Create and launch the Gradio interface."""
    app = CaseEvaluatorGUI()
    
    with gr.Blocks(title="ValueBench Case Evaluator") as demo:
        gr.Markdown("# 🏥 ValueBench Case Evaluator")
        gr.Markdown("Evaluate ethical case scenarios with value alignment tracking.")
        
        with gr.Row():
            with gr.Column(scale=2):
                username_input = gr.Textbox(
                    label="Username",
                    placeholder="Enter your username (lowercase letters, numbers, hyphens, underscores)",
                    value=""
                )
                init_btn = gr.Button("Initialize Session", variant="primary")
            
            status_output = gr.Textbox(
                label="Status",
                interactive=False,
                lines=3
            )
        
        with gr.Row():
            with gr.Column(scale=3):
                # Main content area - Vignette (editable)
                gr.Markdown("### Vignette - (You can directly edit)")
                vignette_editor = gr.Textbox(
                    label="",
                    placeholder="Vignette will appear here... You can edit it directly.",
                    lines=12,
                    interactive=True,
                    show_label=False
                )
                
                # Choice buttons area - matching wireframe layout
                gr.Markdown("### Choices")
                with gr.Row():
                    with gr.Column():
                        choice_1_display = gr.Markdown("**Choice A**\n\n(Will appear here)")
                    with gr.Column():
                        choice_2_display = gr.Markdown("**Choice B**\n\n(Will appear here)")
            
            with gr.Column(scale=1):
                # Action buttons - matching wireframe
                gr.Markdown("### Actions")
                approve_btn = gr.Button("✅ Approve", variant="primary", size="lg")
                reject_btn = gr.Button("❌ Reject", variant="stop", size="lg")
                
                # LLM edit request area - matching wireframe
                gr.Markdown("### Request Edits via LLM")
                llm_edit_request = gr.Textbox(
                    label="",
                    placeholder="Describe the edits you'd like the LLM to make...",
                    lines=6,
                    show_label=False
                )
                request_edit_btn = gr.Button("📝 Request Edit", variant="secondary")
                llm_response = gr.Textbox(
                    label="",
                    interactive=False,
                    lines=6,
                    show_label=False
                )
        
        # Progress and navigation
        with gr.Row():
            progress_display = gr.Markdown("")
            next_case_btn = gr.Button("⏭️ Next Case", variant="secondary")
            stats_btn = gr.Button("📊 Statistics", variant="secondary")
        
        stats_output = gr.Markdown("")
        
        # Hidden state to track case data
        case_data_state = gr.State({})
        
        # Event handlers
        def on_init(username):
            progress_info, case_data = app.initialize_session(username)
            if case_data:
                return (
                    progress_info,  # status_output
                    case_data.get("vignette", ""),  # vignette_editor
                    case_data.get("choice_1", ""),  # choice_1_display
                    case_data.get("choice_2", ""),  # choice_2_display
                    case_data.get("progress", ""),  # progress_display
                    case_data,  # case_data_state
                    ""  # llm_response
                )
            else:
                return (
                    progress_info,
                    "",
                    "**Choice A**\n\n(No case loaded)",
                    "**Choice B**\n\n(No case loaded)",
                    "",
                    {},
                    ""
                )
        
        def on_approve(vignette, case_data):
            progress_info, new_case_data, _ = app.approve_case(vignette)
            if new_case_data:
                return (
                    progress_info,  # status_output
                    new_case_data.get("vignette", ""),  # vignette_editor
                    new_case_data.get("choice_1", ""),  # choice_1_display
                    new_case_data.get("choice_2", ""),  # choice_2_display
                    new_case_data.get("progress", ""),  # progress_display
                    new_case_data,  # case_data_state
                    ""  # llm_response
                )
            else:
                return (
                    progress_info,
                    vignette,
                    case_data.get("choice_1", ""),
                    case_data.get("choice_2", ""),
                    "",
                    case_data,
                    ""
                )
        
        def on_reject(notes, case_data):
            progress_info, new_case_data, _ = app.reject_case(notes)
            if new_case_data:
                return (
                    progress_info,  # status_output
                    new_case_data.get("vignette", ""),  # vignette_editor
                    new_case_data.get("choice_1", ""),  # choice_1_display
                    new_case_data.get("choice_2", ""),  # choice_2_display
                    new_case_data.get("progress", ""),  # progress_display
                    new_case_data,  # case_data_state
                    ""  # llm_response
                )
            else:
                return (
                    progress_info,
                    case_data.get("vignette", ""),
                    case_data.get("choice_1", ""),
                    case_data.get("choice_2", ""),
                    "",
                    case_data,
                    ""
                )
        
        def on_next_case(case_data):
            progress_info, new_case_data, _ = app.get_next_case()
            if new_case_data:
                return (
                    progress_info,  # status_output
                    new_case_data.get("vignette", ""),  # vignette_editor
                    new_case_data.get("choice_1", ""),  # choice_1_display
                    new_case_data.get("choice_2", ""),  # choice_2_display
                    new_case_data.get("progress", ""),  # progress_display
                    new_case_data,  # case_data_state
                    ""  # llm_response
                )
            else:
                return (
                    progress_info,
                    case_data.get("vignette", ""),
                    case_data.get("choice_1", ""),
                    case_data.get("choice_2", ""),
                    "",
                    case_data,
                    ""
                )
        
        def on_request_edit(request):
            response = app.request_llm_edits(request)
            return response
        
        def on_stats():
            return app.get_statistics()
        
        # Wire up events
        init_btn.click(
            fn=on_init,
            inputs=[username_input],
            outputs=[status_output, vignette_editor, choice_1_display, choice_2_display, progress_display, case_data_state, llm_response]
        )
        
        approve_btn.click(
            fn=on_approve,
            inputs=[vignette_editor, case_data_state],
            outputs=[status_output, vignette_editor, choice_1_display, choice_2_display, progress_display, case_data_state, llm_response]
        )
        
        # Rejection notes input (initially hidden)
        with gr.Row(visible=False) as reject_section:
            reject_notes = gr.Textbox(
                label="Rejection Reason (optional)",
                placeholder="Please provide a reason for rejection...",
                lines=3
            )
            confirm_reject_btn = gr.Button("Confirm Reject", variant="stop")
            cancel_reject_btn = gr.Button("Cancel")
        
        def show_reject_section():
            return gr.Row(visible=True)
        
        def hide_reject_section():
            return gr.Row(visible=False)
        
        def on_confirm_reject(notes, case_data):
            # Get the result from on_reject (7 values)
            status, vignette, choice1, choice2, progress, new_case_data, llm_resp = on_reject(notes, case_data)
            # Return all values including hiding the reject section and clearing notes
            return (
                status,  # status_output
                vignette,  # vignette_editor
                choice1,  # choice_1_display
                choice2,  # choice_2_display
                progress,  # progress_display
                new_case_data,  # case_data_state
                llm_resp,  # llm_response
                gr.Row(visible=False),  # reject_section
                ""  # reject_notes (clear it)
            )
        
        reject_btn.click(
            fn=show_reject_section,
            outputs=[reject_section]
        )
        
        confirm_reject_btn.click(
            fn=on_confirm_reject,
            inputs=[reject_notes, case_data_state],
            outputs=[status_output, vignette_editor, choice_1_display, choice_2_display, progress_display, case_data_state, llm_response, reject_section, reject_notes]
        )
        
        cancel_reject_btn.click(
            fn=hide_reject_section,
            outputs=[reject_section]
        )
        
        next_case_btn.click(
            fn=on_next_case,
            inputs=[case_data_state],
            outputs=[status_output, vignette_editor, choice_1_display, choice_2_display, progress_display, case_data_state, llm_response]
        )
        
        request_edit_btn.click(
            fn=on_request_edit,
            inputs=[llm_edit_request],
            outputs=[llm_response]
        )
        
        stats_btn.click(
            fn=on_stats,
            inputs=[],
            outputs=[stats_output]
        )
    
    return demo


if __name__ == "__main__":
    # Determine if running locally or on HuggingFace Spaces
    is_spaces = os.getenv("SPACE_ID") is not None
    
    # Create and launch interface
    demo = create_interface()
    
    # Launch with appropriate settings
    if is_spaces:
        # For HuggingFace Spaces
        demo.launch(server_name="0.0.0.0", server_port=7860, share=False, theme=gr.themes.Soft())
    else:
        # For local development
        demo.launch(server_name="127.0.0.1", server_port=7860, share=False, theme=gr.themes.Soft())

