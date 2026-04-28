# UI Micro Polish Spec

## Feature Overview

This change adds minor UI polish improvements for clarity, consistency, and visual quality in the public SIEM dashboard.

The goal is to make the dashboard feel cleaner, more consistent, and more production-ready without adding new features or changing behavior.

## Current State

- The alerts table is functional and feature-rich
- The investigation timeline exists
- Targeted alert styling exists
- Minor inconsistencies remain in:
  - spacing
  - typography hierarchy
  - badge sizing and alignment
  - visual emphasis consistency

## Requirements

1. Spacing improvements
   - make padding between rows more consistent
   - make spacing inside alert details sections more consistent
   - reduce visual clutter without changing layout structure

2. Typography hierarchy
   - create clearer distinction between:
     - headers
     - labels
     - values
   - keep font sizing consistent across similar UI elements

3. Badge consistency
   - ensure badges use:
     - consistent padding
     - consistent font size
     - consistent border radius
   - prevent oversized or misaligned badges

4. Hover effects
   - add a subtle hover highlight on alert rows
   - keep it compatible with the dark theme
   - avoid heavy animation

5. Tooltips
   - add simple native `title` tooltips on badges where practical
   - do not add a tooltip library

6. Color tuning
   - ensure consistent use of:
     - red for critical / strongest emphasis
     - orange for warning / correlation emphasis
     - neutral tones for default UI
   - avoid overly bright or clashing colors

7. Optional animation
   - add only a very subtle fade or highlight if it is easy within the existing code
   - avoid heavy motion or distracting animation

8. Do not:
   - change layout structure
   - add new features
   - modify backend or API behavior
   - introduce new libraries

## Acceptance Criteria

1. The UI looks cleaner and more consistent
2. No layout breakage is introduced
3. Existing functionality remains unchanged
4. Frontend build succeeds
