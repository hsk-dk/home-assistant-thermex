# Quick Reference: GitHub Workflows

## 🚀 Creating a Release

### Regular Release
1. Go to **Actions** → **Create Release**
2. Enter tag: `v3.4.1`
3. Check **Use draft** ✓
4. Click **Run workflow**

### Pre-release
1. Go to **Actions** → **Create Release**
2. Enter tag with a suffix: `v3.5.0-rc1` (letters and digits only after the dash)
3. Check **Pre-release** ✓ and uncheck **Use draft**
4. Paste your own release notes
5. Click **Run workflow**

## 🏷️ Labels for PRs

| Category | Labels | Use For |
|----------|--------|---------|
| 🛠 Breaking | `breaking-change`, `major` | API changes, breaking compatibility |
| 🚀 Features | `feature`, `enhancement`, `feat` | New functionality |
| 🐛 Bug Fixes | `fix`, `bugfix`, `bug` | Fixing broken functionality |
| 🧰 Maintenance | `chore`, `dependencies`, `maintenance` | Code maintenance, updates |
| 📚 Documentation | `documentation`, `docs` | Documentation changes |
| ⚡ Performance | `performance`, `perf` | Performance improvements |
| 🔒 Security | `security` | Security-related changes |

## 🌿 Branch Naming

```bash
feature/new-sensor       # New features
fix/sensor-update        # Bug fixes
chore/update-deps        # Maintenance
docs/installation        # Documentation
```

## 📋 Commit Messages

```bash
feat: add delayed turn-off functionality
fix: resolve sensor update issue
docs: update installation instructions
chore: bump dependency versions
```

## 🔢 Version Bumping

- **Major** (v3.0.0): Breaking changes
- **Minor** (v3.1.0): New features
- **Patch** (v3.0.1): Bug fixes

## ❌ Exclude from Release Notes

Add label `skip-changelog` to exclude from release notes.

## 🆘 Common Issues

| Issue | Solution |
|-------|----------|
| Tag already exists | Delete tag: `git tag -d v3.4.1 && git push origin :refs/tags/v3.4.1` |
| No draft release | Check PR has proper labels |
| Changes not in notes | Verify labels on merged PR |
| Wrong version bump | Check version resolver labels |

## 📖 Full Documentation

See [WORKFLOWS_GUIDE.md](WORKFLOWS_GUIDE.md) for complete documentation.
