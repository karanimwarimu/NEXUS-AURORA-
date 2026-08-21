# 🔧 NEXUS AURORA Repository Cleanup & Reorganization Instructions

**Date Created:** August 21, 2026  
**Status:** Ready for Implementation  
**Scope:** Complete repository restructuring by phase  
**Priority:** HIGH - Execute before Phase 5 starts

---

## 📋 OVERVIEW

This document contains complete instructions for reorganizing the NEXUS AURORA repository into a clean, phase-based structure. All test files, release notes, audits, reports, and checklists will be organized by development phase.

**Expected Outcome:**
- ✅ Phase-based folder structure (Phase 1-5)
- ✅ All documents organized by type and phase
- ✅ Updated REPOSITORY_STRUCTURE.md
- ✅ Updated main README.md (v4.6.0)
- ✅ Clean, navigable project structure

---

## 🎯 PHASE-BASED FOLDER STRUCTURE

### Target Structure

```
NEXUS AURORA/
├── README.md (master, updated)
├── REPOSITORY_STRUCTURE.md (updated)
├── LICENSE
├── .gitignore
│
├── phases/
│   ├── PHASE_1_EXTRACTION/
│   │   ├── README.md
│   │   ├── release_notes/
│   │   │   └── release_notes_v1.0.0.md
│   │   ├── docs/
│   │   ├── tests/
│   │   └── audits/
│   │
│   ├── PHASE_2_CRAWLER/
│   │   ├── README.md
│   │   ├── release_notes/
│   │   │   ├── release_notes_v2.0.0.md
│   │   │   ├── release_notes_v2.6.0.md
│   │   ├── docs/
│   │   ├── tests/
│   │   └── audits/
│   │
│   ├── PHASE_3_DETECTION/
│   │   ├── README.md
│   │   ├── release_notes/
│   │   │   └── release_notes_v3.0.0.md
│   │   ├── docs/
│   │   ├── tests/
│   │   ├── audits/
│   │   └── reports/
│   │
│   ├── PHASE_4A_STORAGE/
│   │   ├── README.md
│   │   ├── release_notes/
│   │   │   └── release_notes_v4.1.0.md
│   │   ├── docs/
│   │   ├── tests/
│   │   ├── audits/
│   │   └── reports/
│   │
│   ├── PHASE_4B_AI_ENRICHMENT/
│   │   ├── README.md
│   │   ├── release_notes/
│   │   │   └── release_notes_v4.3.0.md
│   │   ├── docs/
│   │   ├── tests/
│   │   ├── audits/
│   │   └── reports/
│   │
│   └── PHASE_4C_API_INFRASTRUCTURE/
│       ├── README.md
│       ├── release_notes/
│       │   └── release_notes_v4.6.0.md
│       ├── docs/
│       │   ├── INDEX.md (master navigation)
│       │   ├── IMPLEMENTATION_STATUS.md
│       │   ├── FINAL_STATUS_REPORT.md
│       │   └── ... (all other Phase 4C docs)
│       ├── tests/
│       │   ├── comprehensive_test_rerun.py
│       │   ├── test_execution_runner.py
│       │   └── PHASE_4C_PHYSICAL_TEST_SUITE.md
│       ├── checklists/
│       │   ├── PHASE_4C_VERIFICATION_CHECKLIST.md
│       │   ├── QUICK_ACTION_CHECKLIST.md
│       │   └── PHASE_5_READINESS_GATE.md
│       ├── audits/
│       │   └── NEXUS_AURORA_PHASE4C_FINAL_AUDIT.md
│       └── reports/
│           ├── TEST_EXECUTION_SESSION_SUMMARY.md
│           ├── EXECUTIVE_SUMMARY.md
│           └── PRODUCTION_READINESS_REPORT.md
│
├── Nexora application/
│   ├── Crawler/
│   ├── Extractor/
│   ├── Models/
│   ├── tests/
│   ├── output/
│   └── application documents/
│       └── README.md (updated - refers to phases/ structure)
│
├── docs/ (general documentation, not phase-specific)
├── scripts/ (utility scripts)
└── tools/ (external tools)
```

