# Ludiglot Documentation Index

Welcome to the Ludiglot documentation. This project is organized following open-source standards to make it easy for users to get started and for developers to contribute.

---

## 📖 User Guides
- [Quick Start Guide](usage/quick-start.md) - Get up and running in 5 minutes.
- [Data Management](usage/data-management.md) - Learn how to set up game text and audio assets.

---

## 🏗️ Technical Design
- [Architecture Overview](design/architecture.md) - How the system works under the hood.
- [OCR System](design/ocr-system.md) - Deep dive into Windows OCR and fallback strategies.
- [Audio System](design/audio-system.md) - Understanding Wwise integration and Hash calculation.

---

## 🛠️ Development
- [Contributing Guide](../CONTRIBUTING.md) - How to help us improve Ludiglot.
- [Project Roadmap](development/roadmap.md) - Current progress and future plans.
- [Development Principles](development/DEVELOPMENT_PRINCIPLES.md) - Architecture design philosophy and best practices.

### 🐛 Troubleshooting & Case Studies
- ⭐ **[Nested Directory Database Issue](development/troubleshooting-nested-directory.md)** - Complete investigation of v3.1 data indexing problem and fix (2026-02-10)

---

## 📝 Project Documents
- [Changelog](../CHANGELOG.md) - Version history, feature updates, and bug fixes.
- [Third-Party Notices](../THIRD_PARTY_NOTICES.md) - Open-source dependencies and licenses.

---

## 🔍 Recent Updates

### 2026-02-10 - Database Construction Fix
- ✅ **Fixed**: 12,000+ missing text entries due to nested directory structure
- ✅ **Enhanced**: Automatic nested language directory discovery
- ✅ **Verified**: Database grew from 296,080 to 308,129 keys
- 📄 **Details**: See [Nested Directory Troubleshooting](development/troubleshooting-nested-directory.md)

### 2026-01-29 - Font Extraction & Documentation Updates
- ✅ Automatic game font extraction (.ufont → .ttf)
- ✅ Configuration unification (fonts_root)
- ✅ Major documentation updates and streamlining

---

**Quick Links**: [Quick Start](usage/quick-start.md) | [Roadmap](development/roadmap.md) | [Architecture](design/architecture.md) | [Changelog](../CHANGELOG.md)

