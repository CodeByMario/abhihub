---
name: Bug Report
about: Report a bug or unexpected behavior
title: '[bug]: '
labels: ['bug', 'needs-triage']
body:
  - type: markdown
    attributes:
      value: |
        Thanks for reporting a bug! Please fill out the information below.
  - type: textarea
    id: description
    attributes:
      label: Description
      description: A clear and concise description of what the bug is.
      placeholder: "The app crashes when I click the save button..."
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior.
      render: markdown
      placeholder: |
        1. Go to '...'
        2. Click on '...'
        3. See error
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What you expected to happen.
      placeholder: "I expected the save button to save my changes."
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: Actual Behavior
      description: What actually happened.
      placeholder: "Instead, the app crashed with a 500 error."
    validations:
      required: true
  - type: input
    id: environment
    attributes:
      label: Environment
      description: "OS, browser, app version, etc."
      placeholder: "Windows 11, Chrome 120, v1.2.3"
    validations:
      required: false
  - type: checkboxes
    id: checks
    attributes:
      label: Checklist
      options:
        - label: I have searched for existing issues
          required: true
        - label: I have tried clearing my cache
          required: false
        - label: I have tried in an incognito window
          required: false