---

## 📂 FILE MIGRATION MAP

### Release Notes
```
Current Location                    →  New Location
release_notes_v4.4.0.md             →  phases/PHASE_4A_STORAGE/release_notes/
release_notes_v4.5.0.md             →  phases/PHASE_4B_AI_ENRICHMENT/release_notes/
release_notes_v4.6.0.md             →  phases/PHASE_4C_API_INFRASTRUCTURE/release_notes/
Nexora application/application documents/release_notes_*.md  →  (by version to corresponding phase)
```

### Phase 4C Test Files
```
Current: Nexora application/application documents/API TESTS (PHASE4C)/*

New:
├── phases/PHASE_4C_API_INFRASTRUCTURE/
│   ├── docs/
│   │   ├── INDEX.md
│   │   ├── KIRO_MASTER_PHASE4C_WORKFLOW.md
│   │   ├── KIRO_PHASE4C_IMPLEMENTATION_STATUS.md
│   │   ├── KIRO_FINAL_STATUS_REPORT.md
│   │   ├── START_HERE_FULL_TEST_RESULTS.md
│   │   ├── COMPLETE_TEST_RESULTS_AND_HUMAN_REVIEW.md
│   │   ├── HUMAN_REVIEW_GUIDE_COMPLETE.md
│   │   ├── RERUN_EXECUTIVE_SUMMARY.md
│   │   ├── PHASE_4C_RIGOROUS_END_TO_END_TEST_PLAN.md
│   │   ├── PHASE_4C_TEST_PLAN_README.md
│   │   ├── TESTING_APPROACH_SUMMARY.md
│   │   └── ... (all other reference docs)
│   │
│   ├── tests/
│   │   ├── comprehensive_test_rerun.py
│   │   ├── test_execution_runner.py
│   │   ├── PHASE_4C_PHYSICAL_TEST_SUITE.md
│   │   └── _probe_db.py
│   │
│   ├── checklists/
│   │   ├── PHASE_4C_VERIFICATION_CHECKLIST.md
│   │   ├── QUICK_ACTION_CHECKLIST.md
│   │   ├── 00_READ_THIS_FIRST_FOR_PHASE5.md (→ PHASE_5_READINESS_GATE.md)
│   │   └── PHASE_5_READINESS_GATE.md
│   │
│   ├── audits/
│   │   └── NEXUS_AURORA_PHASE4C_FINAL_AUDIT.md
│   │
│   └── reports/
│       ├── TEST_EXECUTION_SESSION_SUMMARY.md
│       ├── KIRO_COMPLETION_SUMMARY.txt
│       └── KIRO_FINAL_STATUS_REPORT.md
```

### Other Phase Audits/Reports
```
Nexora application/output/audit/*   →  phases/[PHASE]/audits/
Nexora application/output/*reports* →  phases/[PHASE]/reports/
```

---

## 🔄 STEP-BY-STEP EXECUTION PLAN

### STEP 1: Create Phase Folders

```bash
cd "F:\DSF\stsh projects\NEXUS AURORA"

# Create main phases directory
mkdir phases

# Create each phase folder with subfolders
mkdir phases\PHASE_1_EXTRACTION\{docs,tests,audits,release_notes}
mkdir phases\PHASE_2_CRAWLER\{docs,tests,audits,release_notes}
mkdir phases\PHASE_3_DETECTION\{docs,tests,audits,reports,release_notes}
mkdir phases\PHASE_4A_STORAGE\{docs,tests,audits,reports,release_notes}
mkdir phases\PHASE_4B_AI_ENRICHMENT\{docs,tests,audits,reports,release_notes}
mkdir phases\PHASE_4C_API_INFRASTRUCTURE\{docs,tests,audits,reports,checklists,release_notes}
```

