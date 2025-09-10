# Contributing to Thermex Hood Integration

Thank you for your interest in contributing to the Thermex Hood Integration! This guide will help you get started.

## Quick Start

1. **Fork** the repository
2. **Clone** your fork locally
3. **Create a branch** with descriptive name
4. **Make your changes**
5. **Test thoroughly**
6. **Create a pull request**

## Development Workflow

### Branch Naming

Use descriptive branch names that indicate the type of change:

```bash
feature/new-sensor-type       # New features
fix/connection-timeout        # Bug fixes
docs/installation-guide       # Documentation
chore/update-dependencies     # Maintenance
```

### Commit Messages

Follow conventional commit format:

```bash
feat: add support for new hood model
fix: resolve connection timeout issue
docs: update installation instructions
chore: bump Home Assistant core requirement
```

### Pull Requests

1. **Use the PR template** - It will help you provide all necessary information
2. **Add appropriate labels** - Essential for automatic release notes
3. **Link related issues** - Use "Fixes #123" or "Closes #123"
4. **Test thoroughly** - Include testing details in the PR description

## Labeling Guide

Proper labeling is crucial for automatic release note generation:

| Label | Use For | Release Notes Category |
|-------|---------|----------------------|
| `feature`, `enhancement` | New functionality | 🚀 Features |
| `fix`, `bug` | Bug fixes | 🐛 Bug Fixes |
| `breaking-change`, `major` | Breaking changes | 🛠 Breaking Changes |
| `documentation`, `docs` | Documentation | 📚 Documentation |
| `chore`, `maintenance` | Code maintenance | 🧰 Maintenance |
| `performance`, `perf` | Performance improvements | ⚡ Performance |
| `security` | Security fixes | 🔒 Security |
| `skip-changelog` | Exclude from release notes | (Not shown) |

## Development Setup

### Prerequisites

- Python 3.11+
- Home Assistant development environment
- Access to Thermex hood with API enabled

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/hsk-dk/home-assistant-thermex.git
   cd home-assistant-thermex
   ```

2. **Set up development environment:**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   
   # Install dependencies
   pip install -r requirements-dev.txt
   ```

3. **Run tests:**
   ```bash
   pytest
   ```

4. **Code formatting:**
   ```bash
   black custom_components/
   isort custom_components/
   ```

## Testing

### Manual Testing

1. **Install in development Home Assistant:**
   - Copy `custom_components/thermex_api` to your HA `custom_components/` folder
   - Restart Home Assistant
   - Set up the integration

2. **Test scenarios:**
   - Initial setup and discovery
   - Fan speed control
   - Light control
   - Filter monitoring
   - Connection recovery
   - Configuration changes

### Automated Testing

Run the test suite:
```bash
pytest tests/
```

## Code Standards

### Python Code

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use [Black](https://black.readthedocs.io/) for code formatting
- Use [isort](https://isort.readthedocs.io/) for import sorting
- Add type hints where appropriate
- Write docstrings for public methods

### Home Assistant Standards

- Follow [Home Assistant development guidelines](https://developers.home-assistant.io/)
- Use async/await for I/O operations
- Implement proper error handling
- Add appropriate logging
- Support configuration via UI

## Documentation

### Code Documentation

- Write clear docstrings for classes and methods
- Add inline comments for complex logic
- Update type hints

### User Documentation

- Update README.md for user-facing changes
- Add configuration examples
- Update troubleshooting section if needed

## Release Process

The project uses automated workflows for releases:

1. **Development:** Work on feature branches
2. **Pull Request:** Create PR with proper labels
3. **Review:** Maintainer review and merge
4. **Draft Release:** Automatically created with release notes
5. **Release:** Maintainer publishes using GitHub Actions

See [WORKFLOWS_GUIDE.md](WORKFLOWS_GUIDE.md) for detailed information.

## Getting Help

- **Questions:** Create an issue with the `question` label
- **Bugs:** Use the bug report template
- **Features:** Use the feature request template
- **Development:** Check the [workflows guide](WORKFLOWS_GUIDE.md)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/). Please be respectful and constructive in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

Thank you for contributing! 🎉
