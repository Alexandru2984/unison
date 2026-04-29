# Distributed Idea Evolution Engine

A unique web application showcasing Unison's deterministic execution and content-addressed code.

## Why Unison?

Unison is fundamentally different from traditional programming languages:
- **Content-Addressed Code:** Functions and data are identified by a cryptographic hash of their abstract syntax tree, not by a text-based file name. This means no dependency conflicts and trivial refactoring.
- **Deterministic Evolution:** Each idea mutation is a pure function. Given the same idea and the same function hash, the output is guaranteed to be identical every time. This enables reliable, exact replay of the idea evolution tree.
- **Distributed Ready:** Because code is immutable and content-addressed, functions can be serialized and sent across nodes over a network, making the system naturally distributed.

## Architecture

- **Unison Engine:** Handles pure transformations of textual ideas.
- **Python Backend (FastAPI):** Orchestrates API calls, WebSockets, and state persistence, bridging the web to Unison.
- **React Frontend:** Visualizes the idea tree and timeline.

## Setup
(Internal use only)