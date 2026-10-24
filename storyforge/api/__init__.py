"""HTTP API for starting and reading Storyforge GitHub Actions runs.

The API is a thin layer over the existing workflows. It never runs inference
itself: it dispatches workflows with the caller's GitHub token, tracks their
runs, and reads the artifacts they upload. See docs/API.md.
"""