### STEP 2: Move Release Notes

```bash
# Move root release notes to appropriate phases
move release_notes_v4.4.0.md phases\PHASE_4A_STORAGE\release_notes\
move release_notes_v4.5.0.md phases\PHASE_4B_AI_ENRICHMENT\release_notes\
move release_notes_v4.6.0.md phases\PHASE_4C_API_INFRASTRUCTURE\release_notes\

# Move nested release notes
move "Nexora application\application documents\release_notes_v4.6.0.md" phases\PHASE_4C_API_INFRASTRUCTURE\release_notes\
move "Nexora application\application documents\release_notes_v4.5.0.md" phases\PHASE_4B_AI_ENRICHMENT\release_notes\
move "Nexora application\application documents\release_notes_v4.4.0.md" phases\PHASE_4A_STORAGE\release_notes\
move "Nexora application\application documents\release_notes_v4.3.0.md" phases\PHASE_3_DETECTION\release_notes\
move "Nexora application\application documents\release_notes_v4.2.1.md" phases\PHASE_4A_STORAGE\release_notes\
move "Nexora application\application documents\release_notes_v4.1.0.md" phases\PHASE_4A_STORAGE\release_notes\
```

### STEP 3: Move Phase 4C Test Files

```bash
# Copy entire Phase 4C test directory to new location
xcopy "Nexora application\application documents\API TESTS (PHASE4C)" "phases\PHASE_4C_API_INFRASTRUCTURE" /E /I

# Then reorganize within new location:
cd phases\PHASE_4C_API_INFRASTRUCTURE

# Move test files to tests folder
move comprehensive_test_rerun.py tests\
move test_execution_runner.py tests\
move _probe_db.py tests\
move PHASE_4C_PHYSICAL_TEST_SUITE.md tests\

# Move docs files to docs folder
move INDEX.md docs\
move START_HERE_FULL_TEST_RESULTS.md docs\
move COMPLETE_TEST_RESULTS_AND_HUMAN_REVIEW.md docs\
move HUMAN_REVIEW_GUIDE_COMPLETE.md docs\
move RERUN_EXECUTIVE_SUMMARY.md docs\
move PHASE_4C_RIGOROUS_END_TO_END_TEST_PLAN.md docs\
move PHASE_4C_TEST_PLAN_README.md docs\
move TESTING_APPROACH_SUMMARY.md docs\
move PHASE_4C_VERIFICATION_CHECKLIST.md checklists\
move START_HERE_PHYSICAL_TESTING.md docs\
move PHASE_4C_TESTING_COMPLETE.md docs\
move HUMAN_REVIEW_SUMMARY.txt docs\
move KIRO_MASTER_PHASE4C_WORKFLOW.md docs\
move KIRO_PHASE4C_IMPLEMENTATION_STATUS.md docs\
move KIRO_FINAL_STATUS_REPORT.md reports\
move KIRO_QUICK_ACTION_CHECKLIST.md checklists\
move KIRO_COMPLETION_SUMMARY.txt reports\
move 00_READ_THIS_FIRST_FOR_PHASE5.md checklists\
move PHASE_5_READINESS_GATE.md checklists\

# Move report/audit files
move TEST_EXECUTION_SESSION_SUMMARY.md reports\
move SESSION_SUMMARY_2026-08-19.md reports\
move COMPREHENSIVE_SESSION_DOCUMENTATION_2026-08-18.md reports\
move NEXORA_SESSION_HANDOFF.md docs\
move TECHNICAL_IMPLEMENTATION_REFERENCE.md docs\
move NEXT_STEPS_ACTION_PLAN.md docs\
move checklist.md checklists\

# Move older audit files to audits folder
move PHASE_4C_TEST_EXECUTION_INDEX.md docs\
move PHASE_4C_TEST_REPORT_SUMMARY.md reports\
```

