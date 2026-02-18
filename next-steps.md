# Next Steps

- Finalize role assignments for competition week coverage.
- Pre-build challenge submission templates for `solutions/challenge-1`, `solutions/challenge-2`, and `solutions/challenge-3`.
- Add a minimal reproducibility checklist to the submission workflow (artifacts, versions, seeds, command).
- Confirm 2026 competition rules on external tools, APIs, and cloud compute usage.
- Consider referencing `D:\Projects\eu-ai-compliance-toolkit` during the competition as a local decision-support resource for data/compliance checks.

## MCP Tooling Review (2026-02-19)

### Current Gap
No MCP servers, dependency files, or technical tooling installed. Repo has process scaffolding only.

### Must-Have Baseline (install before March 19)
1. **MarkItDown** (microsoft/markitdown, 87K stars) - Convert challenge PDFs, papers, and dataset docs into Markdown for LLM ingestion.
2. **GitHub MCP Server** (github/github-mcp-server, 27K stars) - GitHub integration (repos, PRs, issues, actions) through AI workflow.

### Optional MCPs (only if challenge requires them)
3. **Context7** (upstash/context7, 46K stars) - Live library docs in editor; useful when using unfamiliar frameworks.
4. **Playwright MCP** (microsoft/playwright-mcp, 27K stars) - Browser automation for web submissions or UI testing.
5. **Claude Task Master** (eyaltoledano/claude-task-master, 25.5K stars) - Task orchestration support for solo execution.
6. **MCP Run Python** (pydantic/pydantic-ai, 14.9K stars) - Sandboxed Python execution for rapid prototyping.
7. **GenAI Toolbox** (googleapis/genai-toolbox, 13K stars) - DB operations if a challenge includes structured SQL/data workloads.
8. **Cognee** (topoteretes/cognee, 12.4K stars) - Graph/vector RAG pipeline support if a RAG-heavy challenge appears.
9. **Browser MCP** (browsermcp/mcp, 5.8K stars) - Local Chrome control for platform interaction.
10. **DesktopCommanderMCP** (wonderwhy-er, 5.5K stars) - OS-level process/file management for run orchestration.

### Key Considerations
- 2025 NORA challenge-type notes (Healthcare RAG, autonomous race car AI, and a third task) are from informal recon and must be treated as unverified until confirmed from official challenge material.
- Solo coverage means task orchestration tooling (Claude Task Master) has outsized value.
- Cognee is high priority if RAG appears again; Playwright if challenges have web-based interfaces.
- All MCPs need config setup in `.claude/` or equivalent before competition day; do not leave setup for kickoff.
- OS/browser automation MCPs can create reliability and compliance risk; only enable if competition rules explicitly permit the behavior.

### MCP Kill Criteria
- Remove any MCP if setup takes more than 30 minutes with no working dry-run.
- Remove any MCP that fails in 2 or more dry-runs.
- Remove any MCP that cannot show clear value in either speed, score, or submission reliability.

### Fallback Path
- If MCP stack is unstable, run a local-script-only workflow (no MCP dependency) and continue with baseline submission path.

### Action Items
- [ ] Install and configure must-have baseline stack (MarkItDown, GitHub MCP).
- [ ] Test each enabled MCP in a dry-run against a mock challenge.
- [ ] Create `.claude/settings.json` with MCP server configs.
- [ ] Add `requirements.txt` / `package.json` with pinned versions for core dependencies.
- [ ] Run full dry-run of `playbooks/submission-runbook.md` with tooling in place.
