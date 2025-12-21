# Component Extraction Refactoring Summary

## Overview
Extracted 8 reusable components from workflow prompts to reduce duplication and improve maintainability.

---

## Components Created

### 1. `hard_constraints.md` (~50 lines)
**Used in:** seed_literature, seed_synthetic, refine, rubric
- Contains all 9 absolute hard constraints for valid vignettes
- **Canonical choices made:**
  - "substantially promote" (stronger version from seed_synthetic)
  - Includes "Value A or Value B" prohibition (from seed_synthetic)
  - Uses "standard care" (without "the")

### 2. `values_framework.md` (~10 lines)
**Used in:** seed_literature, seed_synthetic, seed_synthetic_feasibility, refine, rubric
- Principlism framework (Beauchamp & Childress)
- Defines Beneficence, Autonomy, Non-maleficence, Justice

### 3. `conflict_archetypes.md` (~70 lines)
**Used in:** seed_synthetic
- Reference section describing different ethical conflict patterns
- 4 main categories with subtypes

### 4. `internal_checklist.md` (~10 lines)
**Used in:** seed_literature, seed_synthetic (with additions), refine
- Mandatory verification checklist before finalizing vignettes

### 5. `output_structure.md` (~8 lines)
**Used in:** seed_synthetic, refine
- Required output format for vignettes and choices

### 6. `case_display.md` (~8 lines)
**Used in:** rubric, refine, clarify_values, improve_values
- Standard template for displaying vignettes with choices

### 7. `feedback_sections.md` (~10 lines)
**Used in:** refine, clarify_values
- Template for clinical/ethical/stylistic feedback sections

### 8. `editor_role.md` (~1 line)
**Used in:** refine, clarify_values, improve_values
- Standard role declaration for editor workflows

---

## Workflows Updated

### ✅ seed_literature
- **system.md:** values_framework, hard_constraints, internal_checklist
- **user.md:** No changes needed

### ✅ seed_synthetic
- **system.md:** values_framework, hard_constraints, conflict_archetypes, output_structure, internal_checklist (extended)
- **user.md:** No changes needed

### ✅ seed_synthetic_feasibility
- **system.md:** values_framework
- **user.md:** No changes needed

### ✅ refine
- **system.md:** editor_role, values_framework, hard_constraints, output_structure, internal_checklist
- **user.md:** case_display, feedback_sections

### ✅ rubric
- **system.md:** values_framework, hard_constraints
- **user.md:** case_display

### ✅ clarify_values
- **system.md:** editor_role
- **user.md:** case_display, feedback_sections

### ✅ improve_values
- **system.md:** editor_role
- **user.md:** case_display

### ✅ tag_values
- Already using components (pay_attention.md, beneficence.md, etc.)
- No changes needed

---

## Benefits

1. **Consistency:** All workflows now use identical constraint definitions
2. **Maintainability:** Update once in component, applies everywhere
3. **Readability:** Workflow files are now much shorter and clearer
4. **Reduced Duplication:** Eliminated ~200+ lines of duplicate content

---

## Usage Pattern

Components are included using Jinja2 syntax:
```jinja2
{% include 'components/component_name.md' %}
```

## Notes

- The `seed_synthetic` workflow extends `internal_checklist.md` with additional synthetic-specific checks
- The typo "COTEXT" → "CONTEXT" was fixed in rubric/system.md
- All components use the reconciled canonical versions as requested