### STEP 4: Move Existing Audit/Report Files

```bash
# Move audit files from Nexora application/output/audit to phases
xcopy "Nexora application\output\audit" "phases\PHASE_4B_AI_ENRICHMENT\audits" /E /I
```

### STEP 5: Create Phase README Files

Each phase folder needs a README.md explaining what's in it:

**phases/PHASE_1_EXTRACTION/README.md**
```markdown
# Phase 1: Single Page Extraction

Basic webpage extraction and parsing functionality.

## Contents
- docs/: Documentation
- tests/: Test files
- audits/: Audit reports
- release_notes/: Version history

## Quick Start
[Instructions for Phase 1]
```

(Similar structure for PHASE_2, PHASE_3, PHASE_4A, PHASE_4B)

**phases/PHASE_4C_API_INFRASTRUCTURE/README.md**
```markdown
# Phase 4C: API Infrastructure & Multi-Tenancy

FastAPI server, JWT authentication, multi-tenancy, webhooks, job engine.

## Quick Navigation

### For Testing
- 📋 See: `checklists/PHASE_5_READINESS_GATE.md`
- 🧪 See: `docs/HUMAN_REVIEW_GUIDE_COMPLETE.md`

### For Implementation Status
- 📊 See: `reports/KIRO_FINAL_STATUS_REPORT.md`
- 🎯 See: `docs/KIRO_PHASE4C_IMPLEMENTATION_STATUS.md`

### For Full Details
- 📖 See: `docs/KIRO_MASTER_PHASE4C_WORKFLOW.md`

## Critical Actions
1. **Cross-Workspace Verification**: checklists/PHASE_5_READINESS_GATE.md
2. **Database Migration Test**: checklists/PHASE_5_READINESS_GATE.md
3. **JWT Secret Change**: checklists/PHASE_5_READINESS_GATE.md

## Status
- Tests: 20/27 PASS (74%)
- Critical Blockers: 2
- Ready for Phase 5: CONDITIONAL (after gate verification)
```

### STEP 6: Update Main README.md

Update the main `README.md` to reference v4.6.0 and add a section pointing to the phases structure:

```markdown
## 📂 Phase-Based Documentation

All development phases are organized in the `phases/` directory:

- [Phase 1: Single Page Extraction](phases/PHASE_1_EXTRACTION/README.md)
- [Phase 2: Scrapy Crawler](phases/PHASE_2_CRAWLER/README.md)
- [Phase 3: Dynamic Detection](phases/PHASE_3_DETECTION/README.md)
- [Phase 4A: Storage & Multi-Format Export](phases/PHASE_4A_STORAGE/README.md)
- [Phase 4B: AI Enrichment & Vector Indexing](phases/PHASE_4B_AI_ENRICHMENT/README.md)
- [Phase 4C: API Infrastructure & Multi-Tenancy](phases/PHASE_4C_API_INFRASTRUCTURE/README.md)

Each phase contains:
- **docs/**: Documentation and guides
- **tests/**: Test files and test suites
- **audits/**: Audit reports and findings
- **reports/**: Test reports and summaries
- **checklists/**: Verification and action checklists
- **release_notes/**: Version history for that phase
```

### STEP 7: Update REPOSITORY_STRUCTURE.md

Create a new REPOSITORY_STRUCTURE.md that reflects the new organization:

```markdown
# NEXUS AURORA Repository Structure (v4.6.0)

> Updated structure organized by development phase with consolidated docs, tests, audits, and reports.

## Root Level

```
NEXUS AURORA/
├── README.md                        Main project README (v4.6.0)
├── REPOSITORY_STRUCTURE.md          This file
├── LICENSE
├── .gitignore
├── REPOSITORY_CLEANUP_INSTRUCTIONS.md  (Archive - for reference)
│
├── phases/                          📂 Phase-based organization
│   ├── PHASE_1_EXTRACTION/
│   ├── PHASE_2_CRAWLER/
│   ├── PHASE_3_DETECTION/
│   ├── PHASE_4A_STORAGE/
│   ├── PHASE_4B_AI_ENRICHMENT/
│   └── PHASE_4C_API_INFRASTRUCTURE/  ← Current focus
│
└── Nexora application/              🔧 Active development
    ├── Crawler/
    ├── Extractor/
    ├── Models/
    ├── tests/
    ├── output/
    └── application documents/
        └── (simplified, refers to phases/)
