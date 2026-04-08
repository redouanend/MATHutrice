# Minimalist Multiple Choice Interface — README
## Context

This branch introduces the first minimalist version of a multiple-choice exercise interface. It allows students to attempt exercises and view their scores directly in the interface. The interface is designed to be lightweight and focused on essential functionality, providing a base for further development.

## Why

In this initial version:

The interface successfully displays multiple-choice questions and tracks scores.
Mathematical expressions are not rendered correctly, which impacts usability for math exercises.
A solution is needed to properly display mathematical notation for clarity and student comprehension.

## Solution

The current branch provides a functional base interface with:

- Student score tracking
- Minimal styling for clarity
- A frontend-ready structure to receive dynamic questions

To address the backend and question generation:

Backend integration for dynamic exercises:
- Questions will be generated programmatically or via AI (e.g., Claude, GPT) on the server-side.
- The backend will serve questions as JSON to the frontend, including:
- Question text
- Options
- Correct answer
  
Mathematical expression rendering:
Libraries like MathJax or KaTeX will be used to properly render formulas sent from the backend.

Score and progress management:
Backend will track student responses, update global and per-topic progress, and provide analytics.

Scalability & maintainability:
This architecture separates frontend display and question generation logic, allowing easy updates, new exercise types, or AI-based question improvements.

This branch serves as a foundation for a full e-learning platform with a robust backend, dynamic question generation, and proper math rendering.

## Next steps will involve:

Evaluating libraries or tools (e.g., MathJax or KaTeX) for proper mathematical expression rendering.
Integrating the chosen solution while keeping the interface minimalist and performant.
Ensuring the interface remains responsive and user-friendly across devices.

This is the 1st version displayed : 
<img width="1917" height="962" alt="Capture d&#39;écran 2026-04-08 124044" src="https://github.com/user-attachments/assets/1074a7ee-fdd1-423f-81aa-eab492ac7d54" />
<img width="1122" height="959" alt="Capture d&#39;écran 2026-04-08 124111" src="https://github.com/user-attachments/assets/7603ce74-42c6-4321-83a2-1ed66fc7d541" />
<img width="1115" height="965" alt="Capture d&#39;écran 2026-04-08 124100" src="https://github.com/user-attachments/assets/9cf56503-7e76-4227-b67c-ecaa2a4687ff" />