```

## Phase Structure

Each phase folder contains:
```
phases/PHASE_4C_API_INFRASTRUCTURE/
├── README.md                    Quick guide for this phase
├── docs/                        📚 All documentation
├── tests/                       🧪 Test files and suites
├── audits/                      📋 Audit findings
├── reports/                     📊 Test/verification reports
├── checklists/                  ✅ Action items & gates
└── release_notes/               📝 Version history
```
```

### STEP 8: Clean Up Old Locations

After moving all files:

```bash
# Remove old API TESTS folder (keep backup copy first!)
rmdir "Nexora application\application documents\API TESTS (PHASE4C)" /s

# Update Nexora application/application documents/README.md to reference new structure
```

### STEP 9: Create Migration Summary

Create a file documenting the migration:

**MIGRATION_SUMMARY_2026-08-21.md**
```markdown
# Repository Cleanup & Reorganization Summary

**Date:** August 21, 2026
**Scope:** Complete repository restructuring by phase

## Changes Made

### New Structure
- ✅ Created `phases/` directory with 6 phase folders
- ✅ Moved all release notes to phase-specific folders
- ✅ Reorganized Phase 4C files (docs, tests, audits, reports, checklists)
- ✅ Created phase-specific README files
- ✅ Updated main README.md (v4.6.0)
- ✅ Updated REPOSITORY_STRUCTURE.md

### Files Organized
- Release notes: 8 files moved to appropriate phases
- Phase 4C docs: 30+ files reorganized into subfolders
- Audits: Moved from output/audit to phases/*/audits/
- Reports: Moved to phases/*/reports/

### Benefits
- Clear phase-based navigation
- Easier to locate phase-specific docs/tests/audits
- Scalable structure for future phases
- Better project organization

### Old Locations Cleaned Up
- API TESTS (PHASE4C) folder removed
- Redundant release notes consolidated

## Next Steps
- Archive this cleanup instructions file
- Begin Phase 5 development using new structure
- Update CI/CD pipelines to reference new paths
```

---

## ✅ VERIFICATION CHECKLIST

After completing all steps, verify:

```
[ ] All phase folders created with subfolders
[ ] Release notes moved to correct phase folders
[ ] Phase 4C files reorganized (docs, tests, audits, reports, checklists)
[ ] Each phase has a README.md
[ ] Main README.md updated to v4.6.0
[ ] REPOSITORY_STRUCTURE.md updated
[ ] Old API TESTS folder removed/archived
[ ] No broken links or references
[ ] Migration summary created
[ ] Project structure matches target diagram above
```

---

## 🚀 RUNNING THIS CLEANUP

**To execute this cleanup in a new session:**

1. Copy this entire markdown file to your project
2. Read through completely (30 min)
3. Execute steps 1-9 in order (2-3 hours)
4. Run verification checklist
5. Commit changes to git

**Estimated Total Time:** 3-4 hours

---

## 📞 NOTES

- **Backup first**: Create a git commit before starting
- **Windows commands**: Commands use Windows syntax (mkdir, move, xcopy)
- **For Linux/Mac**: Use equivalent commands (mkdir -p, mv, cp -r)
- **Git history**: Moving files may be visible in git history
- **Cross-platform**: All folder paths should work on Windows/Mac/Linux after conversion

---

**Status:** Ready for implementation  
**Created By:** Kiro AI Agent  
**Last Updated:** August 21, 2026 13:49 UTC+3
